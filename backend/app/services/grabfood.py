"""GrabFood order import (owner's choice for D-13: GrabFood, staff accept each order).

Grab -> RMS (partner endpoints, GrabFood Partner API v1.1.3):
* POST .../oauth/token: Grab exchanges the client ID/secret we issued for a bearer token (client_credentials).
* POST .../orders (Submit order webhook): the order. Item `id` and modifier `id` are the partner's external IDs:
  RMS variant/modifier UUIDs, or codes mapped in platform_item_maps. Prices arrive in minor units (Cambodia: KHR, exponent 2).
* PUT .../order/state (Push order state webhook): ACCEPTED, DRIVER_ALLOCATED, DRIVER_ARRIVED, COLLECTED, DELIVERED, FAILED, CANCELLED...
RMS -> Grab (queued in the outbox, sent by the worker with retries): accept/reject for MANUAL orders, mark ready.

RMS prices come from the RMS menu (server-side, BR-008). Grab's own total is stored and compared; a difference is flagged
for the manager. Payment is recorded with the PLATFORM method when the order is accepted (Grab settles later), so the
pay-first rule for takeaway is met and the kitchen gets the order.
"""
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import Ctx
from app.core.exceptions import AppError, Conflict, NotFound, Unauthorized
from app.models import Branch, Modifier, Order, OutboxEvent, PlatformInbound, PlatformItemMap, PlatformOrder
from app.services.platform import audit, get_setting, notify_permission
from app.utils.money import q
from app.utils.timeutil import utcnow

PLATFORM = "GrabFood"
AUDIENCE = "grabfood-webhook"
TOKEN_SECONDS = 7 * 24 * 3600


# ---------------------------------------------------------------- Grab -> RMS authentication
def issue_token(client_id: str, client_secret: str, grant_type: str) -> dict:
    s = get_settings()
    if not (s.GRABFOOD_PARTNER_CLIENT_ID and s.GRABFOOD_PARTNER_CLIENT_SECRET):
        raise Unauthorized("GrabFood integration isn't configured.", code="INTEGRATION_DISABLED")
    ok = secrets.compare_digest(client_id or "", s.GRABFOOD_PARTNER_CLIENT_ID) & secrets.compare_digest(client_secret or "", s.GRABFOOD_PARTNER_CLIENT_SECRET)
    if not ok or grant_type != "client_credentials":
        raise Unauthorized("Invalid client credentials.", code="INVALID_CLIENT")
    now = utcnow()
    token = jwt.encode({"sub": PLATFORM, "aud": AUDIENCE, "scope": "food.partner_api", "iat": now, "exp": now + timedelta(seconds=TOKEN_SECONDS)},
                       s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)
    return {"access_token": token, "token_type": "Bearer", "expires_in": TOKEN_SECONDS}


def verify_bearer(authorization: str | None) -> None:
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Missing bearer token.", code="TOKEN_MISSING")
    try:
        jwt.decode(authorization[7:], s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM], audience=AUDIENCE)
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid or expired token.", code="TOKEN_INVALID")  # Grab requests a new token on 401


# ---------------------------------------------------------------- helpers
def _log(db: Session, kind: str, payload: dict, outcome: str, branch_id=None, detail: str | None = None) -> None:
    db.add(PlatformInbound(platform=PLATFORM, kind=kind, external_order_id=str(payload.get("orderID") or "")[:80] or None, branch_id=branch_id,
                           payload=payload, outcome=outcome, detail=detail))


def branch_for(db: Session, merchant_id: str | None) -> Branch | None:
    if not merchant_id:
        return None
    for b in db.scalars(select(Branch).where(Branch.is_active)):
        s = get_setting(db, "grabfood", b.id)
        if s.get("enabled") and s.get("merchant_id") == merchant_id:
            return b
    return None


def _ctx(db: Session, branch: Branch) -> Ctx:
    from app.services.online import SYSTEM_PERMISSIONS, system_ctx

    return system_ctx(db, branch, SYSTEM_PERMISSIONS | {"delivery.manage", "delivery.view", "payments.create"})


def _variant_for(db: Session, external_id: str):
    m = db.scalar(select(PlatformItemMap).where(PlatformItemMap.platform == PLATFORM, PlatformItemMap.external_id == external_id))
    if m is not None:
        return m.variant_id
    from app.models import MenuItemVariant

    try:
        v = db.get(MenuItemVariant, uuid.UUID(external_id))
    except ValueError:
        return None
    return v.id if v is not None else None


def _modifier_for(db: Session, external_id: str):
    m = db.scalar(select(PlatformItemMap).where(PlatformItemMap.platform == PLATFORM, PlatformItemMap.external_id == external_id))
    if m is not None:
        return m.modifier_id
    try:
        md = db.get(Modifier, uuid.UUID(external_id))
    except ValueError:
        return None
    return md.id if md is not None else None


def _items(db: Session, payload: dict) -> tuple[list[dict], list[str]]:
    lines, unknown = [], []
    for it in payload.get("items") or []:
        variant = _variant_for(db, str(it.get("id", "")))
        if variant is None:
            unknown.append(f"item {it.get('id')}")
            continue
        mods = []
        for md in it.get("modifiers") or []:
            mid = _modifier_for(db, str(md.get("id", "")))
            if mid is None:
                unknown.append(f"modifier {md.get('id')}")
            else:
                mods.append({"modifier_id": mid})
        lines.append({"variant_id": variant, "quantity": str(int(it.get("quantity") or 1)), "modifiers": mods, "note": (it.get("specifications") or None)})
    return lines, unknown


def _platform_total_usd(db: Session, minor: int | None, currency: dict) -> Decimal | None:
    if minor is None:
        return None
    major = Decimal(minor) / (Decimal(10) ** int(currency.get("exponent", 2)))
    if currency.get("code") == "USD":
        return major
    from app.services.billing import current_rate

    rate = current_rate(db, currency.get("code", "KHR"))
    return q(major / rate.rate) if rate else None


def _queue(db: Session, branch_id, event_type: str, payload: dict) -> None:
    db.add(OutboxEvent(branch_id=branch_id, event_type=event_type, topic="grabfood", payload=payload))


# ---------------------------------------------------------------- Submit order webhook
def submit_order(db: Session, payload: dict) -> dict:
    from app.services import delivery, orders

    order_ref = payload.get("orderID")
    if not order_ref or not isinstance(payload.get("items"), list):
        _log(db, "submit_order", payload, "invalid")
        raise AppError("INVALID_ORDER", "orderID and items are required.", 400)
    branch = branch_for(db, payload.get("merchantID"))
    if branch is None:
        _log(db, "submit_order", payload, "unknown_merchant")
        raise NotFound("Merchant")  # Grab sees the failure; nothing is silently dropped
    existing = db.scalar(select(PlatformOrder).where(PlatformOrder.platform == PLATFORM, PlatformOrder.platform_ref == order_ref).with_for_update())
    flags = payload.get("featureFlags") or {}
    if existing is not None:
        if not flags.get("isMexEditOrder"):
            _log(db, "submit_order", payload, "duplicate", branch.id)
            return {"status": "duplicate"}
        _log(db, "submit_order", payload, "edited", branch.id)
        order = db.get(Order, existing.order_id)
        notify_permission(db, branch.id, "orders.edit", "GrabFood", f"Grab order {existing.platform_short_no} was edited",
                          f"Check RMS order {order.order_no} against the Grab merchant app.", f"/orders/{order.id}")
        return {"status": "edit_flagged"}
    ctx = _ctx(db, branch)
    lines, unknown = _items(db, payload)
    short_no = str(payload.get("shortOrderNumber") or order_ref)[:30]
    if unknown or not lines:
        _log(db, "submit_order", payload, "unmapped", branch.id, ", ".join(unknown)[:500])
        notify_permission(db, branch.id, "orders.edit", "GrabFood", f"Grab order {short_no} needs manual entry",
                          f"Unknown menu IDs: {', '.join(unknown)[:200]}. Enter it as a platform order and map the IDs.", "/platform-orders")
        return {"status": "needs_manual_entry"}
    receiver = payload.get("receiver") or {}
    order = orders.create_order(ctx, {"order_type": "Takeaway", "channel": "Platform", "pickup_name": f"Grab {short_no}"[:60],
                                      "customer_name": (receiver.get("name") or None), "note": "Cutlery" if payload.get("cutlery") else None, "items": lines})
    rate = get_setting(db, "grabfood", branch.id).get("commission_rate")
    po = delivery.record_platform_order(ctx, order, PLATFORM, order_ref, Decimal(str(rate)) if rate is not None else None, None if rate is not None else Decimal("0"))
    price, currency = payload.get("price") or {}, payload.get("currency") or {}
    mode = flags.get("orderAcceptedType") or "MANUAL"
    po.accept_mode, po.acceptance, po.platform_short_no, po.payment_type = mode, "Received", short_no, payload.get("paymentType")
    po.platform_total_minor = price.get("total") if price.get("total") is not None else price.get("subtotal")
    po.platform_currency, po.platform_exponent = currency.get("code"), currency.get("exponent")
    grab_usd = _platform_total_usd(db, po.platform_total_minor, currency)
    if grab_usd is not None and abs(grab_usd - order.grand_total) > max(Decimal("0.05"), order.grand_total * Decimal("0.01")):
        po.mismatch_note = f"Grab total {grab_usd} USD vs RMS {order.grand_total} USD"
        notify_permission(db, branch.id, "delivery.manage", "GrabFood", f"Price difference on Grab order {short_no}", po.mismatch_note, f"/orders/{order.id}")
    _log(db, "submit_order", payload, "imported", branch.id)
    audit(db, ctx, "grabfood.order_imported", "Order", order.id, after={"grab_order": order_ref, "short_no": short_no, "mode": mode})
    if mode == "AUTO":
        _accept(ctx, po, order, tell_grab=False)  # Grab already accepted it
    else:
        notify_permission(db, branch.id, "orders.edit", "GrabFood", f"New Grab order {short_no}: accept within 5 minutes",
                          f"{len(lines)} line(s), {order.grand_total:.2f} USD", f"/orders/{order.id}")
    return {"status": "received", "order_no": order.order_no}


# ---------------------------------------------------------------- staff accept / reject (owner's choice)
def get_po(ctx: Ctx, order_id: uuid.UUID) -> PlatformOrder:
    po = ctx.db.scalar(select(PlatformOrder).where(PlatformOrder.order_id == order_id, PlatformOrder.branch_id == ctx.branch_id).with_for_update())
    if po is None:
        raise NotFound("Platform order")
    return po


def _accept(ctx: Ctx, po: PlatformOrder, order: Order, tell_grab: bool) -> None:
    from app.services import billing, orders

    bills = billing.active_bills(ctx.db, order.id) or billing.generate_bills(ctx, order, "single")
    if bills[0].status != "Paid":
        billing.create_payment(ctx, {"bill_id": bills[0].id, "method": "PLATFORM", "currency": "USD", "reference": po.platform_ref[:80],
                                     "idempotency_key": f"grab:{po.platform_ref}"[:80]})
    po.acceptance = "Accepted"
    orders.send(ctx, order)
    if tell_grab:
        _queue(ctx.db, ctx.branch_id, "grabfood.order_state", {"orderID": po.platform_ref, "toState": "Accepted"})
    audit(ctx.db, ctx, "grabfood.order_accept", "Order", order.id, after={"grab_order": po.platform_ref, "auto": not tell_grab})


def accept(ctx: Ctx, po: PlatformOrder) -> PlatformOrder:
    ctx.require("orders.edit")
    if po.acceptance != "Received":
        raise Conflict("PLATFORM_ORDER_DECIDED", f"This order is already {po.acceptance.lower()}.")
    _accept(ctx, po, ctx.db.get(Order, po.order_id, with_for_update=True), tell_grab=po.platform == PLATFORM and po.accept_mode == "MANUAL")
    return po


def reject(ctx: Ctx, po: PlatformOrder, reason: str) -> PlatformOrder:
    from app.services import orders

    ctx.require("orders.cancel")
    if po.acceptance != "Received":
        raise Conflict("PLATFORM_ORDER_DECIDED", f"This order is already {po.acceptance.lower()}.")
    order = ctx.db.get(Order, po.order_id, with_for_update=True)
    orders.cancel_order(ctx, order, f"Grab order rejected: {reason}", None)
    po.acceptance = "Rejected"
    if po.platform == PLATFORM and po.accept_mode == "MANUAL":
        _queue(ctx.db, ctx.branch_id, "grabfood.order_state", {"orderID": po.platform_ref, "toState": "Rejected"})
    audit(ctx.db, ctx, "grabfood.order_reject", "Order", order.id, reason=reason)
    return po


def on_ready(db: Session, order: Order) -> None:
    """Called when the kitchen finishes an order: tell Grab once so the driver isn't kept waiting."""
    po = db.scalar(select(PlatformOrder).where(PlatformOrder.order_id == order.id, PlatformOrder.platform == PLATFORM))
    if po is not None and po.acceptance == "Accepted" and po.ready_marked_at is None:
        po.ready_marked_at = utcnow()
        _queue(db, order.branch_id, "grabfood.mark_ready", {"orderID": po.platform_ref})


# ---------------------------------------------------------------- Push order state webhook
def push_state(db: Session, payload: dict) -> dict:
    from app.services import orders

    po = db.scalar(select(PlatformOrder).where(PlatformOrder.platform == PLATFORM, PlatformOrder.platform_ref == payload.get("orderID")).with_for_update())
    if po is None:
        _log(db, "order_state", payload, "unknown_order")
        return {"status": "unknown_order"}  # e.g. an order that needed manual entry; logged for the manager
    state = str(payload.get("state") or "")[:20]
    po.external_state = state
    order = db.get(Order, po.order_id, with_for_update=True)
    branch = db.get(Branch, po.branch_id)
    ctx = _ctx(db, branch)
    outcome = "recorded"
    if state in ("COLLECTED", "DELIVERED") and order.order_status == "Open":
        orders.serve(ctx, order, None)  # handed to the driver: items Collected, order completes (already paid by PLATFORM)
        outcome = "collected"
    elif state in ("CANCELLED", "FAILED") and order.order_status not in ("Cancelled", "Completed"):
        notify_permission(db, branch.id, "orders.cancel", "GrabFood", f"Grab {state.lower()} order {po.platform_short_no}",
                          f"{payload.get('message') or ''} Cancel RMS order {order.order_no}, refund the platform payment and record any wastage.".strip(),
                          f"/orders/{order.id}")
        outcome = "manager_notified"
    _log(db, "order_state", payload, outcome, branch.id)
    audit(db, ctx, "grabfood.order_state", "Order", order.id, after={"state": state, "code": payload.get("code")})
    return {"status": outcome}


# ---------------------------------------------------------------- menu sync (Get menu webhook, notifications, availability)
GRAB_CURRENCY = {"code": "KHR", "symbol": "៛", "exponent": 2}  # Grab's default for Cambodia (exponent 2)


def _external_id(db: Session, variant_id=None, modifier_id=None) -> str:
    """The ID Grab sees: a mapped code when one exists, otherwise the RMS UUID (orders map back the same way)."""
    col = PlatformItemMap.variant_id if variant_id else PlatformItemMap.modifier_id
    code = db.scalar(select(PlatformItemMap.external_id).where(PlatformItemMap.platform == PLATFORM, col == (variant_id or modifier_id)).limit(1))
    return code or str(variant_id or modifier_id)


def _khr_minor(db: Session, branch: Branch, usd: Decimal, tax_rate: Decimal) -> int:
    """Grab menu prices are tax-inclusive, in KHR minor units: RMS USD price plus exclusive takeaway tax, at today's rate, rounded to the KHR increment."""
    from app.services.billing import current_rate

    rate = current_rate(db, "KHR")
    if rate is None:
        raise Conflict("EXCHANGE_RATE_MISSING", "Enter today's KHR rate before syncing the Grab menu.")
    inc = Decimal(str(get_setting(db, "billing", branch.id).get("khr_rounding_increment", "100")))
    khr = (usd * (1 + tax_rate) * rate.rate / inc).quantize(Decimal("1")) * inc
    return int(khr * 100)


def _takeaway_tax(db: Session, profile_id) -> Decimal:
    from app.services.orders import charge_rules

    rules = charge_rules(db, {profile_id}).get(profile_id, [])
    return sum((r.rate for r in rules if r.charge_kind == "Tax" and not r.inclusive and "Takeaway" in r.order_types), Decimal(0))


def _service_hours(branch: Branch) -> dict:
    from app.services.online import _hours as parse

    h = parse(branch)
    if h is None:
        day = {"openPeriodType": "OpenAllDay"}
    else:
        day = {"openPeriodType": "OpenPeriod", "periods": [{"startTime": h[0].strftime("%H:%M"), "endTime": h[1].strftime("%H:%M")}]}
    return {d: day for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


def _item_name(it, v, khmer: bool) -> str:
    base = (it.name_km or it.name_en) if khmer else it.name_en
    if v.name_en == "Regular":
        return base[:80]
    vname = (v.name_km or v.name_en) if khmer else v.name_en
    return f"{base} ({vname})"[:80]


def build_menu(db: Session, branch: Branch, merchant_id: str | None) -> dict:
    """Get menu webhook response (Item Selling Time structure): sellingTimes, categories, items, modifierGroups, modifiers.
    Cambodia's default Grab menu language is Khmer, so names are Khmer where RMS has them, with English as the translation."""
    from app.models import MenuCategory, MenuItem
    from app.services import menu as menu_svc

    s = get_setting(db, "grabfood", branch.id)
    channel = s.get("menu_channel") or "Online"
    list_id = menu_svc.price_list_id(db, get_setting(db, "online", branch.id).get("price_list"), branch.id)
    selling = {"id": "rms-opening-hours", "name": "Opening hours", "startTime": "2024-01-01 00:00:00", "endTime": "2099-12-31 23:59:59",
               "serviceHours": _service_hours(branch)}
    cats = []
    categories = db.scalars(select(MenuCategory).where(MenuCategory.restaurant_id == branch.restaurant_id, MenuCategory.is_active)
                            .order_by(MenuCategory.sort_order, MenuCategory.name_en)).all()
    for ci, cat in enumerate(categories, 1):
        items = []
        for it in db.scalars(select(MenuItem).where(MenuItem.category_id == cat.id, MenuItem.is_active).order_by(MenuItem.code)):
            if channel not in (it.channels or []):
                continue
            reason = menu_svc.availability(db, branch.id, it)
            if reason == "not sold at this branch":
                continue
            tax = _takeaway_tax(db, it.tax_profile_id)
            groups = []
            for gi, g in enumerate(menu_svc.item_groups(db, it.id), 1):
                mods = []
                for mi, md in enumerate([x for x in g.modifiers if x.is_active], 1):
                    mods.append({"id": _external_id(db, modifier_id=md.id), "name": (md.name_km or md.name_en)[:40], "sequence": mi,
                                 "nameTranslation": {"en": md.name_en[:40]}, "availableStatus": "AVAILABLE",
                                 "price": _khr_minor(db, branch, md.price_delta, tax) if md.price_delta else 0})
                if mods:
                    groups.append({"id": str(g.id), "name": (g.name_km or g.name_en)[:50], "sequence": gi, "nameTranslation": {"en": g.name_en[:50]},
                                   "availableStatus": "AVAILABLE", "selectionRangeMin": g.min_select, "selectionRangeMax": g.max_select, "modifiers": mods[:100]})
            for v in [x for x in it.variants if x.is_active]:
                p = menu_svc.current_price(db, v.id, branch.id, list_id)
                if p is None:
                    continue
                entry = {"id": _external_id(db, variant_id=v.id), "name": _item_name(it, v, True), "sequence": len(items) + 1,
                         "nameTranslation": {"en": _item_name(it, v, False)}, "availableStatus": "AVAILABLE" if reason is None else "UNAVAILABLE",
                         "description": (it.description or "")[:300], "price": _khr_minor(db, branch, p.price, tax),
                         "photos": [it.image_url] if it.image_url else [], "barcode": it.barcode or "", "modifierGroups": groups[:30]}
                if reason is not None:
                    entry["maxStock"] = 0
                items.append(entry)
        if items:
            cats.append({"id": str(cat.id), "name": (cat.name_km or cat.name_en)[:60], "sequence": ci, "nameTranslation": {"en": cat.name_en[:60]},
                         "availableStatus": "AVAILABLE", "sellingTimeID": selling["id"], "items": items[:300]})
    return {"merchantID": merchant_id or s.get("merchant_id"), "partnerMerchantID": branch.code, "currency": GRAB_CURRENCY, "sellingTimes": [selling],
            "categories": cats[:100]}


def get_menu(db: Session, merchant_id: str | None, partner_merchant_id: str | None) -> dict:
    """Grab asks for the branch's menu. During activation the Grab merchant ID first appears here, so it is stored for the branch."""
    from app.models import Setting

    if partner_merchant_id:
        branch = db.scalar(select(Branch).where(Branch.code == partner_merchant_id.upper(), Branch.is_active))
    else:
        branch = branch_for(db, merchant_id)
    if branch is None or not get_setting(db, "grabfood", branch.id).get("enabled"):
        raise NotFound("Merchant")
    s = get_setting(db, "grabfood", branch.id)
    if merchant_id and not s.get("merchant_id"):
        row = db.scalar(select(Setting).where(Setting.key == "grabfood", Setting.branch_id == branch.id).with_for_update())
        if row is not None:
            row.value = {**row.value, "merchant_id": merchant_id}
        _log(db, "get_menu", {"merchantID": merchant_id, "partnerMerchantID": partner_merchant_id}, "merchant_id_stored", branch.id)
    return build_menu(db, branch, merchant_id)


def menu_sync_state(db: Session, payload: dict) -> dict:
    """At-least-once delivery: a repeated requestID is ignored. A FAILED sync alerts the menu managers with Grab's errors."""
    req = payload.get("requestID")
    if req and db.scalar(select(PlatformInbound.id).where(PlatformInbound.platform == PLATFORM, PlatformInbound.kind == "menu_sync_state",
                                                          PlatformInbound.payload["requestID"].astext == req)):
        return {"status": "duplicate"}
    branch = branch_for(db, payload.get("merchantID"))
    status = str(payload.get("status") or "")
    if status == "FAILED" and branch is not None:
        errs = "; ".join(str(e) for e in (payload.get("errors") or []) if e)[:300]
        notify_permission(db, branch.id, "menu.manage", "GrabFood", "Grab menu sync failed", errs or "No details from Grab.", "/menu")
    _log(db, "menu_sync_state", payload, status.lower() or "unknown", branch.id if branch else None)
    return {"status": "recorded"}


def integration_status(db: Session, payload: dict) -> None:
    branch = db.scalar(select(Branch).where(Branch.code == str(payload.get("partnerMerchantID") or "").upper()))
    st = str(payload.get("integrationStatus") or "")
    if branch is not None and st in ("FAILED", "INACTIVE"):
        notify_permission(db, branch.id, "menu.manage", "GrabFood", f"Grab integration {st.lower()}", f"Grab merchant {payload.get('grabMerchantID')}", "/settings")
    _log(db, "integration_status", payload, st.lower() or "unknown", branch.id if branch else None)


def request_full_sync(ctx: Ctx) -> dict:
    """Ask Grab to pull the whole menu (Grab recommends at most once a day, off-peak)."""
    s = get_setting(ctx.db, "grabfood", ctx.branch_id)
    if not s.get("enabled") or not s.get("merchant_id"):
        raise Conflict("GRABFOOD_NOT_LINKED", "Link this branch to its Grab merchant ID first.")
    build_menu(ctx.db, ctx.branch, s["merchant_id"])  # fail here (e.g. missing exchange rate) rather than when Grab calls
    _queue(ctx.db, ctx.branch_id, "grabfood.menu_notification", {"merchantID": s["merchant_id"]})
    audit(ctx.db, ctx, "grabfood.menu_sync_requested", "Branch", ctx.branch_id, after={"merchant_id": s["merchant_id"]})
    return {"queued": True}


def on_availability(ctx: Ctx, item, available: bool) -> None:
    """86 / back in stock: update Grab right away (Update menu record) instead of a full sync."""
    s = get_setting(ctx.db, "grabfood", ctx.branch_id)
    if not s.get("enabled") or not s.get("merchant_id") or (s.get("menu_channel") or "Online") not in (item.channels or []):
        return
    for v in item.variants:
        # Grab: UNAVAILABLE needs maxStock 0, and an item becomes AVAILABLE again when maxStock > 0 (9999999 is the documented maximum)
        _queue(ctx.db, ctx.branch_id, "grabfood.menu_record", {"merchantID": s["merchant_id"], "field": "ITEM", "id": _external_id(ctx.db, variant_id=v.id),
                                                               "availableStatus": "AVAILABLE" if available else "UNAVAILABLE",
                                                               "maxStock": 9999999 if available else 0})
