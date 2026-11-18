"""Online customer accounts by phone verification (FR-ONL-004, FR-ONL-010; BR-045, BR-046).

A 6-digit code goes out by SMS; only an HMAC of it is stored. Codes last 10 minutes and allow 5 tries, and a phone
can ask for at most 3 codes per 15 minutes. A verified phone signs in to its existing customer record, or creates
one with the name given (data minimisation: name and phone only). The session token is opaque; only its hash is kept.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, BusinessRuleError, Unauthorized
from app.integrations.sms import get_sender
from app.models import Branch, Customer, CustomerSession, Order, PhoneVerification
from app.services import sms
from app.services.platform import audit, get_setting
from app.utils.timeutil import utcnow

CODE_MINUTES, MAX_TRIES, MAX_CODES, WINDOW_MINUTES = 10, 5, 3, 15


def _digest(phone: str, code: str) -> str:
    return hmac.new(get_settings().JWT_SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _phone(raw: str) -> str:
    from app.services.front import normalise_phone

    phone = normalise_phone(raw)
    if not phone:
        raise BusinessRuleError("PHONE_INVALID", "Enter a valid phone number.")
    return phone


def request_code(db: Session, branch: Branch, raw_phone: str) -> dict:
    if get_sender() is None:
        raise AppError("SMS_UNAVAILABLE", "Sign-in by phone isn't available right now.", 503)
    phone = _phone(raw_phone)
    now = utcnow()
    recent = db.scalar(select(func.count()).select_from(PhoneVerification).where(PhoneVerification.phone_e164 == phone,
                                                                                PhoneVerification.created_at > now - timedelta(minutes=WINDOW_MINUTES)))
    if recent >= MAX_CODES:
        raise AppError("RATE_LIMITED", "Too many codes requested. Please wait a few minutes.", 429, retry_after_seconds=WINDOW_MINUTES * 60)
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(PhoneVerification(phone_e164=phone, code_hash=_digest(phone, code), expires_at=now + timedelta(minutes=CODE_MINUTES)))
    sms.queue(db, branch.id, phone, "auth.code", f"{branch.name_en}: your sign-in code is {code}. It expires in {CODE_MINUTES} minutes. Don't share it.")
    return {"sent": True, "expires_in_seconds": CODE_MINUTES * 60}


def verify(db: Session, branch: Branch, raw_phone: str, code: str, name: str | None) -> dict:
    phone = _phone(raw_phone)
    now = utcnow()
    v = db.scalar(select(PhoneVerification).where(PhoneVerification.phone_e164 == phone, PhoneVerification.consumed_at.is_(None),
                                                  PhoneVerification.expires_at > now).order_by(PhoneVerification.created_at.desc()).limit(1).with_for_update())
    if v is None or v.attempts >= MAX_TRIES:
        raise BusinessRuleError("CODE_INVALID", "That code isn't valid any more. Ask for a new one.")
    if not hmac.compare_digest(v.code_hash, _digest(phone, code.strip())):
        v.attempts += 1
        db.flush()
        db.commit()  # keep the failed-attempt count even though this request fails
        raise BusinessRuleError("CODE_INVALID", "That code isn't right.", tries_left=max(MAX_TRIES - v.attempts, 0))
    v.consumed_at = now
    c = db.scalar(select(Customer).where(Customer.phone_e164 == phone, Customer.merged_into_id.is_(None), Customer.anonymised_at.is_(None)))
    from app.services.online import system_ctx

    ctx = system_ctx(db, branch, {"customers.view", "customers.manage"})
    if c is None:
        if not name or not name.strip():
            raise BusinessRuleError("NAME_REQUIRED", "Tell us your name to create your account.", details=[{"field": "name", "issue": "required"}])
        from app.services.front import create_customer

        c = create_customer(ctx, {"name": name.strip()[:120], "phone": phone}, force=False)
    raw = secrets.token_urlsafe(32)
    days = int(get_setting(db, "sms", branch.id).get("customer_session_days", 30))
    db.add(CustomerSession(customer_id=c.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=now + timedelta(days=days)))
    audit(db, ctx, "customer.sign_in", "Customer", c.id, after={"channel": "sms_code"})
    return {"customer_token": raw, "expires_at": now + timedelta(days=days), "customer": {"name": c.name, "loyalty_points": c.loyalty_points}}


def current(db: Session, token: str | None, required: bool = True) -> Customer | None:
    if not token:
        if required:
            raise Unauthorized("Sign in to see your account.", code="CUSTOMER_SIGN_IN_REQUIRED")
        return None
    s = db.scalar(select(CustomerSession).where(CustomerSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if s is None or s.revoked_at or s.expires_at < utcnow():
        raise Unauthorized("Your sign-in has expired. Please sign in again.", code="CUSTOMER_SESSION_INVALID")
    c = db.get(Customer, s.customer_id)
    if c is None or c.merged_into_id or c.anonymised_at:
        raise Unauthorized("This account isn't available.", code="CUSTOMER_SESSION_INVALID")
    return c


def sign_out(db: Session, token: str) -> None:
    s = db.scalar(select(CustomerSession).where(CustomerSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if s and not s.revoked_at:
        s.revoked_at = utcnow()


def my_orders(db: Session, c: Customer) -> list[dict]:
    """FR-ONL-010: only this customer's own orders."""
    rows = db.execute(select(Order, Branch.name_en).join(Branch, Branch.id == Order.branch_id).where(Order.customer_id == c.id)
                      .order_by(Order.created_at.desc()).limit(50)).all()
    return [{"order_no": o.order_no, "business_date": o.business_date, "branch": bname, "order_type": o.order_type, "status": o.order_status,
             "total": o.grand_total, "currency": o.currency,
             "items": [{"name": i.item_name_en_snapshot, "quantity": i.quantity} for i in o.items if i.item_status != "Cancelled"]} for o, bname in rows]
