"""External message delivery log (FR-NOTIF-013) and personal notification preferences (FR-NOTIF-011).

Delivery log: customer text messages (sms_messages) and emails (email.* outbox events) with status, attempts and the
last error. Message bodies are not shown for emails (they can hold sign-in links); phone numbers and addresses are
masked unless the viewer may see customer contact details.

Preferences: the owner's decision is that safety and money notifications are always delivered (approvals, items
ready, kitchen delays, payment problems, cash variances, system alerts). Only the optional kinds below can be muted.
"""
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.models import Branch, NotificationPreference, OutboxEvent, SmsMessage
from app.services.platform import audit

OPTIONAL_KINDS = {"Stock": "Low stock and expiry alerts", "Reminder": "Open-session reminders", "Digest": "Daily summaries"}
MANDATORY_KINDS = {"Approval": "Approvals waiting for you", "Kitchen": "Items ready and kitchen delays", "Payment": "Failed or unconfirmed payments",
                   "Cash": "Cash variances", "System": "System and security alerts"}

EMAIL_SUBJECTS = {"email.password_reset": "Password reset", "email.purchase_order": "Purchase order to supplier",
                  "email.online_order_confirmation": "Online order confirmation", "email.online_order_rejected": "Online order not accepted",
                  "email.scheduled_report": "Scheduled report ready"}


# ---------------------------------------------------------------- preferences
def muted_users(db, user_ids: list[uuid.UUID], kind: str) -> set[uuid.UUID]:
    if kind not in OPTIONAL_KINDS or not user_ids:
        return set()
    return set(db.scalars(select(NotificationPreference.user_id).where(NotificationPreference.user_id.in_(user_ids), NotificationPreference.kind == kind,
                                                                       NotificationPreference.enabled.is_(False))))


def preferences(ctx: Ctx) -> list[dict]:
    mine = {p.kind: p.enabled for p in ctx.db.scalars(select(NotificationPreference).where(NotificationPreference.user_id == ctx.user_id))}
    return ([{"kind": k, "label": v, "mandatory": True, "enabled": True} for k, v in MANDATORY_KINDS.items()]
            + [{"kind": k, "label": v, "mandatory": False, "enabled": mine.get(k, True)} for k, v in OPTIONAL_KINDS.items()])


def set_preferences(ctx: Ctx, changes: dict[str, bool]) -> list[dict]:
    bad = [k for k in changes if k not in OPTIONAL_KINDS]
    if bad:
        raise BusinessRuleError("NOTIFICATION_MANDATORY", "Safety and money notifications can't be turned off.", details=[{"field": k, "issue": "mandatory"} for k in bad])
    before = {p["kind"]: p["enabled"] for p in preferences(ctx) if not p["mandatory"]}
    for kind, enabled in changes.items():
        row = ctx.db.get(NotificationPreference, (ctx.user_id, kind))
        if row is None:
            ctx.db.add(NotificationPreference(user_id=ctx.user_id, kind=kind, enabled=enabled))
        else:
            row.enabled = enabled
    ctx.db.flush()
    audit(ctx.db, ctx, "notification.preferences", "User", ctx.user_id, before=before, after=changes)
    return preferences(ctx)


# ---------------------------------------------------------------- delivery log
def _mask_phone(msisdn: str) -> str:
    return msisdn[:5] + "•" * max(len(msisdn) - 8, 0) + msisdn[-3:] if len(msisdn) > 8 else "•••"


def _mask_email(addr: str) -> str:
    name, _, domain = addr.partition("@")
    return f"{name[:1]}•••@{domain}" if domain else "•••"


def email_status(e: OutboxEvent, max_attempts: int) -> str:
    if e.processed_at:
        return e.delivery_status or "Sent"
    if e.attempts >= max_attempts:
        return "Failed"
    return "Retrying" if e.attempts else "Queued"


def _day_bounds(ctx: Ctx, d_from: date, d_to: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(ctx.db.get(Branch, ctx.branch_id).timezone)
    return datetime.combine(d_from, time.min, tz), datetime.combine(d_to + timedelta(days=1), time.min, tz)


def log(ctx: Ctx, d_from: date, d_to: date, channel: str | None = None, status: str | None = None) -> list[dict]:
    from app.services.sms import MAX_ATTEMPTS as SMS_MAX
    from app.workers.celery_app import MAX_ATTEMPTS as EMAIL_MAX

    if d_to < d_from or (d_to - d_from).days > 92:
        raise BusinessRuleError("VALIDATION_ERROR", "Choose a range of up to 3 months.")
    start, end = _day_bounds(ctx, d_from, d_to)
    full = ctx.can("customers.contact.view")
    here = or_(SmsMessage.branch_id == ctx.branch_id, SmsMessage.branch_id.is_(None))
    out = []
    if channel in (None, "SMS"):
        for m in ctx.db.scalars(select(SmsMessage).where(here, SmsMessage.created_at >= start, SmsMessage.created_at < end).order_by(SmsMessage.created_at.desc()).limit(500)):
            out.append({"id": m.id, "channel": "SMS", "to": m.to_msisdn if full else _mask_phone(m.to_msisdn), "purpose": m.purpose,
                        "summary": m.content if full else None, "status": "Failed" if m.status == "Failed" else ("Retrying" if m.status == "Queued" and m.attempts else m.status),
                        "attempts": m.attempts, "max_attempts": SMS_MAX, "last_error": m.last_error, "created_at": m.created_at, "sent_at": m.sent_at,
                        "next_attempt_at": m.next_attempt_at, "provider": m.provider})
    if channel in (None, "Email"):
        q = select(OutboxEvent).where(OutboxEvent.event_type.like("email.%"), or_(OutboxEvent.branch_id == ctx.branch_id, OutboxEvent.branch_id.is_(None)),
                                      OutboxEvent.created_at >= start, OutboxEvent.created_at < end).order_by(OutboxEvent.created_at.desc()).limit(500)
        for e in ctx.db.scalars(q):
            addr = str((e.payload or {}).get("email") or "")
            out.append({"id": e.id, "channel": "Email", "to": (addr if full else _mask_email(addr)) if addr else "—", "purpose": EMAIL_SUBJECTS.get(e.event_type, e.event_type[6:]),
                        "summary": None, "status": email_status(e, EMAIL_MAX), "attempts": e.attempts, "max_attempts": EMAIL_MAX, "last_error": e.last_error,
                        "created_at": e.created_at, "sent_at": e.processed_at, "next_attempt_at": e.next_attempt_at, "provider": "SMTP"})
    if status:
        out = [r for r in out if r["status"] == status]
    return sorted(out, key=lambda r: r["created_at"], reverse=True)


def retry(ctx: Ctx, channel: str, message_id: uuid.UUID) -> dict:
    """A failed message gets a fresh set of attempts. Successful messages are never re-sent from here."""
    if channel == "SMS":
        m = ctx.db.get(SmsMessage, message_id)
        if m is None or m.branch_id not in (ctx.branch_id, None):
            raise NotFound("Message")
        if m.status != "Failed":
            raise Conflict("NOT_FAILED", "Only failed messages can be retried.")
        m.status, m.attempts, m.next_attempt_at, m.last_error = "Queued", 0, None, None
    else:
        e = ctx.db.get(OutboxEvent, message_id)
        if e is None or not e.event_type.startswith("email.") or e.branch_id not in (ctx.branch_id, None):
            raise NotFound("Message")
        from app.workers.celery_app import MAX_ATTEMPTS

        if email_status(e, MAX_ATTEMPTS) != "Failed":
            raise Conflict("NOT_FAILED", "Only failed messages can be retried.")
        e.attempts, e.next_attempt_at, e.delivery_status = 0, None, None
    audit(ctx.db, ctx, "message.retry", channel, message_id)
    return {"id": message_id, "channel": channel, "status": "Queued"}


def failed_filter():
    """Outbox rows the worker may pick up now (back-off respected)."""
    from app.utils.timeutil import utcnow

    return and_(OutboxEvent.processed_at.is_(None), or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= utcnow()))
