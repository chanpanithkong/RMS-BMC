"""Online ordering and QR table ordering (SRS §6.21 ONL; BR-030, BR-038, BR-046, BR-052).

Public requests run as the inactive service account ``online.system`` with a fixed, narrow permission set, inside
the branch the customer chose. Everything a customer sends is re-validated here: availability, channel, prices,
modifiers, quantity limits, opening hours, lead time, minimum order, delivery zone and promotion codes.
"""
import hashlib
import re
import secrets
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import Ctx
from app.core.exceptions import AppError, BusinessRuleError, Conflict, Forbidden, NotFound
from app.integrations.payments import get_gateway
from app.models import Branch, Delivery, Order, OnlineOrder, OutboxEvent, RestaurantTable, TrackingToken, User
from app.services.platform import audit, get_setting, notify_permission
from app.utils.money import ZERO
from app.utils.timeutil import utcnow

SYSTEM_PERMISSIONS = {"orders.view", "orders.view_all", "orders.create", "orders.edit", "orders.cancel", "payments.view", "payments.create", "delivery.view",
                      "menu.view", "tables.view", "tables.operate", "notifications.view"}


# ---------------------------------------------------------------- context and settings
def system_ctx(db: Session, branch: Branch) -> Ctx:
    from app.services.seed import SYSTEM_USERNAME, system_user

    user = db.scalar(select(User).where(User.username == SYSTEM_USERNAME)) or system_user(db)
    return Ctx(db=db, user=user, session_id=uuid.UUID(int=0), branch=branch, permissions=set(SYSTEM_PERMISSIONS), roles={"SYSTEM"})


def public_branch(db: Session, code: str, feature: str = "online") -> tuple[Branch, dict]:
    b = db.scalar(select(Branch).where(Branch.code == code.upper(), Branch.is_active))
    if b is None:
        raise NotFound("Branch")
    s = get_setting(db, feature, b.id)
    if not s.get("enabled"):
        raise Forbidden("Online ordering isn't available at this branch." if feature == "online" else "Table ordering isn't available here.",
                        code="ONLINE_ORDERING_DISABLED" if feature == "online" else "QR_ORDERING_DISABLED")
    return b, s


def _hours(branch: Branch) -> tuple[time, time] | None:
    """Branch.opening_hours as 'HH:MM-HH:MM' (overnight ranges allowed). Empty means no restriction."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", branch.opening_hours or "")
    if not m:
        return None
    a, b = time(int(m[1]) % 24, int(m[2])), time(int(m[3]) % 24, int(m[4]))
    return a, b


def is_open(branch: Branch, at: datetime) -> bool:
    h = _hours(branch)
    if h is None:
        return True
    t = at.astimezone(ZoneInfo(branch.timezone)).time()
    return h[0] <= t < h[1] if h[0] < h[1] else (t >= h[0] or t < h[1])


def check_time(branch: Branch, s: dict, scheduled_at: datetime | None) -> None:
    """FR-ONL-003: ASAP or a scheduled time within opening hours and at least the preparation lead time ahead."""
    now = utcnow()
    if scheduled_at is None:
        if not is_open(branch, now):
            raise BusinessRuleError("BRANCH_CLOSED", f"{branch.name_en} is closed now. Choose a later time.")
        return
    if scheduled_at.tzinfo is None:
        raise BusinessRuleError("VALIDATION_ERROR", "Give the scheduled time with a time zone.", details=[{"field": "scheduled_at", "issue": "timezone required"}])
    if scheduled_at < now + timedelta(minutes=int(s.get("lead_minutes", 20))):
        raise BusinessRuleError("TOO_SOON", f"The earliest time is {int(s.get('lead_minutes', 20))} minutes from now.")
    if scheduled_at > now + timedelta(days=7):
        raise BusinessRuleError("TOO_FAR_AHEAD", "Orders can be scheduled up to 7 days ahead.")
    if not is_open(branch, scheduled_at):
        raise BusinessRuleError("BRANCH_CLOSED", f"{branch.name_en} is closed at that time.")


# ---------------------------------------------------------------- public menu (FR-ONL-001)
def public_menu(ctx: Ctx, channel: str) -> dict:
    from app.api.v1.endpoints.menu import item_out
    from app.models import MenuItem
    from app.services import menu as menu_svc

    s = get_setting(ctx.db, "online", ctx.branch_id)
    list_id = menu_svc.price_list_id(ctx.db, s.get("price_list"), ctx.branch_id)
    channels = ("Online",) if channel == "Online" else ("QR", "Online")
    items = []
    for it in ctx.db.scalars(select(MenuItem).where(MenuItem.restaurant_id == ctx.branch.restaurant_id, MenuItem.is_active).order_by(MenuItem.code)):
        if not set(it.channels or []) & set(channels):
            continue
        out = item_out(ctx, it, list_id)
        if not out["available"] or not any(v["price"] is not None for v in out["variants"]):
            continue
        items.append({k: out[k] for k in ("id", "code", "name_en", "name_km", "description", "category_id", "category_name_en", "image_url", "modifier_groups")}
                     | {"variants": [v for v in out["variants"] if v["is_active"] and v["price"] is not None]})
    b = ctx.branch
    return {"branch": {"code": b.code, "name_en": b.name_en, "name_km": b.name_km, "address": b.address, "phone": b.phone, "opening_hours": b.opening_hours,
                       "open_now": is_open(b, utcnow())},
            "lead_minutes": s.get("lead_minutes"), "min_order": s.get("min_order"), "max_qty_per_line": s.get("max_qty_per_line"), "items": items}


# ---------------------------------------------------------------- checkout (FR-ONL-002..008, FR-ONL-012)
def _cart_limits(s: dict, items: list[dict]) -> None:
    cap = int(s.get("max_qty_per_line", 20))
    for i, it in enumerate(items):
        if Decimal(str(it["quantity"])) > cap:
            raise BusinessRuleError("QUANTITY_LIMIT", f"At most {cap} of an item per order line.", details=[{"field": f"items[{i}].quantity", "issue": f"max {cap}"}])


def _create(ctx: Ctx, data: dict, s: dict) -> Order:
    from app.services import front, orders, promotions

    _cart_limits(s, data["items"])
    phone = front.normalise_phone(data["phone"])
    if not phone:
        raise BusinessRuleError("VALIDATION_ERROR", "Enter a valid phone number.", details=[{"field": "phone", "issue": "invalid"}])
    delivery = None
    if data["fulfilment"] == "Delivery":
        if not data.get("delivery"):
            raise BusinessRuleError("DELIVERY_DETAILS_REQUIRED", "Choose a delivery zone and enter the address.")
        delivery = {k: v for k, v in data["delivery"].items() if k != "fee_override"}  # customers never set the fee
    order = orders.create_order(ctx, {"order_type": "Delivery" if data["fulfilment"] == "Delivery" else "Takeaway", "channel": "Online",
                                      "customer_name": data["name"], "customer_phone": front.national(phone), "pickup_name": data["name"][:60],
                                      "scheduled_at": data.get("scheduled_at"), "note": data.get("note"), "delivery": delivery, "items": data["items"]})
    if data.get("promo_code"):
        promotions.apply_code(ctx, order, data["promo_code"])  # BR-038, server-side (FR-ONL-006)
    calc = orders.calculation(ctx.db, order)
    if Decimal(str(s.get("min_order", "0"))) > calc.subtotal:
        raise BusinessRuleError("MINIMUM_ORDER_NOT_MET", f"The minimum online order is {Decimal(str(s['min_order'])):.2f}.")
    if order.order_type == "Delivery":
        from app.services import delivery as dsvc

        dsvc.check_minimum(ctx, order)
    return order


def totals_out(order: Order) -> dict:
    return {"subtotal": order.subtotal, "discount_total": order.discount_total, "service_charge": order.service_charge_total, "tax": order.tax_total,
            "delivery_fee": order.delivery_fee, "total": order.grand_total, "currency": order.currency}


def quote(db: Session, branch: Branch, s: dict, data: dict) -> dict:
    """Prices the cart exactly as checkout would, then rolls everything back (no order, number or event is kept)."""
    ctx = system_ctx(db, branch)
    check_time(branch, s, data.get("scheduled_at"))
    pending = len(db.info.get("pending_events", []))
    sp = db.begin_nested()
    try:
        order = _create(ctx, data, s)
        out = {"totals": totals_out(order), "lines": [{"name": i.item_name_en_snapshot, "variant": i.variant_name_snapshot, "quantity": i.quantity, "net": i.line_net}
                                                      for i in order.items]}
    finally:
        sp.rollback()
        db.info["pending_events"] = db.info.get("pending_events", [])[:pending]
    return out


def _token(db: Session, order: Order, hours: int) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(TrackingToken(order_id=order.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=utcnow() + timedelta(hours=hours)))
    return raw


def tracking_url(token: str) -> str:
    return f"{get_settings().FRONTEND_URL.split(',')[0].rstrip('/')}/track/{token}"


def checkout(db: Session, branch: Branch, s: dict, data: dict) -> dict:
    ctx = system_ctx(db, branch)
    if s.get("paused"):
        raise Conflict("ONLINE_ORDERING_PAUSED", "Online ordering is paused at the moment. Please try again later.")
    check_time(branch, s, data.get("scheduled_at"))
    gateway = None
    if data["payment"] == "Online":
        gateway = get_gateway()
        if gateway is None:
            raise BusinessRuleError("ONLINE_PAYMENT_UNAVAILABLE", "Online payment isn't available. Choose pay at pickup or on delivery.")
    elif not s.get("pay_later_allowed", True):
        raise BusinessRuleError("ONLINE_PAYMENT_REQUIRED", "This branch only takes orders paid online.")
    order = _create(ctx, data, s)
    if data.get("expected_total") is not None and Decimal(str(data["expected_total"])) != order.grand_total:
        # BR-046: prices changed between cart and checkout; nothing is kept and the customer confirms the new total.
        raise AppError("PRICE_CHANGED", "Prices have changed. Please review the new total.", 409, current_total=str(order.grand_total))
    oo = OnlineOrder(order_id=order.id, branch_id=branch.id, source="Online", fulfilment=data["fulfilment"], customer_email=data.get("email"),
                     payment_mode=data["payment"], payment_status="Pending" if gateway else "NotRequired")
    out: dict = {}
    if gateway:
        co = gateway.create_checkout(order.order_no, order.grand_total, order.currency)
        oo.gateway, oo.gateway_session = gateway.name, co.session_ref
        out["payment"] = {"gateway": gateway.name, "session_ref": co.session_ref, "redirect_url": co.redirect_url}
    db.add(oo)
    db.flush()
    token = _token(db, order, int(s.get("tracking_hours", 24)))
    audit(db, ctx, "online.order_received", "Order", order.id, after={"fulfilment": oo.fulfilment, "payment": oo.payment_mode, "total": order.grand_total})
    notify_permission(db, branch.id, "orders.edit", "Online", f"New online order {order.order_no}", f"{oo.fulfilment}, {order.grand_total:.2f} {order.currency}",
                      f"/orders/{order.id}")
    if s.get("auto_accept") and oo.payment_status == "NotRequired":
        _accept(ctx, oo, order)
    _confirm(db, branch, order, oo, token)
    return {"order_id": order.id, "order_no": order.order_no, "status": tracking_status(db, order, oo), "tracking_token": token, "tracking_url": tracking_url(token),
            "totals": totals_out(order), **out}


def _confirm(db: Session, branch: Branch, order: Order, oo: OnlineOrder, token: str) -> None:
    """FR-ONL-008: confirmation by email when given. SMS needs a messaging provider (not integrated)."""
    if oo.customer_email:
        db.add(OutboxEvent(branch_id=branch.id, event_type="email.online_order_confirmation", topic="email",
                           payload={"email": oo.customer_email, "order_no": order.order_no, "branch": branch.name_en, "total": str(order.grand_total),
                                    "currency": order.currency, "fulfilment": oo.fulfilment, "tracking_url": tracking_url(token)}))


# ---------------------------------------------------------------- payment callback (FR-ONL-007)
def payment_callback(db: Session, provider: str, body: bytes, signature: str | None) -> dict:
    from app.services import billing

    gateway = get_gateway(provider)
    if gateway is None:
        raise NotFound("Payment provider")
    payload = gateway.verify(body, signature)
    if payload is None:
        raise Forbidden("The payment notification signature is invalid.", code="SIGNATURE_INVALID")
    oo = db.scalar(select(OnlineOrder).where(OnlineOrder.gateway_session == payload.get("session_ref")).with_for_update())
    if oo is None:
        raise NotFound("Payment session")
    if oo.payment_status == "Paid":
        return {"status": "already_recorded"}  # gateways retry; at most one payment per session (BR-030)
    order = db.get(Order, oo.order_id, with_for_update=True)
    ctx = system_ctx(db, db.get(Branch, oo.branch_id))
    if payload.get("status") != "paid":
        oo.payment_status = "Failed"
        audit(db, ctx, "online.payment_failed", "Order", order.id, after={"session": oo.gateway_session})
        return {"status": "failed_recorded"}
    amount = Decimal(str(payload.get("amount")))
    if amount != order.grand_total or payload.get("currency") != order.currency:
        audit(db, ctx, "online.payment_mismatch", "Order", order.id, after={"expected": order.grand_total, "received": amount})
        raise Conflict("PAYMENT_AMOUNT_MISMATCH", "The paid amount doesn't match the order total.")
    bills = billing.active_bills(db, order.id) or billing.generate_bills(ctx, order, "single")
    billing.create_payment(ctx, {"bill_id": bills[0].id, "method": "ONLINE", "currency": order.currency, "reference": str(payload.get("gateway_txn"))[:80],
                                 "idempotency_key": f"gateway:{oo.gateway_session}"})
    oo.payment_status, oo.gateway_txn = "Paid", str(payload.get("gateway_txn"))[:80]
    audit(db, ctx, "online.payment_confirmed", "Order", order.id, after={"gateway": oo.gateway, "txn": oo.gateway_txn, "amount": amount})
    if get_setting(db, "online", oo.branch_id).get("auto_accept") and oo.status == "Received":
        _accept(ctx, oo, order)
    return {"status": "recorded"}


# ---------------------------------------------------------------- staff side (FR-ONL-011, FR-ONL-014)
def get_online(ctx: Ctx, online_id: uuid.UUID) -> OnlineOrder:
    oo = ctx.db.scalar(select(OnlineOrder).where(OnlineOrder.id == online_id, OnlineOrder.branch_id == ctx.branch_id).with_for_update())
    if oo is None:
        raise NotFound("Online order")
    return oo


def _accept(ctx: Ctx, oo: OnlineOrder, order: Order) -> None:
    from app.services import orders

    oo.status, oo.accepted_by, oo.accepted_at = "Accepted", ctx.user_id, utcnow()
    ctx.db.flush()
    orders.send(ctx, order)
    audit(ctx.db, ctx, "online.order_accept", "Order", order.id, after={"auto": ctx.user.username == "online.system"})


def accept(ctx: Ctx, oo: OnlineOrder) -> OnlineOrder:
    ctx.require("orders.edit")
    if oo.status != "Received":
        raise Conflict("ONLINE_ORDER_DECIDED", f"This order is already {oo.status.lower()}.")
    if oo.payment_status in ("Pending", "Failed"):
        raise Conflict("PAYMENT_PENDING", "Wait for the online payment before accepting.")
    _accept(ctx, oo, ctx.db.get(Order, oo.order_id, with_for_update=True))
    return oo


def reject(ctx: Ctx, oo: OnlineOrder, reason: str) -> OnlineOrder:
    """Rejecting cancels the order; an order paid online must be refunded first through the refund flow (BR-012)."""
    from app.services import orders

    ctx.require("orders.cancel")
    if oo.status != "Received":
        raise Conflict("ONLINE_ORDER_DECIDED", f"This order is already {oo.status.lower()}.")
    order = ctx.db.get(Order, oo.order_id, with_for_update=True)
    orders.cancel_order(ctx, order, f"Online order rejected: {reason}", None)
    oo.status, oo.reject_reason = "Rejected", reason
    if oo.customer_email:
        ctx.db.add(OutboxEvent(branch_id=ctx.branch_id, event_type="email.online_order_rejected", topic="email",
                               payload={"email": oo.customer_email, "order_no": order.order_no, "branch": ctx.branch.name_en, "reason": reason}))
    audit(ctx.db, ctx, "online.order_reject", "Order", order.id, reason=reason)
    return oo


def set_paused(ctx: Ctx, paused: bool) -> dict:
    from app.models import Setting

    ctx.require("settings.manage")
    row = ctx.db.scalar(select(Setting).where(Setting.key == "online", Setting.branch_id == ctx.branch_id).with_for_update())
    if row is None:
        row = Setting(branch_id=ctx.branch_id, key="online", value={}, updated_by=ctx.user_id)
        ctx.db.add(row)
    before = dict(row.value or {})
    row.value = {**before, "paused": paused}
    row.updated_by = ctx.user_id
    ctx.db.flush()
    audit(ctx.db, ctx, "online.pause" if paused else "online.resume", "Setting", "online", before={"paused": before.get("paused", False)}, after={"paused": paused})
    return get_setting(ctx.db, "online", ctx.branch_id)


# ---------------------------------------------------------------- tracking (FR-ONL-009)
def tracking_status(db: Session, order: Order, oo: OnlineOrder | None) -> str:
    if oo is not None and oo.status == "Rejected":
        return "Rejected"
    if order.order_status == "Cancelled":
        return "Cancelled"
    if order.order_status == "Completed":
        return "Completed"
    if oo is not None and oo.status == "Received":
        return "Received"
    d = db.scalar(select(Delivery).where(Delivery.order_id == order.id))
    if d is not None and d.status == "OutForDelivery":
        return "Out for Delivery"
    if order.kitchen_status in ("Ready", "Served"):
        return "Ready"
    if order.kitchen_status == "InProgress":
        return "Preparing"
    return "Accepted"


def track(db: Session, token: str) -> dict:
    row = db.scalar(select(TrackingToken).where(TrackingToken.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if row is None or row.expires_at < utcnow():
        raise NotFound("Order")  # unknown and expired links look the same
    order = db.get(Order, row.order_id)
    oo = db.scalar(select(OnlineOrder).where(OnlineOrder.order_id == order.id))
    b = db.get(Branch, order.branch_id)
    return {"order_no": order.order_no, "status": tracking_status(db, order, oo), "fulfilment": oo.fulfilment if oo else None, "scheduled_at": order.scheduled_at,
            "branch": {"name_en": b.name_en, "name_km": b.name_km, "phone": b.phone},
            "items": [{"name": i.item_name_en_snapshot, "variant": i.variant_name_snapshot, "quantity": i.quantity, "status": i.item_status}
                      for i in order.items if i.item_status != "Cancelled"],
            "totals": totals_out(order), "payment_status": oo.payment_status if oo else None, "reject_reason": oo.reject_reason if oo else None,
            "expires_at": row.expires_at}


# ---------------------------------------------------------------- QR table ordering (FR-ONL-013)
def issue_qr(ctx: Ctx, table: RestaurantTable) -> str:
    ctx.require("tables.manage")
    raw = secrets.token_urlsafe(24)
    table.qr_token_hash = hashlib.sha256(raw.encode()).hexdigest()  # rotating invalidates the printed code
    audit(ctx.db, ctx, "table.qr_issue", "RestaurantTable", table.id, after={"table": table.table_code})
    return raw


def qr_table(db: Session, token: str) -> tuple[RestaurantTable, Branch, dict]:
    t = db.scalar(select(RestaurantTable).where(RestaurantTable.qr_token_hash == hashlib.sha256(token.encode()).hexdigest(), RestaurantTable.is_active))
    if t is None:
        raise NotFound("Table")
    branch, s = public_branch(db, db.get(Branch, t.branch_id).code, "qr")
    if t.is_out_of_service:
        raise Conflict("TABLE_OUT_OF_SERVICE", "This table isn't in service. Please ask a member of staff.")
    return t, branch, s


def qr_order(db: Session, token: str, data: dict) -> dict:
    """Creates a dine-in order for the table, or adds to its open order. Staff confirm before the kitchen sees it unless configured otherwise."""
    from app.services import orders

    table, branch, s = qr_table(db, token)
    ctx = system_ctx(db, branch)
    online_s = get_setting(db, "online", branch.id)
    _cart_limits(online_s, data["items"])
    if not is_open(branch, utcnow()):
        raise BusinessRuleError("BRANCH_CLOSED", f"{branch.name_en} is closed now.")
    order = db.scalar(select(Order).where(Order.table_id == table.id, Order.order_status.in_(("Draft", "Open"))).order_by(Order.created_at.desc()).with_for_update())
    if order is None:
        order = orders.create_order(ctx, {"order_type": "DineIn", "channel": "QR", "table_id": table.id, "guest_count": data.get("guest_count") or 1,
                                          "note": data.get("note"), "items": data["items"]})
        db.add(OnlineOrder(order_id=order.id, branch_id=branch.id, source="QR", fulfilment="DineIn", payment_mode="PayLater", payment_status="NotRequired",
                           status="Received" if s.get("require_staff_confirmation", True) else "Accepted"))
    else:
        orders.check_version(order, None)
        for it in data["items"]:
            orders.add_item(ctx, order, it)
        orders.recalc(ctx, order)
        orders.log_event(ctx, order, "qr_items_added", {"lines": len(data["items"])})
    db.flush()
    if s.get("require_staff_confirmation", True):
        notify_permission(db, branch.id, "orders.edit", "QR", f"Table {table.table_code}: new items to confirm", f"Order {order.order_no}", f"/orders/{order.id}")
        state = "WaitingForStaff"
    else:
        orders.send(ctx, order)
        state = "SentToKitchen"
    token_out = _token(db, order, int(online_s.get("tracking_hours", 24)))
    audit(db, ctx, "online.qr_order", "Order", order.id, after={"table": table.table_code, "lines": len(data["items"]), "state": state})
    return {"order_id": order.id, "order_no": order.order_no, "table": table.table_code, "state": state, "tracking_token": token_out,
            "tracking_url": tracking_url(token_out), "totals": totals_out(order)}
