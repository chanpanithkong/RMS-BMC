"""Customers (SRS §6.7; BR-045) and reservations / waiting list (§6.8; BR-028)."""
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.core.realtime import emit
from app.models import Bill, Customer, CustomerAddress, Order, Reservation, ReservationTable, RestaurantTable, WaitlistEntry
from app.services import orders as osvc
from app.services.platform import audit, get_setting, next_number
from app.utils.timeutil import utcnow


# ---------------------------------------------------------------- phone and masking
def normalise_phone(raw: str | None) -> str | None:
    """Cambodian numbers accepted with a leading 0 or +855 (FR-CUST validation); others must be +<country><number>."""
    if raw is None or not raw.strip():
        return None
    digits = re.sub(r"[\s\-().]", "", raw.strip())
    if digits.startswith("+"):
        e164 = "+" + re.sub(r"\D", "", digits)
    elif digits.startswith("855"):
        e164 = "+" + digits
    elif digits.startswith("0"):
        e164 = "+855" + digits[1:]
    else:
        raise BusinessRuleError("PHONE_INVALID", "Enter the phone with a leading 0 or a +country code.", details=[{"field": "phone", "issue": "format"}])
    if e164.startswith("+855") and not re.fullmatch(r"\+855[1-9]\d{7,8}", e164):
        raise BusinessRuleError("PHONE_INVALID", "That isn't a valid Cambodian phone number.", details=[{"field": "phone", "issue": "format"}])
    if not re.fullmatch(r"\+[1-9]\d{7,14}", e164):
        raise BusinessRuleError("PHONE_INVALID", "That isn't a valid phone number.", details=[{"field": "phone", "issue": "format"}])
    return e164


def national(e164: str | None) -> str | None:
    if not e164:
        return None
    if e164.startswith("+855"):
        n = "0" + e164[4:]
        return f"{n[:3]} {n[3:6]} {n[6:]}"
    return e164


def mask_phone(e164: str | None) -> str | None:
    """FR-CUST-009, AT-CUST-02: 012 *** 678."""
    n = national(e164)
    if not n:
        return None
    parts = n.split(" ")
    return f"{parts[0]} *** {parts[-1]}" if len(parts) >= 3 else n[:3] + "***" + n[-3:]


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    user, domain = email.split("@", 1)
    return f"{user[:1]}***@{domain}"


def customer_out(ctx: Ctx, c: Customer, with_stats: bool = False) -> dict:
    show = ctx.can("customers.contact.view")
    out = {"id": c.id, "code": c.code, "name": c.name, "phone": national(c.phone_e164) if show else mask_phone(c.phone_e164),
           "email": c.email if show else mask_email(c.email), "contact_masked": not show, "preferred_language": c.preferred_language,
           "classification": c.classification, "preferences": c.preferences, "allergy_notes": c.allergy_notes, "consent_marketing": c.consent_marketing,
           "no_show_count": c.no_show_count, "loyalty_points": c.loyalty_points, "anonymised": c.anonymised_at is not None, "merged_into_id": c.merged_into_id,
           "addresses": [{"id": a.id, "label": a.label, "address": a.address if show else "•••", "landmark": a.landmark if show else None} for a in c.addresses],
           "version": c.version}
    if with_stats:  # FR-CUST-005
        visits, spend, last = ctx.db.execute(select(func.count(func.distinct(Order.id)), func.coalesce(func.sum(Bill.paid_total - Bill.refunded_total), 0), func.max(Order.created_at))
                                             .select_from(Order).outerjoin(Bill, (Bill.order_id == Order.id) & (Bill.status != "Void"))
                                             .where(Order.customer_id == c.id, Order.order_status == "Completed")).one()
        out.update({"visits": visits, "total_spend": spend, "last_visit": last})
    return out


# ---------------------------------------------------------------- customers
def get_customer(ctx: Ctx, customer_id: uuid.UUID, lock: bool = False) -> Customer:
    stmt = select(Customer).where(Customer.id == customer_id)
    c = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if c is None:
        raise NotFound("Customer")
    return c


def find_duplicates(ctx: Ctx, phone_e164: str | None, email: str | None, exclude: uuid.UUID | None = None) -> list[Customer]:
    conds = []
    if phone_e164:
        conds.append(Customer.phone_e164 == phone_e164)
    if email:
        conds.append(func.lower(Customer.email) == email.lower())
    if not conds:
        return []
    stmt = select(Customer).where(or_(*conds), Customer.merged_into_id.is_(None), Customer.anonymised_at.is_(None))
    if exclude:
        stmt = stmt.where(Customer.id != exclude)
    return list(ctx.db.scalars(stmt))


def create_customer(ctx: Ctx, data: dict, force: bool) -> Customer:
    phone = normalise_phone(data.pop("phone", None))
    dupes = find_duplicates(ctx, phone, data.get("email"))
    if dupes:
        # AT-CUST-01: warn and offer the existing record. A phone duplicate can never be forced (unique).
        if not force or any(d.phone_e164 == phone for d in dupes if phone):
            raise Conflict("POSSIBLE_DUPLICATE", "A customer with this phone or email already exists.", existing=[{"id": str(d.id), "code": d.code, "name": d.name} for d in dupes])
    addresses = data.pop("addresses", [])
    consent = data.get("consent_marketing", False)
    c = Customer(code=f"C-{next_number(ctx.db, ctx.branch_id, 'CUSTOMER', 'C'):06d}", phone_e164=phone, created_by=ctx.user_id,
                 consent_at=utcnow() if consent else None, consent_channel="POS" if consent else None, **data)
    ctx.db.add(c)
    ctx.db.flush()
    ctx.db.add_all([CustomerAddress(customer_id=c.id, **a) for a in addresses])
    ctx.db.flush()
    ctx.db.refresh(c)
    audit(ctx.db, ctx, "customer.create", "Customer", c.id, after={"code": c.code, "consent": consent})
    return c


def update_customer(ctx: Ctx, c: Customer, data: dict) -> Customer:
    if c.anonymised_at:
        raise Conflict("CUSTOMER_ANONYMISED", "This customer was anonymised.")
    if "phone" in data:
        phone = normalise_phone(data.pop("phone"))
        if phone and find_duplicates(ctx, phone, None, exclude=c.id):
            raise Conflict("POSSIBLE_DUPLICATE", "Another customer has this phone number.")
        c.phone_e164 = phone
    if data.get("consent_marketing") is not None and data["consent_marketing"] != c.consent_marketing:
        c.consent_at, c.consent_channel = utcnow(), "POS"
    for k, v in data.items():
        setattr(c, k, v)
    audit(ctx.db, ctx, "customer.update", "Customer", c.id, after={k: v for k, v in data.items() if k not in ("email",)})
    return c


def merge(ctx: Ctx, keep: Customer, merge_from: Customer) -> Customer:
    """FR-CUST-004: history moves to the kept record; the other is retired, not deleted."""
    if keep.id == merge_from.id or merge_from.merged_into_id:
        raise BusinessRuleError("MERGE_INVALID", "Choose two different active customers.")
    db = ctx.db
    moved = db.execute(update(Order).where(Order.customer_id == merge_from.id).values(customer_id=keep.id)).rowcount
    db.execute(update(Reservation).where(Reservation.customer_id == merge_from.id).values(customer_id=keep.id))
    db.execute(update(CustomerAddress).where(CustomerAddress.customer_id == merge_from.id).values(customer_id=keep.id))
    keep.loyalty_points += merge_from.loyalty_points
    from app.services.loyalty import move_on_merge

    move_on_merge(ctx.db, merge_from.id, keep.id)
    keep.no_show_count += merge_from.no_show_count
    if not keep.phone_e164 and merge_from.phone_e164:
        phone, merge_from.phone_e164 = merge_from.phone_e164, None
        db.flush()
        keep.phone_e164 = phone
    merge_from.merged_into_id = keep.id
    db.flush()
    db.refresh(keep)
    audit(db, ctx, "customer.merge", "Customer", keep.id, after={"merged_from": merge_from.id, "orders_moved": moved})
    return keep


def anonymise(ctx: Ctx, c: Customer, reason: str) -> Customer:
    """FR-CUST-010, AT-CUST-03: personal data removed; financial records keep the anonymised reference."""
    db = ctx.db
    c.name, c.phone_e164, c.email, c.preferences, c.allergy_notes = f"Anonymised {c.code}", None, None, None, None
    c.consent_marketing, c.anonymised_at = False, utcnow()
    for a in list(c.addresses):
        db.delete(a)
    db.execute(update(Order).where(Order.customer_id == c.id).values(customer_name=None, customer_phone=None, delivery_address=None))
    db.execute(update(Reservation).where(Reservation.customer_id == c.id).values(guest_name=f"Anonymised {c.code}", guest_phone=None))
    db.flush()
    audit(db, ctx, "customer.anonymise", "Customer", c.id, reason=reason)
    return c


def attach_to_order(ctx: Ctx, order: Order, customer_id: uuid.UUID | None) -> dict:
    osvc.ensure_editable(order)
    if customer_id is None:
        order.customer_id = None
        return {"customer": None}
    c = get_customer(ctx, customer_id)
    if c.merged_into_id or c.anonymised_at:
        raise Conflict("CUSTOMER_INACTIVE", "This customer record is merged or anonymised.")
    order.customer_id, order.customer_name = c.id, c.name
    order.customer_phone = order.customer_phone or national(c.phone_e164)
    osvc.log_event(ctx, order, "customer_attached", {"customer_id": c.id})
    # FR-CUST-006: show preferences and allergy notes on POS
    return {"customer": {"id": c.id, "name": c.name, "classification": c.classification, "preferences": c.preferences, "allergy_notes": c.allergy_notes}}


# ---------------------------------------------------------------- reservations
def rsv_settings(ctx: Ctx) -> dict:
    return get_setting(ctx.db, "reservations", ctx.branch_id)


def _slot(ctx: Ctx, start: datetime, duration: int) -> Range:
    buffer = int(rsv_settings(ctx)["buffer_minutes"])
    return Range(start, start + timedelta(minutes=duration + buffer))


def _tables(ctx: Ctx, ids: list[uuid.UUID]) -> list[RestaurantTable]:
    ts = list(ctx.db.scalars(select(RestaurantTable).where(RestaurantTable.id.in_(ids), RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active)))
    if len(ts) != len(set(ids)):
        raise NotFound("Table")
    return ts


def busy_until(ctx: Ctx, table_id: uuid.UUID, slot: Range, exclude: uuid.UUID | None = None) -> datetime | None:
    stmt = select(func.max(func.upper(ReservationTable.slot))).where(ReservationTable.table_id == table_id, ReservationTable.active,
                                                                    ReservationTable.slot.op("&&")(slot))
    if exclude:
        stmt = stmt.where(ReservationTable.reservation_id != exclude)
    return ctx.db.scalar(stmt)


def assign_tables(ctx: Ctx, r: Reservation, table_ids: list[uuid.UUID]) -> None:
    db = ctx.db
    for rt in r.tables:
        rt.active = False
    db.flush()
    if not table_ids:
        return
    tables = _tables(ctx, table_ids)
    if sum(t.capacity for t in tables) < r.party_size:
        raise BusinessRuleError("TABLE_TOO_SMALL", f"The selected tables seat {sum(t.capacity for t in tables)}, fewer than {r.party_size}.")
    slot = _slot(ctx, r.reserved_at, r.duration_minutes)
    for t in tables:
        try:
            with db.begin_nested():
                db.add(ReservationTable(reservation_id=r.id, table_id=t.id, slot=slot))
                db.flush()
        except IntegrityError:
            # BR-028 / AT-RSV-01: rejected by the exclusion constraint; suggest the next free start time.
            free_at = busy_until(ctx, t.id, slot, exclude=r.id)
            alternatives = [str(x["table_id"]) for x in available_tables(ctx, r.reserved_at, r.party_size, r.duration_minutes, exclude=r.id)[:5]]
            raise Conflict("TABLE_TIME_CONFLICT", f"Table {t.table_code} is already reserved then.", next_available=free_at.isoformat() if free_at else None,
                           alternative_table_ids=alternatives)
    db.flush()
    db.refresh(r)


def available_tables(ctx: Ctx, at: datetime, party: int, duration: int | None = None, exclude: uuid.UUID | None = None) -> list[dict]:
    """FR-RSV-002: single tables that fit, then pairs in the same area."""
    duration = duration or int(rsv_settings(ctx)["default_duration_minutes"])
    slot = _slot(ctx, at, duration)
    tables = list(ctx.db.scalars(select(RestaurantTable).where(RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active, ~RestaurantTable.is_out_of_service)
                                 .order_by(RestaurantTable.capacity, RestaurantTable.table_code)))
    free = [t for t in tables if busy_until(ctx, t.id, slot, exclude) is None]
    singles = [{"table_ids": [t.id], "table_id": t.id, "tables": [t.table_code], "capacity": t.capacity} for t in free if t.capacity >= party]
    pairs = []
    if not singles:
        for i, a in enumerate(free):
            for b in free[i + 1:]:
                if a.dining_area_id == b.dining_area_id and a.capacity + b.capacity >= party:
                    pairs.append({"table_ids": [a.id, b.id], "table_id": a.id, "tables": [a.table_code, b.table_code], "capacity": a.capacity + b.capacity})
    return singles + pairs[:10]


def create_reservation(ctx: Ctx, data: dict) -> Reservation:
    s = rsv_settings(ctx)
    if data["reserved_at"] <= utcnow():
        raise BusinessRuleError("RESERVATION_IN_PAST", "Choose a time in the future.", details=[{"field": "reserved_at", "issue": "past"}])
    if data["party_size"] > int(s["max_party_size"]):
        raise BusinessRuleError("PARTY_TOO_LARGE", f"Parties above {s['max_party_size']} need a manual arrangement.")
    phone = normalise_phone(data.get("guest_phone"))
    if data.get("customer_id"):
        get_customer(ctx, data["customer_id"])
    r = Reservation(branch_id=ctx.branch_id, customer_id=data.get("customer_id"), guest_name=data["guest_name"], guest_phone=national(phone),
                    reserved_at=data["reserved_at"], duration_minutes=data.get("duration_minutes") or int(s["default_duration_minutes"]), party_size=data["party_size"],
                    status=data.get("status", "Confirmed"), notes=data.get("notes"), created_by=ctx.user_id)
    ctx.db.add(r)
    ctx.db.flush()
    assign_tables(ctx, r, data.get("table_ids") or [])
    if r.status == "Confirmed":
        from app.services import sms

        sms.reservation_message(ctx.db, r, "confirmed")  # FR-RSV-009
    audit(ctx.db, ctx, "reservation.create", "Reservation", r.id, after={"at": r.reserved_at, "party": r.party_size, "tables": data.get("table_ids")})
    emit(ctx.db, f"tables:{ctx.branch_id}", "reservation.created", {"reservation_id": str(r.id)})
    return r


def get_reservation(ctx: Ctx, rid: uuid.UUID, lock: bool = False) -> Reservation:
    stmt = select(Reservation).where(Reservation.id == rid, Reservation.branch_id == ctx.branch_id)
    r = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if r is None:
        raise NotFound("Reservation")
    return r


def _release_tables(ctx: Ctx, r: Reservation) -> None:
    for rt in r.tables:
        if rt.active:
            rt.active = False
            t = ctx.db.get(RestaurantTable, rt.table_id, with_for_update=True)
            if t.service_state == "Reserved":
                osvc.set_table_state(ctx, t, "Available")


def update_reservation(ctx: Ctx, r: Reservation, data: dict) -> Reservation:
    if r.status not in ("Requested", "Confirmed"):
        raise Conflict("RESERVATION_CLOSED", f"This reservation is {r.status}.")
    before = {"at": r.reserved_at, "party": r.party_size, "tables": [str(t.table_id) for t in r.tables if t.active]}
    table_ids = data.pop("table_ids", None)
    if "guest_phone" in data:
        data["guest_phone"] = national(normalise_phone(data["guest_phone"]))
    for k, v in data.items():
        setattr(r, k, v)
    if table_ids is not None or {"reserved_at", "duration_minutes", "party_size"} & set(data):
        ids = table_ids if table_ids is not None else [t.table_id for t in r.tables if t.active]
        assign_tables(ctx, r, ids)
    if "reserved_at" in data and r.status == "Confirmed":
        from app.services import sms

        r.reminder_sent_at = None
        sms.reservation_message(ctx.db, r, "confirmed")  # new time: new confirmation (the dedupe key includes the time)
    audit(ctx.db, ctx, "reservation.update", "Reservation", r.id, before=before, after={**data, "tables": table_ids})  # FR-RSV-004 history
    return r


def cancel_reservation(ctx: Ctx, r: Reservation, reason: str) -> Reservation:
    if r.status not in ("Requested", "Confirmed"):
        raise Conflict("RESERVATION_CLOSED", f"This reservation is {r.status}.")
    r.status, r.cancel_reason = "Cancelled", reason
    _release_tables(ctx, r)
    audit(ctx.db, ctx, "reservation.cancel", "Reservation", r.id, reason=reason)
    return r


def seat_reservation(ctx: Ctx, r: Reservation) -> Order:
    """FR-RSV-007: tables seated and an order opened in one action."""
    if r.status not in ("Requested", "Confirmed"):
        raise Conflict("RESERVATION_CLOSED", f"This reservation is {r.status}.")
    active = [rt for rt in r.tables if rt.active]
    if not active:
        raise BusinessRuleError("TABLE_REQUIRED", "Assign a table before seating.")
    tables = [ctx.db.get(RestaurantTable, rt.table_id, with_for_update=True) for rt in active]
    for t in tables:
        if t.service_state not in ("Available", "Reserved") or t.is_out_of_service:
            raise Conflict("TABLE_NOT_AVAILABLE", f"Table {t.table_code} isn't free yet.")
    order = osvc.create_order(ctx, {"order_type": "DineIn", "table_id": tables[0].id, "guest_count": r.party_size, "customer_name": r.guest_name, "customer_phone": r.guest_phone})
    order.customer_id = r.customer_id
    for t in tables[1:]:
        osvc.set_table_state(ctx, t, "Seated")
        t.guest_count, t.server_user_id, t.seated_at = 0, ctx.user_id, utcnow()
    r.status, r.order_id = "Seated", order.id
    audit(ctx.db, ctx, "reservation.seat", "Reservation", r.id, after={"order_id": order.id})
    return order


def no_show(ctx: Ctx, r: Reservation, now: datetime | None = None) -> Reservation:
    """FR-RSV-006: after the grace period the reservation becomes No-show and tables are released."""
    now = now or utcnow()
    grace = int(rsv_settings(ctx)["grace_minutes"])
    if r.status != "Confirmed":
        raise Conflict("RESERVATION_CLOSED", f"This reservation is {r.status}.")
    if now < r.reserved_at + timedelta(minutes=grace):
        raise BusinessRuleError("GRACE_NOT_OVER", f"The grace period of {grace} minutes isn't over yet.")
    r.status = "NoShow"
    _release_tables(ctx, r)
    if r.customer_id:
        c = ctx.db.get(Customer, r.customer_id, with_for_update=True)
        c.no_show_count += 1
    audit(ctx.db, ctx, "reservation.no_show", "Reservation", r.id)
    return r


def process_holds(ctx: Ctx, now: datetime | None = None) -> dict:
    """FR-RSV-005 and FR-RSV-006 sweep: hold tables inside the hold window; mark no-shows after grace. Run by the worker or a manager."""
    now = now or utcnow()
    s = rsv_settings(ctx)
    held = no_shows = 0
    for r in ctx.db.scalars(select(Reservation).where(Reservation.branch_id == ctx.branch_id, Reservation.status == "Confirmed").with_for_update()):
        if now >= r.reserved_at + timedelta(minutes=int(s["grace_minutes"])):
            no_show(ctx, r, now)
            no_shows += 1
        elif now >= r.reserved_at - timedelta(minutes=int(s["hold_minutes"])):
            for rt in r.tables:
                t = ctx.db.get(RestaurantTable, rt.table_id, with_for_update=True)
                if rt.active and t.service_state == "Available" and not t.is_out_of_service:
                    osvc.set_table_state(ctx, t, "Reserved")
                    held += 1
    return {"held_tables": held, "no_shows": no_shows}


def upcoming_for_table(ctx: Ctx, table_id: uuid.UUID, within_minutes: int) -> Reservation | None:
    now = utcnow()
    return ctx.db.scalar(select(Reservation).join(ReservationTable).where(ReservationTable.table_id == table_id, ReservationTable.active,
                                                                          Reservation.status.in_(("Confirmed", "Requested")),
                                                                          Reservation.reserved_at.between(now - timedelta(minutes=15), now + timedelta(minutes=within_minutes)))
                         .order_by(Reservation.reserved_at).limit(1))


# ---------------------------------------------------------------- waiting list (FR-RSV-008)
def average_turn_minutes(ctx: Ctx) -> int:
    since = utcnow() - timedelta(days=7)
    avg = ctx.db.scalar(select(func.avg(func.extract("epoch", Order.completed_at - Order.created_at) / 60)).where(
        Order.branch_id == ctx.branch_id, Order.order_type == "DineIn", Order.order_status == "Completed", Order.completed_at >= since))
    return int(avg) if avg else int(rsv_settings(ctx)["default_duration_minutes"])


def estimate_wait(ctx: Ctx, party_size: int, ahead: int) -> int:
    fitting = ctx.db.scalar(select(func.count()).select_from(RestaurantTable).where(RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active,
                                                                                    RestaurantTable.capacity >= party_size, ~RestaurantTable.is_out_of_service)) or 1
    free_now = ctx.db.scalar(select(func.count()).select_from(RestaurantTable).where(RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active,
                                                                                     RestaurantTable.capacity >= party_size, RestaurantTable.service_state == "Available",
                                                                                     ~RestaurantTable.is_out_of_service)) or 0
    if free_now > ahead:
        return 0
    return max(5, round(average_turn_minutes(ctx) * (ahead + 1 - free_now) / fitting))


def add_waiting(ctx: Ctx, data: dict) -> WaitlistEntry:
    ahead = ctx.db.scalar(select(func.count()).select_from(WaitlistEntry).where(WaitlistEntry.branch_id == ctx.branch_id, WaitlistEntry.status.in_(("Waiting", "Notified")))) or 0
    quoted = data.get("quoted_minutes") or estimate_wait(ctx, data["party_size"], ahead)
    w = WaitlistEntry(branch_id=ctx.branch_id, party_name=data["party_name"], party_size=data["party_size"], phone=national(normalise_phone(data.get("phone"))),
                      quoted_minutes=quoted, created_by=ctx.user_id)
    ctx.db.add(w)
    ctx.db.flush()
    audit(ctx.db, ctx, "waitlist.add", "WaitlistEntry", w.id, after={"party": w.party_size, "quoted": quoted})
    return w


def set_waiting_status(ctx: Ctx, wid: uuid.UUID, status: str) -> WaitlistEntry:
    w = ctx.db.scalar(select(WaitlistEntry).where(WaitlistEntry.id == wid, WaitlistEntry.branch_id == ctx.branch_id).with_for_update())
    if w is None:
        raise NotFound("Waiting-list entry")
    allowed = {"Waiting": {"Notified", "Seated", "Left"}, "Notified": {"Seated", "Left"}}
    if status not in allowed.get(w.status, set()):
        raise Conflict("INVALID_STATUS_TRANSITION", f"Can't move from {w.status} to {status}.")
    w.status = status
    if status == "Notified":
        w.notified_at = utcnow()  # AT-RSV-03
        from app.services import sms

        sms.waitlist_ready(ctx.db, w)  # FR-RSV-009
    elif status == "Seated":
        w.seated_at = utcnow()
    audit(ctx.db, ctx, f"waitlist.{status.lower()}", "WaitlistEntry", w.id)
    return w
