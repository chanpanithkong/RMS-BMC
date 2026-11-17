"""Multi-branch (BRN): create branches, branch menu assignment, inter-branch transfers, branch comparison."""
import uuid
from datetime import date, time
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator
from sqlalchemy import or_, select

from app.core.dependencies import Ctx, require
from app.core.exceptions import NotFound
from app.models import InterBranchTransfer, MenuItem
from app.schemas.common import Strict
from app.services import branches as svc
from app.services.reports import _range

router = APIRouter(tags=["branches"])


class BranchIn(Strict):
    code: str = Field(min_length=2, max_length=10, pattern=r"^[A-Za-z0-9_-]+$")
    name_en: str = Field(min_length=1, max_length=120)
    name_km: str | None = Field(None, max_length=120)
    address: str | None = None
    phone: str | None = Field(None, max_length=20)
    timezone: str = "Asia/Phnom_Penh"
    day_end_time: time = time(4, 0)
    opening_hours: str | None = Field(None, max_length=60)

    @field_validator("timezone")
    @classmethod
    def tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown time zone")
        return v


class AssignmentIn(Strict):
    assigned: bool


class TransferLineIn(Strict):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    uom_id: uuid.UUID


class DispatchIn(Strict):
    to_branch_id: uuid.UUID
    from_location_id: uuid.UUID
    note: str | None = Field(None, max_length=300)
    lines: list[TransferLineIn] = Field(min_length=1)


class ReceiveLineIn(Strict):
    line_id: uuid.UUID
    qty_received: Decimal = Field(ge=0, description="In the ingredient's stock unit")
    variance_reason: str | None = Field(None, max_length=200)


class ReceiveIn(Strict):
    to_location_id: uuid.UUID
    lines: list[ReceiveLineIn] = Field([], description="Lines left out are received in full")


class CancelIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


@router.post("/branches", status_code=201, summary="Register a branch with default stations and storage locations (FR-BRN-001)")
def create_branch(body: BranchIn, ctx: Annotated[Ctx, Depends(require("branches.manage"))]):
    return svc.branch_out(svc.create_branch(ctx, body.model_dump()))


@router.put("/menu-items/{item_id}/branch-assignment", summary="Sell or stop selling an item at the current branch (FR-BRN-003)")
def assign(item_id: uuid.UUID, body: AssignmentIn, ctx: Annotated[Ctx, Depends(require("menu.manage"))]):
    item = ctx.db.get(MenuItem, item_id)
    if item is None:
        raise NotFound("Menu item")
    bmi = svc.set_menu_assignment(ctx, item, body.assigned)
    return {"menu_item_id": item.id, "branch_id": bmi.branch_id, "assigned": bmi.is_assigned}


@router.get("/branch-transfers", summary="Transfers sent from or arriving at the current branch")
def list_transfers(ctx: Annotated[Ctx, Depends(require("inventory.view"))], status: str | None = None, direction: str | None = Query(None, pattern="^(in|out)$")):
    stmt = select(InterBranchTransfer)
    if direction == "in":
        stmt = stmt.where(InterBranchTransfer.to_branch_id == ctx.branch_id)
    elif direction == "out":
        stmt = stmt.where(InterBranchTransfer.from_branch_id == ctx.branch_id)
    else:
        stmt = stmt.where(or_(InterBranchTransfer.from_branch_id == ctx.branch_id, InterBranchTransfer.to_branch_id == ctx.branch_id))
    if status:
        stmt = stmt.where(InterBranchTransfer.status == status)
    return [svc.transfer_out(t) for t in ctx.db.scalars(stmt.order_by(InterBranchTransfer.dispatched_at.desc()).limit(200))]


@router.post("/branch-transfers", status_code=201, summary="Dispatch stock to another branch (FR-BRN-006)")
def dispatch(body: DispatchIn, ctx: Annotated[Ctx, Depends(require("inventory.manage"))]):
    return svc.transfer_out(svc.dispatch(ctx, body.to_branch_id, body.from_location_id, [ln.model_dump() for ln in body.lines], body.note))


@router.get("/branch-transfers/{transfer_id}")
def get_transfer(transfer_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("inventory.view"))]):
    return svc.transfer_out(svc.get_transfer(ctx, transfer_id))


@router.post("/branch-transfers/{transfer_id}/receive", summary="Receive at the destination; short quantities need a reason")
def receive(transfer_id: uuid.UUID, body: ReceiveIn, ctx: Annotated[Ctx, Depends(require("inventory.manage"))]):
    t = svc.get_transfer(ctx, transfer_id, lock=True)
    return svc.transfer_out(svc.receive(ctx, t, body.to_location_id, {ln.line_id: (ln.qty_received, ln.variance_reason) for ln in body.lines}))


@router.post("/branch-transfers/{transfer_id}/cancel", summary="Sending branch only, while in transit; stock returns to the source location")
def cancel(transfer_id: uuid.UUID, body: CancelIn, ctx: Annotated[Ctx, Depends(require("inventory.manage"))]):
    return svc.transfer_out(svc.cancel(ctx, svc.get_transfer(ctx, transfer_id, lock=True), body.reason))


@router.get("/branch-comparison", summary="Per-branch measures with consolidated totals (FR-BRN-008, FR-BRN-009); needs report.cross_branch")
def comparison(ctx: Annotated[Ctx, Depends(require("dashboard.view"))], date_from: date | None = None, date_to: date | None = None,
               branch_ids: Annotated[list[uuid.UUID] | None, Query()] = None):
    start, end = _range(date_from, date_to, ctx)
    return {"from": start, "to": end, **svc.comparison(ctx, start, end, branch_ids)}
