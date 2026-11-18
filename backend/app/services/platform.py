"""Cross-cutting services: audit chain, idempotency, numbering, approvals, notifications, settings."""
import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import Ctx, load_permissions
from app.core.exceptions import AppError, BusinessRuleError, Conflict, Forbidden
from app.core.realtime import emit
from app.core.security import verify_secret
from app.models import Approval, AuditLog, IdempotencyKey, Notification, NumberSequence, RolePermission, Setting, User, UserBranch, UserRole
from app.permissions.catalog import APPROVAL_ACTIONS
from app.utils.timeutil import utcnow

GENESIS = "0" * 64


def _jsonable(data: Any) -> Any:
    return None if data is None else jsonable_encoder(data)


# ---------------------------------------------------------------- audit (BR-023)
def audit(db: Session, ctx: Ctx | None, action: str, entity_type: str, entity_id: Any = None, before: dict | None = None, after: dict | None = None,
          reason: str | None = None, branch_id: uuid.UUID | None = None, actor_id: uuid.UUID | None = None) -> AuditLog:
    """Append a hash-chained entry in the caller's transaction; failure rolls the business change back."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('rms_audit_chain'))"))
    prev = db.scalar(select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1)) or GENESIS
    occurred = utcnow()
    entry = AuditLog(
        occurred_at=occurred, actor_user_id=ctx.user_id if ctx else actor_id, actor_type="User" if (ctx or actor_id) else "System",
        device_id=ctx.device_id if ctx else None, ip=ctx.ip if ctx else None, branch_id=branch_id or (ctx.branch_id if ctx else None),
        action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None,
        before_data=_jsonable(before), after_data=_jsonable(after), reason=reason, correlation_id=ctx.correlation_id if ctx else None, prev_hash=prev,
    )
    entry.entry_hash = hash_entry(entry)
    db.add(entry)
    db.flush()
    return entry


def hash_entry(e: AuditLog) -> str:
    body = json.dumps([e.prev_hash, e.occurred_at.isoformat(), str(e.actor_user_id), e.action, e.entity_type, e.entity_id, e.before_data, e.after_data, e.reason],
                      sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def verify_audit_chain(db: Session) -> dict:
    """FR-AUD-010: recompute every hash in order."""
    prev = GENESIS
    count = 0
    for e in db.scalars(select(AuditLog).order_by(AuditLog.id)).yield_per(500):
        if e.prev_hash != prev or hash_entry(e) != e.entry_hash:
            return {"valid": False, "broken_at_id": e.id, "checked": count}
        prev = e.entry_hash
        count += 1
    return {"valid": True, "checked": count}


# ---------------------------------------------------------------- idempotency (BR-030)
def idempotent(db: Session, scope: str, key: str | None, payload: Any, run: Callable[[], Any], status_code: int = 200) -> Any:
    if not key:
        raise BusinessRuleError("IDEMPOTENCY_KEY_REQUIRED", "Send an Idempotency-Key header with this request.", 400)
    if len(key) > 80:
        raise BusinessRuleError("IDEMPOTENCY_KEY_INVALID", "Idempotency-Key is too long.", 400)
    digest = hashlib.sha256(json.dumps(jsonable_encoder(payload), sort_keys=True).encode()).hexdigest()
    # Reserve the key first: a concurrent duplicate blocks here until this transaction ends.
    inserted = db.execute(
        insert(IdempotencyKey).values(scope=scope, key=key, request_hash=digest, response_status=0, response_body={}).on_conflict_do_nothing().returning(IdempotencyKey.key)
    ).scalar()
    if inserted is None:
        row = db.get(IdempotencyKey, (scope, key))
        if row.request_hash != digest:
            raise Conflict("IDEMPOTENCY_MISMATCH", "This Idempotency-Key was already used with a different request.")
        return row.response_body
    result = jsonable_encoder(run())
    row = db.get(IdempotencyKey, (scope, key))
    row.response_status = status_code
    row.response_body = result
    return result


# ---------------------------------------------------------------- numbering (BR-001, BR-049)
def next_number(db: Session, branch_id: uuid.UUID, series: str, period: str) -> int:
    stmt = insert(NumberSequence).values(branch_id=branch_id, series=series, period=period, next_value=2)
    stmt = stmt.on_conflict_do_update(index_elements=["branch_id", "series", "period"], set_={"next_value": NumberSequence.next_value + 1})
    return db.execute(stmt.returning(NumberSequence.next_value)).scalar_one() - 1


# ---------------------------------------------------------------- settings
DEFAULT_SETTINGS: dict[str, dict] = {
    "billing": {"base_currency": "USD", "khr_rounding_increment": "100", "partial_payments": True, "default_price_list": "STANDARD"},
    "cash": {"variance_tolerance": {"USD": "1.00", "KHR": "4000"}},
    "inventory": {"consumption_point": "Send", "allow_negative_from_sales": True, "expiry_warning_days": 3},
    "orders": {"require_table_for_dine_in": True, "pay_first_order_types": ["Takeaway"]},
    "kitchen": {"printer_fallback_seconds": 15, "late_ticket_minutes": 15},
    # Online and QR ordering are off until a manager turns them on. Values are placeholders, not SRS figures.
    "online": {"enabled": False, "paused": False, "auto_accept": False, "lead_minutes": 20, "min_order": "0", "max_qty_per_line": 20, "price_list": None,
               "pay_later_allowed": True, "tracking_hours": 24},
    "qr": {"enabled": False, "require_staff_confirmation": True},
    # Customer text messages (owner's choice: online order updates, verification codes, reservation messages). Off until enabled.
    # Accounting export to Xero (owner's choice). Codes start as placeholders; set mapping_confirmed once the accountant has replaced them.
    "accounting": {"accounts": {}, "method_accounts": {}, "category_accounts": {}, "expense_category_accounts": {}, "tax_rate_name": "Tax Exempt",
                   "date_format": "%Y-%m-%d", "tracking_name": "Branch", "include_inventory": True, "include_expenses": True, "include_purchasing": True,
                   "mapping_confirmed": False},
    # GrabFood import per branch: Grab merchant ID, and the commission rate from the Grab agreement (for the cost estimate before settlement).
    "grabfood": {"enabled": False, "merchant_id": None, "commission_rate": None, "menu_channel": "Online"},
    # Customer credit accounts (owner's decisions for D-07): 30-day terms by default; over-limit or overdue charges need a manager.
    "credit": {"enabled": False, "default_terms_days": 30},
    "sms": {"enabled": False, "order_updates": True, "reservations": True, "reservation_reminder_minutes": 120, "customer_session_days": 30},
    # Loyalty rules decided by the owner (D-14): 1 point per 1 USD of net sales, 100 points = 1.00 USD off, points expire 12 months after earning.
    "loyalty": {"enabled": False, "points_per_usd": "1", "redeem_step_points": 100, "redeem_step_value": "1.00", "expiry_months": 12,
                "earn_channels": ["POS", "QR", "Online", "Platform"], "earn_with_promotions": True},
    "reservations": {"default_duration_minutes": 90, "buffer_minutes": 15, "hold_minutes": 60, "grace_minutes": 15, "max_party_size": 20, "walkin_warning_minutes": 60},
    "purchasing": {"receipt_tolerance_pct": "5", "price_tolerance_pct": "5", "invoice_tolerance": "1.00", "separate_receiver": False},
    "recipes": {"target_food_cost_pct": "35"},
}


def get_setting(db: Session, key: str, branch_id: uuid.UUID | None = None) -> dict:
    rows = {s.branch_id: s.value for s in db.scalars(select(Setting).where(Setting.key == key, (Setting.branch_id == branch_id) | Setting.branch_id.is_(None)))}
    return {**DEFAULT_SETTINGS.get(key, {}), **rows.get(None, {}), **(rows.get(branch_id, {}) if branch_id else {})}


# ---------------------------------------------------------------- approvals (BR-009, BR-029, §13.4)
def grant_approval(ctx: Ctx, action: str, approver_username: str, secret: str, amount: Decimal | None, target_id: uuid.UUID | None, reason: str | None) -> Approval:
    """Approver authenticates on the requester's device with password or PIN."""
    if action not in APPROVAL_ACTIONS:
        raise BusinessRuleError("UNKNOWN_APPROVAL_ACTION", f"Approvals aren't defined for '{action}'.")
    permission, limit_key = APPROVAL_ACTIONS[action]
    db = ctx.db
    approver = db.scalar(select(User).where(User.username.ilike(approver_username)))
    if approver is None or approver.status != "Active" or not (verify_secret(secret, approver.pin_hash) or verify_secret(secret, approver.password_hash)):
        raise Forbidden("Approver credentials were not accepted.", code="APPROVER_INVALID")
    if approver.id == ctx.user_id:
        raise Forbidden("You can't approve your own request.", code="SELF_APPROVAL")
    if not any(b.id == ctx.branch_id for b in approver.branches):
        raise Forbidden("The approver isn't assigned to this branch.", code="APPROVER_BRANCH")
    perms, limits = load_permissions(db, approver)
    if permission not in perms:
        raise Forbidden("The approver's role can't approve this.", code="APPROVER_NOT_PERMITTED")
    approver_limit = limits.get(limit_key, Decimal("0"))
    if amount is not None and amount > approver_limit:
        raise Forbidden(f"This exceeds the approver's limit of {approver_limit}.", code="APPROVER_LIMIT_EXCEEDED")
    approval = Approval(branch_id=ctx.branch_id, action=action, target_id=target_id, amount=amount, reason=reason, requested_by=ctx.user_id, approver_id=approver.id,
                        limit_applied=approver_limit, expires_at=utcnow() + timedelta(minutes=get_settings().APPROVAL_TOKEN_MINUTES))
    db.add(approval)
    db.flush()
    audit(db, ctx, "approval.granted", "Approval", approval.id, after={"action": action, "amount": amount, "approver": approver.username, "target_id": target_id}, reason=reason)
    return approval


def consume_approval(ctx: Ctx, approval_id: uuid.UUID | None, action: str, amount: Decimal | None, target_id: uuid.UUID | None) -> uuid.UUID:
    """Validates and marks the token used. Returns the approver's user id."""
    if approval_id is None:
        raise AppError("APPROVAL_REQUIRED", "This needs approval from a manager.", 403, action=action, amount=str(amount) if amount is not None else None)
    approval = ctx.db.get(Approval, approval_id, with_for_update=True)
    if approval is None or approval.branch_id != ctx.branch_id or approval.requested_by != ctx.user_id or approval.action != action:
        raise Forbidden("This approval doesn't match the request.", code="APPROVAL_MISMATCH")
    if approval.status != "Approved" or approval.expires_at < utcnow():
        raise Forbidden("This approval has expired or was already used.", code="APPROVAL_EXPIRED")
    if approval.target_id is not None and target_id is not None and approval.target_id != target_id:
        raise Forbidden("This approval was given for a different record.", code="APPROVAL_MISMATCH")
    if amount is not None and (approval.amount is None or amount > approval.amount):
        raise Forbidden("The amount is higher than what was approved.", code="APPROVAL_MISMATCH")
    approval.status, approval.used_at = "Used", utcnow()
    return approval.approver_id


def requires_approval(ctx: Ctx, limit_key: str, amount: Decimal) -> bool:
    return amount > ctx.limit(limit_key)


# ---------------------------------------------------------------- notifications (NOTIF)
def notify_users(db: Session, user_ids: list[uuid.UUID], branch_id: uuid.UUID | None, kind: str, title: str, body: str, link: str | None = None, data: dict | None = None) -> None:
    from app.services.messages import muted_users

    muted = muted_users(db, list(set(user_ids)), kind)  # optional kinds the person turned off (FR-NOTIF-011)
    for uid in set(user_ids) - muted:
        n = Notification(branch_id=branch_id, recipient_user_id=uid, kind=kind, title=title, body=body, link=link, data=_jsonable(data))
        db.add(n)
        db.flush()
        emit(db, f"user:{uid}", "notification", {"id": str(n.id), "kind": kind, "title": title, "body": body, "link": link})


def users_with_permission(db: Session, branch_id: uuid.UUID, permission: str) -> list[uuid.UUID]:
    q = (select(UserRole.user_id).join(RolePermission, RolePermission.role_id == UserRole.role_id).join(UserBranch, UserBranch.user_id == UserRole.user_id)
         .join(User, User.id == UserRole.user_id).where(RolePermission.permission_code == permission, UserBranch.branch_id == branch_id, User.status == "Active"))
    return list(set(db.scalars(q)))


def notify_permission(db: Session, branch_id: uuid.UUID, permission: str, kind: str, title: str, body: str, link: str | None = None) -> None:
    notify_users(db, users_with_permission(db, branch_id, permission), branch_id, kind, title, body, link)
