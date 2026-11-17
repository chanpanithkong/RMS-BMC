"""Customers (CUST), reservations and waiting list (RSV)."""
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import EmailStr, Field
from sqlalchemy import func, or_, select

from app.core.dependencies import Ctx, require
from app.models import Customer, Order, Reservation, WaitlistEntry
from app.schemas.common import Strict
from app.services import front as svc
from app.services import orders as osvc
from app.utils.timeutil import utcnow

customers = APIRouter(prefix="/customers", tags=["customers"])
reservations = APIRouter(tags=["reservations"])
CView = Annotated[Ctx, Depends(require("customers.view"))]
CManage = Annotated[Ctx, Depends(require("customers.manage"))]
RView = Annotated[Ctx, Depends(require("reservations.view"))]
RManage = Annotated[Ctx, Depends(require("reservations.manage"))]


class AddressIn(Strict):
    label: str = Field("Home", max_length=40)
    address: str = Field(min_length=3)
    landmark: str | None = None


class CustomerIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(None, max_length=25)
    email: EmailStr | None = None
    preferred_language: Literal["en", "km"] = "km"
    classification: Literal["Regular", "VIP", "Corporate"] = "Regular"
    preferences: str | None = None
    allergy_notes: str | None = None
    consent_marketing: bool = False
    addresses: list[AddressIn] = []


class CustomerPatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=120)
    phone: str | None = Field(None, max_length=25)
    email: EmailStr | None = None
    preferred_language: Literal["en", "km"] | None = None
    classification: Literal["Regular", "VIP", "Corporate"] | None = None
    preferences: str | None = None
    allergy_notes: str | None = None
    consent_marketing: bool | None = None


class MergeIn(Strict):
    keep_id: uuid.UUID
    merge_id: uuid.UUID


class ReasonIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class AttachIn(Strict):
    customer_id: uuid.UUID | None


@customers.get("", summary="Search by phone, name or code (FR-CUST-003); contact details masked without customers.contact.view")
def search(ctx: CView, q: str | None = Query(None, min_length=1), classification: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(Customer).where(Customer.merged_into_id.is_(None))
    if q:
        conds = [Customer.name.ilike(f"%{q}%"), Customer.code.ilike(f"%{q}%")]
        try:
            phone = svc.normalise_phone(q) if any(ch.isdigit() for ch in q) else None
        except Exception:
            phone = None
        if phone:
            conds.append(Customer.phone_e164 == phone)
        conds.append(Customer.phone_e164.like(f"%{''.join(ch for ch in q if ch.isdigit())[-6:]}%") if sum(ch.isdigit() for ch in q) >= 4 else Customer.code.ilike(q))
        stmt = stmt.where(or_(*conds))
    if classification:
        stmt = stmt.where(Customer.classification == classification)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(Customer.name).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": [svc.customer_out(ctx, c) for c in rows], "total": total, "page": page, "page_size": page_size}


@customers.post("", status_code=201, summary="Register a customer; duplicates by phone or email return 409 POSSIBLE_DUPLICATE with the existing record")
def create(body: CustomerIn, ctx: CManage, force: bool = False):
    data = body.model_dump()
    data["addresses"] = [a.model_dump() for a in body.addresses]
    return svc.customer_out(ctx, svc.create_customer(ctx, data, force))


@customers.get("/{customer_id}")
def get(customer_id: uuid.UUID, ctx: CView):
    return svc.customer_out(ctx, svc.get_customer(ctx, customer_id), with_stats=True)


@customers.patch("/{customer_id}")
def patch(customer_id: uuid.UUID, body: CustomerPatch, ctx: CManage):
    return svc.customer_out(ctx, svc.update_customer(ctx, svc.get_customer(ctx, customer_id, lock=True), body.model_dump(exclude_unset=True)))


@customers.post("/merge", summary="Merge a duplicate into the kept record (FR-CUST-004)")
def merge(body: MergeIn, ctx: CManage):
    keep = svc.get_customer(ctx, body.keep_id, lock=True)
    other = svc.get_customer(ctx, body.merge_id, lock=True)
    return svc.customer_out(ctx, svc.merge(ctx, keep, other))


@customers.post("/{customer_id}/anonymise", summary="Remove personal data; financial history stays under the anonymised reference")
def anonymise(customer_id: uuid.UUID, body: ReasonIn, ctx: CManage):
    return svc.customer_out(ctx, svc.anonymise(ctx, svc.get_customer(ctx, customer_id, lock=True), body.reason))


@customers.get("/{customer_id}/orders")
def history(customer_id: uuid.UUID, ctx: CView, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    svc.get_customer(ctx, customer_id)
    stmt = select(Order).where(Order.customer_id == customer_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": [{"id": o.id, "order_no": o.order_no, "business_date": o.business_date, "order_type": o.order_type, "order_status": o.order_status,
                      "grand_total": o.grand_total} for o in rows], "total": total, "page": page, "page_size": page_size}


@customers.post("/attach/{order_id}", summary="Attach (or detach) a customer on an order; returns preferences and allergy notes for the POS")
def attach(order_id: uuid.UUID, body: AttachIn, ctx: Annotated[Ctx, Depends(require("orders.edit"))]):
    order = osvc.get_order(ctx, order_id, lock=True)
    return svc.attach_to_order(ctx, order, body.customer_id)


# ---------------------------------------------------------------- reservations
class ReservationIn(Strict):
    guest_name: str = Field(min_length=1, max_length=120)
    guest_phone: str | None = None
    customer_id: uuid.UUID | None = None
    reserved_at: datetime
    party_size: int = Field(ge=1, le=200)
    duration_minutes: int | None = Field(None, ge=15, le=480)
    table_ids: list[uuid.UUID] = []
    notes: str | None = Field(None, max_length=500)


class ReservationPatch(Strict):
    guest_name: str | None = None
    guest_phone: str | None = None
    reserved_at: datetime | None = None
    party_size: int | None = Field(None, ge=1, le=200)
    duration_minutes: int | None = Field(None, ge=15, le=480)
    table_ids: list[uuid.UUID] | None = None
    notes: str | None = None


def rsv_out(r: Reservation) -> dict:
    return {"id": r.id, "guest_name": r.guest_name, "guest_phone": r.guest_phone, "customer_id": r.customer_id, "reserved_at": r.reserved_at, "party_size": r.party_size,
            "duration_minutes": r.duration_minutes, "status": r.status, "notes": r.notes, "cancel_reason": r.cancel_reason, "order_id": r.order_id,
            "table_ids": [t.table_id for t in r.tables if t.active], "version": r.version}


@reservations.get("/reservations", summary="Calendar and list; filter by date, status, name or phone (FR-RSV-010)")
def list_reservations(ctx: RView, on: date | None = None, status: str | None = None, q: str | None = None):
    stmt = select(Reservation).where(Reservation.branch_id == ctx.branch_id)
    if on:
        start = datetime.combine(on, datetime.min.time(), tzinfo=ZoneInfo(ctx.branch.timezone))
        stmt = stmt.where(Reservation.reserved_at >= start, Reservation.reserved_at < start + timedelta(days=1))
    if status:
        stmt = stmt.where(Reservation.status == status)
    if q:
        stmt = stmt.where(or_(Reservation.guest_name.ilike(f"%{q}%"), Reservation.guest_phone.ilike(f"%{q}%")))
    return [rsv_out(r) for r in ctx.db.scalars(stmt.order_by(Reservation.reserved_at).limit(500))]


@reservations.get("/reservations/availability", summary="Free tables and same-area table pairs for a time and party size")
def availability(ctx: RView, at: datetime, party_size: int = Query(ge=1), duration_minutes: int | None = None):
    return svc.available_tables(ctx, at, party_size, duration_minutes)


@reservations.post("/reservations", status_code=201, summary="Overlapping table assignments return 409 TABLE_TIME_CONFLICT with next_available")
def create_reservation(body: ReservationIn, ctx: RManage):
    return rsv_out(svc.create_reservation(ctx, body.model_dump()))


@reservations.patch("/reservations/{reservation_id}")
def update_reservation(reservation_id: uuid.UUID, body: ReservationPatch, ctx: RManage):
    return rsv_out(svc.update_reservation(ctx, svc.get_reservation(ctx, reservation_id, lock=True), body.model_dump(exclude_unset=True)))


@reservations.post("/reservations/{reservation_id}/cancel")
def cancel(reservation_id: uuid.UUID, body: ReasonIn, ctx: RManage):
    return rsv_out(svc.cancel_reservation(ctx, svc.get_reservation(ctx, reservation_id, lock=True), body.reason))


@reservations.post("/reservations/{reservation_id}/seat", summary="Seat the party and open the order in one step (FR-RSV-007)")
def seat(reservation_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("reservations.manage", "orders.create"))]):
    r = svc.get_reservation(ctx, reservation_id, lock=True)
    order = svc.seat_reservation(ctx, r)
    return {**rsv_out(r), "order_id": order.id}


@reservations.post("/reservations/{reservation_id}/no-show")
def no_show(reservation_id: uuid.UUID, ctx: RManage):
    return rsv_out(svc.no_show(ctx, svc.get_reservation(ctx, reservation_id, lock=True)))


@reservations.post("/reservations/process-holds", summary="Hold tables inside the hold window and mark overdue no-shows (also run by the worker)")
def process_holds(ctx: RManage):
    return svc.process_holds(ctx)


class WaitIn(Strict):
    party_name: str = Field(min_length=1, max_length=80)
    party_size: int = Field(ge=1, le=50)
    phone: str | None = None
    quoted_minutes: int | None = Field(None, ge=0, le=300, description="Leave empty to use the estimate from current turn times")


@reservations.get("/waitlist")
def waitlist(ctx: RView, include_closed: bool = False):
    stmt = select(WaitlistEntry).where(WaitlistEntry.branch_id == ctx.branch_id)
    if not include_closed:
        stmt = stmt.where(WaitlistEntry.status.in_(("Waiting", "Notified")))
    rows = ctx.db.scalars(stmt.order_by(WaitlistEntry.added_at)).all()
    now = utcnow()
    return [{"id": w.id, "party_name": w.party_name, "party_size": w.party_size, "phone": w.phone, "quoted_minutes": w.quoted_minutes, "status": w.status,
             "added_at": w.added_at, "waited_minutes": int((now - w.added_at).total_seconds() // 60), "notified_at": w.notified_at, "position": i + 1} for i, w in enumerate(rows)]


@reservations.post("/waitlist", status_code=201)
def add_wait(body: WaitIn, ctx: RManage):
    w = svc.add_waiting(ctx, body.model_dump())
    return {"id": w.id, "quoted_minutes": w.quoted_minutes, "status": w.status}


@reservations.post("/waitlist/{entry_id}/{action}", summary="action: notify, seat or left")
def wait_action(entry_id: uuid.UUID, action: Literal["notify", "seat", "left"], ctx: RManage):
    w = svc.set_waiting_status(ctx, entry_id, {"notify": "Notified", "seat": "Seated", "left": "Left"}[action])
    return {"id": w.id, "status": w.status, "notified_at": w.notified_at, "seated_at": w.seated_at}
