"""Printable bill and receipt (SRS §6.7, BR-049). Everything the paper copy shows comes from the posted records;
the frontend only lays it out. A receipt reprint is labelled COPY n (the count is kept by reprint_receipt).

The layout is a customer bill or receipt. It is not presented as a VAT tax invoice: what a Cambodian tax invoice
must contain has not been verified for this project.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.dependencies import Ctx
from app.models import (Bill, Branch, Order, OrderItem, Payment, PaymentMethod, Receipt, Restaurant, RestaurantTable, User)
from app.services.billing import current_rate
from app.utils.timeutil import utcnow

ZERO = Decimal("0")


def _local(dt: datetime | None, tz: ZoneInfo) -> str | None:
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if dt else None


def bill_document(ctx: Ctx, bill: Bill) -> dict:
    db = ctx.db
    order = db.get(Order, bill.order_id)
    branch = db.get(Branch, bill.branch_id)
    restaurant = db.get(Restaurant, branch.restaurant_id)
    tz = ZoneInfo(branch.timezone)
    receipt = db.scalar(select(Receipt).where(Receipt.bill_id == bill.id))
    table = db.get(RestaurantTable, order.table_id) if order.table_id else None
    server = db.get(User, order.server_user_id) if order.server_user_id else None

    items = {i.id: i for i in db.scalars(select(OrderItem).where(OrderItem.id.in_([ln.order_item_id for ln in bill.lines] or [None])))}
    entries: dict = {}
    order_of: list = []
    for ln in sorted(bill.lines, key=lambda x: (items[x.order_item_id].created_at, str(x.order_item_id))):  # as ordered; combo parts in slot order
        it = items[ln.order_item_id]
        e = {"name_en": it.item_name_en_snapshot, "name_km": it.item_name_km_snapshot,
             "variant": None if it.variant_name_snapshot == "Regular" else it.variant_name_snapshot,
             "modifiers": [m.name_snapshot for m in it.modifiers], "note": it.note, "quantity": (it.quantity * ln.quantity_share).normalize(),  # share of the line on this bill
             "amount_gross": ln.amount_gross, "amount_discount": ln.amount_discount, "amount_net": ln.amount_net, "parts": []}
        entries[it.id] = (it, e)
        order_of.append(it.id)
    lines = []
    for iid in order_of:
        it, e = entries[iid]
        parent = entries.get(it.parent_item_id) if it.parent_item_id else None
        if parent:  # combo item: listed under its combo, which carries the combo's total (FR-MENU-005)
            p = parent[1]
            p["parts"].append(f"{it.combo_slot_name}: {e['name_en']}" if it.combo_slot_name else e["name_en"])
            for k in ("amount_gross", "amount_discount", "amount_net"):
                p[k] += e[k]
            continue
        lines.append(e)

    pays = []
    for p, m in db.execute(select(Payment, PaymentMethod).join(PaymentMethod, PaymentMethod.id == Payment.method_id)
                           .where(Payment.bill_id == bill.id, Payment.status == "Confirmed").order_by(Payment.created_at)):
        pays.append({"method": m.name, "currency": p.currency, "tendered": p.amount_tendered, "applied": p.amount_applied,
                     "change": p.change_amount, "change_currency": p.change_currency or p.currency,
                     "card_last4": p.card_last4, "reference": p.external_ref, "at": _local(p.created_at, tz)})
    rate = current_rate(db, "KHR")
    kind = "Receipt" if receipt else "Bill"
    return {
        "kind": kind,
        "copy_label": f"COPY {receipt.reprint_count}" if receipt and receipt.reprint_count else None,
        "restaurant": {"name_en": restaurant.name_en, "name_km": restaurant.name_km, "legal_name": restaurant.legal_name, "tax_id": restaurant.tax_id},
        "branch": {"name_en": branch.name_en, "name_km": branch.name_km, "address": branch.address, "phone": branch.phone},
        "order": {"order_no": order.order_no, "order_type": order.order_type, "table": table.table_code if table else order.table_tag,
                  "pickup_name": order.pickup_name, "guests": order.guest_count, "server": server.full_name if server else None,
                  "opened_at": _local(order.created_at, tz)},
        "bill": {"bill_no": bill.bill_no, "split": f"{bill.split_index + 1} of {bill.split_count}" if bill.split_count > 1 else None,
                 "business_date": bill.business_date, "status": bill.status, "printed_count": bill.printed_count},
        "receipt": {"receipt_no": receipt.receipt_no, "issued_at": _local(receipt.issued_at, tz)} if receipt else None,
        "lines": lines,
        "charges": [{"type": c.charge_type, "name": c.name, "rate": c.rate, "amount": c.amount} for c in bill.charges],
        "totals": {"gross": bill.gross_total, "discount": bill.discount_total, "subtotal": bill.subtotal, "service_charge": bill.service_charge_total,
                   "tax": bill.tax_total, "delivery_fee": bill.delivery_fee, "rounding": bill.rounding_total, "total": bill.total,
                   "paid": bill.paid_total, "refunded": bill.refunded_total, "balance": bill.balance, "currency": bill.currency},
        "khr_rate": rate.rate if rate else None,
        "payments": pays,
        "printed_at": _local(utcnow(), tz),
        "printed_by": ctx.user.full_name,
    }
