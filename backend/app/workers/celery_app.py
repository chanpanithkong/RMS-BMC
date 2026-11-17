"""Background worker (SRS §12.2 Workers): outbox delivery and scheduled integrity checks.

Run:  celery -A app.workers.celery_app worker -B -l info   (needs REDIS_URL)
"""
import logging
import os

from celery import Celery
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import session_factory
from app.integrations.email import EmailSender
from app.models import OutboxEvent
from app.services.platform import notify_permission, verify_audit_chain
from app.utils.timeutil import utcnow

log = logging.getLogger("rms.worker")
_broker = get_settings().REDIS_URL or "memory://"
celery = Celery("rms", broker=_broker, backend=None)
celery.conf.beat_schedule = {
    "outbox": {"task": "app.workers.celery_app.process_outbox", "schedule": 10.0},
    "audit-chain": {"task": "app.workers.celery_app.verify_audit", "schedule": 86400.0},
}
MAX_ATTEMPTS = int(os.environ.get("OUTBOX_MAX_ATTEMPTS", "8"))


def handle(event: OutboxEvent, mailer: EmailSender) -> None:
    if event.event_type == "email.password_reset":
        link = f"{get_settings().FRONTEND_URL}/reset-password?token={event.payload['token']}"
        if event.payload.get("email"):
            mailer.send(event.payload["email"], "Reset your RMS password", f"Use this link within 30 minutes:\n{link}\n\nIf you didn't ask for this, ignore this email.")
    elif event.event_type == "email.purchase_order":
        mailer.send(event.payload["email"], f"Purchase order {event.payload['po_no']}", purchase_order_text(event.payload))
    elif event.event_type == "email.online_order_confirmation":  # FR-ONL-008
        p = event.payload
        mailer.send(p["email"], f"Order {p['order_no']} received – {p['branch']}",
                    f"Thank you. We've received your {p['fulfilment'].lower()} order {p['order_no']} for {p['total']} {p['currency']}.\n"
                    f"Follow it here: {p['tracking_url']}\n\nThe link stops working after a while for your privacy.")
    elif event.event_type == "email.online_order_rejected":
        p = event.payload
        mailer.send(p["email"], f"Order {p['order_no']} couldn't be accepted – {p['branch']}",
                    f"Sorry, {p['branch']} couldn't accept order {p['order_no']}: {p['reason']}.")
    else:
        # Not delivered: leave it unprocessed and visible rather than dropping it silently.
        raise ValueError(f"No outbox handler for {event.event_type}")


def purchase_order_text(p: dict) -> str:
    """Plain-text PO email (FR-PUR-005). The printable/PDF document is not built yet."""
    lines = [f"Purchase order {p['po_no']} from {p.get('branch') or 'our restaurant'}", f"Supplier: {p.get('supplier', '')}"]
    if p.get("delivery_date"):
        lines.append(f"Requested delivery: {p['delivery_date']}")
    lines.append("")
    for ln in p.get("lines", []):
        lines.append(f"- {ln['item']}: {ln['quantity']} {ln['unit']} at {ln['unit_price']} {p.get('currency', 'USD')}")
    lines += ["", f"Total: {p['total']} {p.get('currency', 'USD')}"]
    return "\n".join(lines)


@celery.task
def process_outbox(batch: int = 50) -> int:
    """At-least-once delivery with retry back-off counted in attempts (FR-NOTIF-013)."""
    mailer = EmailSender()
    done = 0
    with session_factory()() as db:
        rows = db.scalars(select(OutboxEvent).where(OutboxEvent.processed_at.is_(None), OutboxEvent.attempts < MAX_ATTEMPTS)
                          .order_by(OutboxEvent.created_at).limit(batch).with_for_update(skip_locked=True)).all()
        for e in rows:
            try:
                handle(e, mailer)
                e.processed_at = utcnow()
                done += 1
            except Exception:
                e.attempts += 1
                log.exception("outbox event %s failed (attempt %s)", e.id, e.attempts)
        db.commit()
    return done


@celery.task
def verify_audit() -> dict:
    """FR-AUD-010: daily hash-chain verification; alerts administrators on a break."""
    with session_factory()() as db:
        result = verify_audit_chain(db)
        if not result["valid"]:
            from app.models import Branch

            for b in db.scalars(select(Branch)):
                notify_permission(db, b.id, "audit.view", "System", "Audit chain break detected", f"Entry {result['broken_at_id']} failed verification.", "/audit")
            db.commit()
        return result
