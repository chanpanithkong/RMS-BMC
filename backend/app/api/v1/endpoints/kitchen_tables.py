import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.dependencies import Ctx, require
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import DiningArea, KitchenStation, Order, OrderItem, RestaurantTable, TableGroup
from app.schemas.common import ORM, Strict
from app.schemas.orders import ItemStatusIn, OrderItemOut, PriorityIn, TicketOut, WasteOutcomeIn
from app.services import kitchen as ksvc
from app.services import orders as osvc
from app.services.platform import audit
from app.utils.timeutil import utcnow

kitchen = APIRouter(prefix="/kitchen", tags=["kitchen"])
tables = APIRouter(tags=["tables"])
KView = Annotated[Ctx, Depends(require("kitchen.view"))]


class StationOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    warn_minutes: int
    critical_minutes: int
    backup_printer: str | None
    is_active: bool


@kitchen.get("/stations", response_model=list[StationOut])
def stations(ctx: KView):
    return ctx.db.scalars(select(KitchenStation).where(KitchenStation.branch_id == ctx.branch_id).order_by(KitchenStation.code)).all()


@kitchen.get("/stations/{station_code}/open-tickets", response_model=list[TicketOut], summary="Full open-ticket state to (re)synchronise a station screen")
def open_tickets(station_code: str, ctx: KView):
    out = []
    for row in ksvc.open_tickets(ctx, station_code):
        t, o, items = row["ticket"], row["order"], row["items"]
        out.append({"ticket_id": t.id, "ticket_no": t.ticket_no, "ticket_type": t.ticket_type, "station_code": t.station_code, "priority": t.priority, "order_id": o.id,
                    "order_no": o.order_no, "order_type": o.order_type, "table_code": ctx.db.get(RestaurantTable, o.table_id).table_code if o.table_id else None,
                    "pickup_name": o.pickup_name, "server_user_id": o.server_user_id, "created_at": t.created_at, "age_seconds": row["age_seconds"],
                    "items": [{"order_item_id": i.id, "name_en": i.item_name_en_snapshot, "name_km": i.item_name_km_snapshot, "variant": i.variant_name_snapshot,
                               "quantity": i.quantity, "modifiers": [m.name_snapshot for m in i.modifiers], "note": i.note, "is_allergy": i.is_allergy,
                               "status": i.item_status, "version": i.version} for i in items]})
    return out


@kitchen.post("/items/{item_id}/status", response_model=OrderItemOut, summary="Start, ready, recall or serve one item (BR-007)")
def item_status(item_id: uuid.UUID, body: ItemStatusIn, ctx: KView):
    return ksvc.set_item_status(ctx, item_id, body.status, body.version)


class TicketActionOut(BaseModel):
    ticket_id: uuid.UUID
    bumped_at: object | None
    priority: int


def _t(t) -> dict:
    return {"ticket_id": t.id, "bumped_at": t.bumped_at, "priority": t.priority}


@kitchen.post("/tickets/{ticket_id}/bump", response_model=TicketActionOut)
def bump(ticket_id: uuid.UUID, ctx: KView):
    return _t(ksvc.bump(ctx, ticket_id))


@kitchen.post("/tickets/{ticket_id}/recall", response_model=TicketActionOut)
def recall(ticket_id: uuid.UUID, ctx: KView):
    return _t(ksvc.recall(ctx, ticket_id))


@kitchen.post("/tickets/{ticket_id}/priority", response_model=TicketActionOut)
def priority(ticket_id: uuid.UUID, body: PriorityIn, ctx: KView):
    return _t(ksvc.set_priority(ctx, ticket_id, body.priority))


@kitchen.post("/items/{item_id}/waste-outcome", response_model=OrderItemOut)
def waste(item_id: uuid.UUID, body: WasteOutcomeIn, ctx: KView):
    return ksvc.waste_outcome(ctx, item_id, body.outcome)


# ---------------------------------------------------------------- tables (TBL)
TView = Annotated[Ctx, Depends(require("tables.view"))]
TOperate = Annotated[Ctx, Depends(require("tables.operate"))]
TManage = Annotated[Ctx, Depends(require("tables.manage"))]


class AreaOut(ORM):
    id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool


class AreaIn(Strict):
    name: str = Field(min_length=1, max_length=60)
    sort_order: int = 0


class TableOut(ORM):
    id: uuid.UUID
    dining_area_id: uuid.UUID
    table_code: str
    capacity: int
    shape: str
    layout_x: Decimal | None
    layout_y: Decimal | None
    service_state: str
    is_out_of_service: bool
    out_of_service_reason: str | None
    current_group_id: uuid.UUID | None
    guest_count: int
    server_user_id: uuid.UUID | None
    seated_at: object | None
    version: int
    open_order_id: uuid.UUID | None = None
    open_order_total: Decimal | None = None
    flagged: bool = False


class TableIn(Strict):
    dining_area_id: uuid.UUID
    table_code: str = Field(min_length=1, max_length=10)
    capacity: int = Field(ge=1, le=50)
    shape: Literal["square", "round", "rect"] = "square"
    layout_x: Decimal | None = None
    layout_y: Decimal | None = None


class TablePatch(Strict):
    table_code: str | None = Field(None, min_length=1, max_length=10)
    capacity: int | None = Field(None, ge=1, le=50)
    shape: Literal["square", "round", "rect"] | None = None
    layout_x: Decimal | None = None
    layout_y: Decimal | None = None
    dining_area_id: uuid.UUID | None = None
    is_active: bool | None = None
    version: int | None = None


class SeatIn(Strict):
    guest_count: int = Field(ge=1, le=200)
    allow_over_capacity: bool = False
    open_order: bool = True


class StateIn(Strict):
    state: Literal["Available", "Reserved", "Seated", "Ordering", "Served", "AwaitingPayment", "Cleaning"]
    version: int | None = None


class OosIn(Strict):
    reason: str = Field(min_length=2, max_length=120)


class GroupIn(Strict):
    table_ids: list[uuid.UUID] = Field(min_length=2)


def _table(ctx: Ctx, table_id: uuid.UUID, lock: bool = True) -> RestaurantTable:
    stmt = select(RestaurantTable).where(RestaurantTable.id == table_id, RestaurantTable.branch_id == ctx.branch_id)
    t = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if t is None:
        raise NotFound("Table")
    return t


def table_out(ctx: Ctx, t: RestaurantTable) -> dict:
    order = ctx.db.scalar(select(Order).where(Order.table_id == t.id, Order.order_status.in_(("Draft", "Open"))).order_by(Order.created_at.desc()))
    data = TableOut.model_validate(t).model_dump()
    data["open_order_id"] = order.id if order else None
    data["open_order_total"] = order.grand_total if order and ctx.can("payments.view") else None
    data["flagged"] = bool(order) and t.service_state == "Available"  # FR-TBL-012
    return data


@tables.get("/dining-areas", response_model=list[AreaOut])
def areas(ctx: TView):
    return ctx.db.scalars(select(DiningArea).where(DiningArea.branch_id == ctx.branch_id).order_by(DiningArea.sort_order)).all()


@tables.post("/dining-areas", response_model=AreaOut, status_code=201)
def create_area(body: AreaIn, ctx: TManage):
    a = DiningArea(branch_id=ctx.branch_id, **body.model_dump())
    ctx.db.add(a)
    ctx.db.flush()
    audit(ctx.db, ctx, "tables.area_create", "DiningArea", a.id, after=body.model_dump())
    return a


@tables.get("/tables", response_model=list[TableOut], summary="Floor plan with live state and occupancy flags")
def list_tables(ctx: TView, area_id: uuid.UUID | None = None):
    stmt = select(RestaurantTable).where(RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active)
    if area_id:
        stmt = stmt.where(RestaurantTable.dining_area_id == area_id)
    return [table_out(ctx, t) for t in ctx.db.scalars(stmt.order_by(RestaurantTable.table_code))]


@tables.post("/tables", response_model=TableOut, status_code=201)
def create_table(body: TableIn, ctx: TManage):
    if ctx.db.scalar(select(RestaurantTable.id).where(RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.table_code == body.table_code, RestaurantTable.is_active)):
        raise Conflict("TABLE_CODE_EXISTS", f"Table {body.table_code} already exists in this branch.")  # BR-002
    area = ctx.db.get(DiningArea, body.dining_area_id)
    if area is None or area.branch_id != ctx.branch_id:
        raise NotFound("Dining area")
    t = RestaurantTable(branch_id=ctx.branch_id, **body.model_dump())
    ctx.db.add(t)
    ctx.db.flush()
    audit(ctx.db, ctx, "tables.create", "RestaurantTable", t.id, after=body.model_dump())
    return table_out(ctx, t)


@tables.patch("/tables/{table_id}", response_model=TableOut)
def update_table(table_id: uuid.UUID, body: TablePatch, ctx: TManage):
    t = _table(ctx, table_id)
    data = body.model_dump(exclude_unset=True)
    if (v := data.pop("version", None)) is not None and v != t.version:
        raise Conflict("VERSION_CONFLICT", "This table was changed on another device.")
    if "table_code" in data and data["table_code"] != t.table_code and ctx.db.scalar(select(RestaurantTable.id).where(
            RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.table_code == data["table_code"], RestaurantTable.is_active)):
        raise Conflict("TABLE_CODE_EXISTS", f"Table {data['table_code']} already exists in this branch.")
    before = {k: getattr(t, k) for k in data}
    for k, v in data.items():
        setattr(t, k, v)
    audit(ctx.db, ctx, "tables.update", "RestaurantTable", t.id, before=before, after=data)
    return table_out(ctx, t)


@tables.post("/tables/{table_id}/seat", summary="Seat a party and open a linked order in one step (FR-TBL-006)")
def seat(table_id: uuid.UUID, body: SeatIn, ctx: TOperate):
    t = _table(ctx, table_id)
    if t.is_out_of_service:
        raise Conflict("TABLE_OUT_OF_SERVICE", f"Table {t.table_code} is out of service.")
    if t.service_state not in ("Available", "Reserved"):
        raise Conflict("INVALID_STATUS_TRANSITION", f"Table {t.table_code} is {t.service_state}.")
    if body.guest_count > t.capacity and not (body.allow_over_capacity and ctx.can("tables.manage")):
        raise BusinessRuleError("OVER_CAPACITY", f"{body.guest_count} guests exceed the capacity of {t.capacity}. A manager can override.")
    osvc.set_table_state(ctx, t, "Seated")
    t.guest_count, t.server_user_id, t.seated_at = body.guest_count, ctx.user_id, utcnow()
    order = None
    if body.open_order:
        ctx.require("orders.create")
        order = osvc.create_order(ctx, {"order_type": "DineIn", "table_id": t.id, "guest_count": body.guest_count})
    audit(ctx.db, ctx, "tables.seat", "RestaurantTable", t.id, after={"guests": body.guest_count, "order_id": order.id if order else None})
    return {"table": TableOut.model_validate(table_out(ctx, t)), "order_id": order.id if order else None}


@tables.post("/tables/{table_id}/state", response_model=TableOut, summary="Change service state; invalid transitions return 409 (BR-027)")
def set_state(table_id: uuid.UUID, body: StateIn, ctx: TOperate):
    t = _table(ctx, table_id)
    if body.version is not None and body.version != t.version:
        raise Conflict("VERSION_CONFLICT", "This table was changed on another device.")
    before = t.service_state
    osvc.set_table_state(ctx, t, body.state)
    audit(ctx.db, ctx, "tables.state", "RestaurantTable", t.id, before={"state": before}, after={"state": body.state})
    return table_out(ctx, t)


@tables.post("/tables/{table_id}/out-of-service", response_model=TableOut)
def out_of_service(table_id: uuid.UUID, body: OosIn, ctx: TOperate):
    t = _table(ctx, table_id)
    if t.service_state != "Available":
        raise Conflict("TABLE_IN_USE", "Only an available table can be taken out of service.")
    t.is_out_of_service, t.out_of_service_reason = True, body.reason
    audit(ctx.db, ctx, "tables.out_of_service", "RestaurantTable", t.id, after={"reason": body.reason})
    return table_out(ctx, t)


@tables.post("/tables/{table_id}/return-to-service", response_model=TableOut)
def return_to_service(table_id: uuid.UUID, ctx: TOperate):
    t = _table(ctx, table_id)
    t.is_out_of_service, t.out_of_service_reason = False, None
    audit(ctx.db, ctx, "tables.return_to_service", "RestaurantTable", t.id)
    return table_out(ctx, t)


@tables.post("/table-groups", status_code=201, summary="Combine tables for one party (FR-TBL-007)")
def combine(body: GroupIn, ctx: TOperate):
    ts = list(ctx.db.scalars(select(RestaurantTable).where(RestaurantTable.id.in_(body.table_ids), RestaurantTable.branch_id == ctx.branch_id).order_by(RestaurantTable.id).with_for_update()))
    if len(ts) != len(set(body.table_ids)):
        raise NotFound("Table")
    if any(t.current_group_id or t.is_out_of_service for t in ts):
        raise Conflict("TABLE_NOT_AVAILABLE", "One of the tables is already combined or out of service.")
    g = TableGroup(branch_id=ctx.branch_id)
    ctx.db.add(g)
    ctx.db.flush()
    for t in ts:
        t.current_group_id = g.id
    audit(ctx.db, ctx, "tables.combine", "TableGroup", g.id, after={"tables": [t.table_code for t in ts]})
    return {"group_id": g.id, "tables": [t.table_code for t in ts], "capacity": sum(t.capacity for t in ts)}


@tables.delete("/table-groups/{group_id}", summary="Split a combined group")
def split_group(group_id: uuid.UUID, ctx: TOperate):
    g = ctx.db.get(TableGroup, group_id)
    if g is None or g.branch_id != ctx.branch_id or g.dissolved_at:
        raise NotFound("Table group")
    for t in ctx.db.scalars(select(RestaurantTable).where(RestaurantTable.current_group_id == g.id).with_for_update()):
        t.current_group_id = None
    g.dissolved_at = utcnow()
    audit(ctx.db, ctx, "tables.split_group", "TableGroup", g.id)
    return {"group_id": g.id, "dissolved_at": g.dissolved_at}


_ = (Forbidden, OrderItem)
