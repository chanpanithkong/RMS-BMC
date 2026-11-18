"""Customer text messages: online order updates, sign-in codes, reservation messages (owner's choice).

Messages are queued in sms_messages inside the business transaction (so a rolled-back order sends nothing) and
delivered by the worker with up to 5 attempts. A dedupe key stops the same message being queued twice.
Nothing is sent while the 'sms' setting is off, except sign-in codes, which only need a configured provider.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.sms import SmsError, get_sender, msisdn
from app.models import Branch, Order, SmsMessage
from app.services.platform import get_setting
from app.utils.timeutil import utcnow

log = logging.getLogger("rms.sms")
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 30


def enabled(db: Session, branch_id, kind: str) -> bool:
    s = get_setting(db, "sms", branch_id)
    return bool(s.get("enabled")) and bool(s.get(kind, True))


def queue(db: Session, branch_id, phone_e164: str | None, purpose: str, content: str, dedupe_key: str | None = None) -> bool:
    """Returns False when there's no number or the same message was already queued."""
    if not phone_e164:
        return False
    stmt = insert(SmsMessage).values(branch_id=branch_id, to_msisdn=msisdn(phone_e164), purpose=purpose, content=content, dedupe_key=dedupe_key)
    if dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=SmsMessage.dedupe_key.is_not(None))
    res = db.execute(stmt.returning(SmsMessage.id))
    return res.scalar() is not None


def deliver_pending(db: Session, batch: int = 50) -> dict:
    """Worker: send queued messages. Without a provider they are marked Logged (like emails without SMTP)."""
    sender = get_sender()
    counts = {"sent": 0, "failed": 0, "retry": 0, "logged": 0}
    now = utcnow()
    rows = db.scalars(select(SmsMessage).where(SmsMessage.status == "Queued", (SmsMessage.next_attempt_at.is_(None)) | (SmsMessage.next_attempt_at <= now))
                      .order_by(SmsMessage.created_at).limit(batch).with_for_update(skip_locked=True)).all()
    for m in rows:
        if sender is None:
            m.status = "Logged"
            log.info("SMS (no provider) %s to %s***", m.purpose, m.to_msisdn[:5])
            counts["logged"] += 1
            continue
        m.attempts += 1
        m.provider = sender.name
        try:
            m.provider_ref = sender.send(m.to_msisdn, m.content)
            m.status, m.sent_at, m.last_error = "Sent", utcnow(), None
            counts["sent"] += 1
        except SmsError as e:
            m.last_error = str(e)[:500]
            if m.attempts >= MAX_ATTEMPTS:
                m.status = "Failed"
                counts["failed"] += 1
            else:
                m.next_attempt_at = now + timedelta(seconds=BACKOFF_SECONDS * 2 ** (m.attempts - 1))  # 30 s, 1, 2, 4 minutes
                counts["retry"] += 1
            log.warning("SMS %s attempt %s failed: %s", m.id, m.attempts, e)
    db.flush()
    return counts


# ---------------------------------------------------------------- templates (English until Khmer support is confirmed with PlasGate)
def _branch(db: Session, branch_id) -> Branch:
    return db.get(Branch, branch_id)


def _order_phone(order: Order) -> str | None:
    from app.services.front import normalise_phone

    try:
        return normalise_phone(order.customer_phone)
    except Exception:  # noqa: BLE001 - an unusable number just means no SMS
        return None


def order_update(db: Session, order: Order, kind: str, link: str | None = None, reason: str | None = None) -> bool:
    """kind: received | accepted | rejected | ready | out_for_delivery (online orders only)."""
    if order.channel != "Online" or not enabled(db, order.branch_id, "order_updates"):
        return False
    b = _branch(db, order.branch_id)
    text = {
        "received": f"{b.name_en}: we received order {order.order_no}. Track it: {link}" if link else f"{b.name_en}: we received order {order.order_no}.",
        "accepted": f"{b.name_en}: order {order.order_no} is accepted and being prepared.",
        "rejected": f"{b.name_en}: sorry, order {order.order_no} couldn't be accepted. {reason or ''}".strip(),
        "ready": f"{b.name_en}: order {order.order_no} is ready for pickup.",
        "out_for_delivery": f"{b.name_en}: order {order.order_no} is on its way.",
    }[kind]
    return queue(db, order.branch_id, _order_phone(order), f"order.{kind}", text, f"order:{order.id}:{kind}")


def reservation_message(db: Session, r, kind: str) -> bool:
    """kind: confirmed | reminder. Times are shown in the branch's time zone."""
    from zoneinfo import ZoneInfo

    from app.services.front import normalise_phone

    if not enabled(db, r.branch_id, "reservations"):
        return False
    b = _branch(db, r.branch_id)
    when: datetime = r.reserved_at.astimezone(ZoneInfo(b.timezone))
    text = (f"{b.name_en}: your table for {r.party_size} is booked for {when:%a %d %b at %H:%M}. Call {b.phone or 'us'} to change it."
            if kind == "confirmed" else f"{b.name_en}: reminder of your table for {r.party_size} today at {when:%H:%M}. See you soon!")
    try:
        phone = normalise_phone(r.guest_phone)
    except Exception:  # noqa: BLE001
        phone = None
    return queue(db, r.branch_id, phone, f"reservation.{kind}", text, f"reservation:{r.id}:{kind}:{r.reserved_at.isoformat()}")


def waitlist_ready(db: Session, w) -> bool:
    from app.services.front import normalise_phone

    if not enabled(db, w.branch_id, "reservations"):
        return False
    b = _branch(db, w.branch_id)
    try:
        phone = normalise_phone(w.phone)
    except Exception:  # noqa: BLE001
        phone = None
    return queue(db, w.branch_id, phone, "waitlist.ready", f"{b.name_en}: your table for {w.party_size} is ready. Please come to the front desk.",
                 f"waitlist:{w.id}:ready")


def reminders_due(db: Session, now: datetime | None = None) -> int:
    """Worker: one reminder per reservation, sent when it's within the configured minutes."""
    from datetime import timedelta

    from app.models import Reservation

    now = now or utcnow()
    n = 0
    for b in db.scalars(select(Branch).where(Branch.is_active)):
        s = get_setting(db, "sms", b.id)
        if not (s.get("enabled") and s.get("reservations", True)):
            continue
        horizon = now + timedelta(minutes=int(s.get("reservation_reminder_minutes", 120)))
        for r in db.scalars(select(Reservation).where(Reservation.branch_id == b.id, Reservation.status == "Confirmed", Reservation.reminder_sent_at.is_(None),
                                                      Reservation.reserved_at > now, Reservation.reserved_at <= horizon).with_for_update(skip_locked=True)):
            reservation_message(db, r, "reminder")
            r.reminder_sent_at = now
            n += 1
    db.flush()
    return n
