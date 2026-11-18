"""System configuration (CFG) and branches/devices (BRN basics)."""
import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.dialects.postgresql import Range

from app.core.dependencies import Ctx, require
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.core.security import new_opaque_token, token_digest
from app.models import Branch, CashierSession, Device, ExchangeRate, KitchenStation, Order, Payment, PaymentMethod, ReasonCode, Setting, TaxProfile, TaxProfileRate
from app.schemas.common import ORM, Strict
from app.services.platform import DEFAULT_SETTINGS, audit, get_setting
from app.utils.timeutil import utcnow

router = APIRouter(tags=["settings"])
View = Annotated[Ctx, Depends(require("settings.view"))]
Manage = Annotated[Ctx, Depends(require("settings.manage"))]
FINANCIAL_KEYS = {"billing", "cash"}  # BR-050: financial settings need settings.approve


class SettingIn(Strict):
    value: dict
    branch_scoped: bool = Field(True, description="False = restaurant-wide default")


@router.get("/settings/{key}", summary="Effective settings for this branch (defaults < restaurant < branch)")
def get_settings_group(key: str, ctx: View):
    if key not in DEFAULT_SETTINGS and key != "day_end":
        raise NotFound("Settings group")
    return {"key": key, "value": get_setting(ctx.db, key, ctx.branch_id)}


@router.put("/settings/{key}")
def put_settings_group(key: str, body: SettingIn, ctx: Manage):
    if key not in DEFAULT_SETTINGS:
        raise NotFound("Settings group")
    if key in FINANCIAL_KEYS:
        ctx.require("settings.approve")
    unknown = set(body.value) - set(DEFAULT_SETTINGS[key])
    if unknown:
        raise BusinessRuleError("SETTING_UNKNOWN", f"Unknown settings: {', '.join(sorted(unknown))}")
    if key == "billing" and Decimal(str(body.value.get("khr_rounding_increment", "100"))) <= 0:
        raise BusinessRuleError("VALIDATION_ERROR", "The rounding increment must be positive.")
    branch_id = ctx.branch_id if body.branch_scoped else None
    row = ctx.db.scalar(select(Setting).where(Setting.key == key, Setting.branch_id == branch_id if branch_id else Setting.branch_id.is_(None)).with_for_update())
    before = row.value if row else None
    if row is None:
        row = Setting(branch_id=branch_id, key=key, value=body.value, updated_by=ctx.user_id)
        ctx.db.add(row)
    else:
        row.value, row.updated_by = {**row.value, **body.value}, ctx.user_id
    ctx.db.flush()
    audit(ctx.db, ctx, "settings.change", "Setting", row.id, before=before, after=row.value)  # FR-CFG-018
    return {"key": key, "value": get_setting(ctx.db, key, ctx.branch_id)}


# ---------------------------------------------------------------- exchange rates (BR-024)
class RateIn(Strict):
    quote_currency: Literal["KHR"] = "KHR"
    rate: Decimal = Field(gt=0)
    effective_from: datetime
    source: str = Field(min_length=2, max_length=60)


class RateOut(ORM):
    id: uuid.UUID
    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_from: datetime
    source: str
    entered_by: uuid.UUID | None


@router.get("/exchange-rates", response_model=list[RateOut])
def rates(ctx: View):
    return ctx.db.scalars(select(ExchangeRate).order_by(ExchangeRate.effective_from.desc()).limit(100)).all()


@router.post("/exchange-rates", response_model=RateOut, status_code=201, summary="Enter a rate effective now or later (past dates need settings.approve)")
def add_rate(body: RateIn, ctx: Annotated[Ctx, Depends(require("exchange_rates.manage"))]):
    if body.effective_from < utcnow().replace(second=0, microsecond=0) and not ctx.can("settings.approve"):
        raise Forbidden("Only an approver can back-date an exchange rate.", code="BACKDATE_FORBIDDEN")
    r = ExchangeRate(base_currency="USD", quote_currency=body.quote_currency, rate=body.rate, effective_from=body.effective_from, source=body.source, entered_by=ctx.user_id)
    ctx.db.add(r)
    ctx.db.flush()
    audit(ctx.db, ctx, "settings.exchange_rate", "ExchangeRate", r.id, after=body.model_dump())
    return r


# ---------------------------------------------------------------- tax profiles (BR-010, BR-050)
class TaxRateIn(Strict):
    charge_kind: Literal["Tax", "ServiceCharge"]
    name: str = Field(min_length=1, max_length=60)
    rate: Decimal = Field(ge=0, lt=1, description="Fraction, e.g. 0.10. Configure only verified values (V-01).")
    base_rule: Literal["DiscountedSubtotal", "SubtotalPlusServiceCharge"]
    inclusive: bool = False
    applies_to_order_types: list[Literal["DineIn", "Takeaway", "Delivery"]] = Field(min_length=1)
    valid_from: datetime
    verified: bool = False
    verified_ref: str | None = None


@router.get("/tax-profiles", summary="Profiles with their effective-dated rules; unverified rules are flagged")
def tax_profiles(ctx: View):
    return [{"id": p.id, "code": p.code, "name": p.name, "is_active": p.is_active,
             "rates": [{"id": r.id, "charge_kind": r.charge_kind, "name": r.name, "rate": r.rate, "base_rule": r.base_rule, "inclusive": r.inclusive,
                        "applies_to_order_types": r.applies_to_order_types, "valid_from": r.valid_during.lower, "valid_to": r.valid_during.upper,
                        "verified": r.verified, "verified_ref": r.verified_ref} for r in p.rates]}
            for p in ctx.db.scalars(select(TaxProfile).order_by(TaxProfile.code))]


@router.post("/tax-profiles/{profile_id}/rates", status_code=201, summary="Schedule a new rule; the current open-ended rule ends at valid_from (dual control: settings.approve)")
def add_tax_rate(profile_id: uuid.UUID, body: TaxRateIn, ctx: Annotated[Ctx, Depends(require("settings.approve"))]):
    profile = ctx.db.get(TaxProfile, profile_id)
    if profile is None:
        raise NotFound("Tax profile")
    if body.valid_from < utcnow():
        raise BusinessRuleError("EFFECTIVE_IN_PAST", "Tax changes take effect from a future time (BR-050).")
    for old in ctx.db.scalars(select(TaxProfileRate).where(TaxProfileRate.profile_id == profile_id, TaxProfileRate.charge_kind == body.charge_kind,
                                                           TaxProfileRate.valid_during.op("@>")(cast(body.valid_from, DateTime(timezone=True)))).with_for_update()):
        if old.valid_during.upper is not None:
            raise Conflict("RATE_OVERLAP", "Another rule already covers that time.")
        old.valid_during = Range(old.valid_during.lower, body.valid_from)
    ctx.db.flush()
    r = TaxProfileRate(profile_id=profile_id, valid_during=Range(body.valid_from, None), **body.model_dump(exclude={"valid_from"}))
    ctx.db.add(r)
    ctx.db.flush()
    audit(ctx.db, ctx, "settings.tax_rate", "TaxProfile", profile_id, after=body.model_dump())
    return {"id": r.id, "valid_from": body.valid_from}


# ---------------------------------------------------------------- payment methods, stations, reasons
class MethodOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    currencies: list[str]
    reference_required: bool
    change_allowed: bool
    is_active: bool


class MethodPatch(Strict):
    name: str | None = None
    reference_required: bool | None = None
    is_active: bool | None = None


@router.get("/payment-methods", response_model=list[MethodOut])
def methods(ctx: Annotated[Ctx, Depends(require("payments.view"))]):
    return ctx.db.scalars(select(PaymentMethod).order_by(PaymentMethod.code)).all()


@router.patch("/payment-methods/{method_id}", response_model=MethodOut)
def patch_method(method_id: uuid.UUID, body: MethodPatch, ctx: Annotated[Ctx, Depends(require("settings.approve"))]):
    m = ctx.db.get(PaymentMethod, method_id)
    if m is None:
        raise NotFound("Payment method")
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(m, k) for k in data}
    for k, v in data.items():
        setattr(m, k, v)
    audit(ctx.db, ctx, "settings.payment_method", "PaymentMethod", m.id, before=before, after=data)
    return m


class StationIn(Strict):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,20}$")
    name: str = Field(min_length=1, max_length=60)
    warn_minutes: int = Field(10, ge=1, le=120)
    critical_minutes: int = Field(20, ge=2, le=240)
    backup_printer: str | None = None


@router.post("/kitchen-stations", status_code=201, summary="Configure a station (FR-CFG-009)")
def add_station(body: StationIn, ctx: Manage):
    if body.critical_minutes <= body.warn_minutes:
        raise BusinessRuleError("VALIDATION_ERROR", "Critical must be later than warning.")
    if ctx.db.scalar(select(KitchenStation.id).where(KitchenStation.branch_id == ctx.branch_id, KitchenStation.code == body.code)):
        raise Conflict("STATION_EXISTS", "A station with this code already exists.")
    s = KitchenStation(branch_id=ctx.branch_id, **body.model_dump())
    ctx.db.add(s)
    ctx.db.flush()
    audit(ctx.db, ctx, "settings.station", "KitchenStation", s.id, after=body.model_dump())
    return {"id": s.id, "code": s.code}


@router.get("/reason-codes")
def reason_codes(ctx: Annotated[Ctx, Depends(require("notifications.view"))], kind: str | None = None):
    stmt = select(ReasonCode).where(ReasonCode.is_active)
    if kind:
        stmt = stmt.where(ReasonCode.kind == kind)
    return [{"id": r.id, "kind": r.kind, "code": r.code, "name_en": r.name_en, "name_km": r.name_km} for r in ctx.db.scalars(stmt.order_by(ReasonCode.kind, ReasonCode.name_en))]


# ---------------------------------------------------------------- branches and devices
class BranchPatch(Strict):
    name_en: str | None = None
    name_km: str | None = None
    address: str | None = None
    phone: str | None = None
    opening_hours: str | None = None
    day_end_time: time | None = None


class DeviceIn(Strict):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["POS", "KDS", "PrintAgent", "Web"]


@router.get("/branches")
def branches(ctx: View):
    return [{"id": b.id, "code": b.code, "name_en": b.name_en, "name_km": b.name_km, "timezone": b.timezone, "day_end_time": b.day_end_time, "is_active": b.is_active}
            for b in ctx.user.branches]


@router.patch("/branches/{branch_id}")
def patch_branch(branch_id: uuid.UUID, body: BranchPatch, ctx: Annotated[Ctx, Depends(require("branches.manage"))]):
    b = next((x for x in ctx.user.branches if x.id == branch_id), None)
    if b is None:
        raise NotFound("Branch")
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(b, k) for k in data}
    for k, v in data.items():
        setattr(b, k, v)
    audit(ctx.db, ctx, "branch.update", "Branch", b.id, before=before, after=data)
    return {"id": b.id, **data}


@router.post("/devices", status_code=201, summary="Register a POS/KDS device; the token is shown once (FR-CFG-019)")
def register_device(body: DeviceIn, ctx: Annotated[Ctx, Depends(require("branches.manage"))]):
    token = new_opaque_token()
    d = Device(branch_id=ctx.branch_id, name=body.name, kind=body.kind, token_hash=token_digest(token))
    ctx.db.add(d)
    ctx.db.flush()
    audit(ctx.db, ctx, "device.register", "Device", d.id, after=body.model_dump())
    return {"id": d.id, "name": d.name, "kind": d.kind, "device_token": token}


@router.get("/devices")
def devices(ctx: View):
    return [{"id": d.id, "name": d.name, "kind": d.kind, "status": d.status, "last_seen_at": d.last_seen_at}
            for d in ctx.db.scalars(select(Device).where(Device.branch_id == ctx.branch_id).order_by(Device.name))]


@router.post("/devices/{device_id}/revoke")
def revoke_device(device_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("branches.manage"))]):
    d = ctx.db.get(Device, device_id)
    if d is None or d.branch_id != ctx.branch_id:
        raise NotFound("Device")
    d.status = "Revoked"
    audit(ctx.db, ctx, "device.revoke", "Device", d.id)
    return {"id": d.id, "status": d.status}


# ---------------------------------------------------------------- day-end (FR-CFG-016, BR-047)
class DayEndIn(Strict):
    acknowledge_open_items: bool = False
    reason: str | None = None


@router.post("/day-end/close", summary="Check open orders, sessions and pending payments, then close the business day")
def day_end(body: DayEndIn, ctx: Manage):
    bdate = ctx.business_date()
    open_orders = ctx.db.scalar(select(func.count()).select_from(Order).where(Order.branch_id == ctx.branch_id, Order.business_date == bdate, Order.order_status.in_(("Draft", "Open"))))
    open_sessions = ctx.db.scalar(select(func.count()).select_from(CashierSession).where(CashierSession.branch_id == ctx.branch_id, CashierSession.status == "Open"))
    pending = ctx.db.scalar(select(func.count()).select_from(Payment).where(Payment.branch_id == ctx.branch_id, Payment.status == "Pending"))
    summary = {"business_date": bdate.isoformat(), "open_orders": open_orders, "open_sessions": open_sessions, "pending_payments": pending}
    if (open_orders or open_sessions or pending) and not body.acknowledge_open_items:
        raise Conflict("DAY_END_BLOCKED", "Resolve or acknowledge open orders, sessions and pending payments first.", **summary)
    if (open_orders or open_sessions or pending) and not body.reason:
        raise BusinessRuleError("REASON_REQUIRED", "Give a reason for closing with open items.")
    row = ctx.db.scalar(select(Setting).where(Setting.key == "day_end", Setting.branch_id == ctx.branch_id).with_for_update())
    if row is None:
        row = Setting(branch_id=ctx.branch_id, key="day_end", value={"closed_dates": []})
        ctx.db.add(row)
    if bdate.isoformat() in row.value.get("closed_dates", []):
        raise Conflict("ALREADY_CLOSED", "This business day is already closed.")
    row.value = {"closed_dates": [*row.value.get("closed_dates", []), bdate.isoformat()][-400:]}
    ctx.db.flush()
    audit(ctx.db, ctx, "day_end.close", "Branch", ctx.branch_id, after=summary, reason=body.reason)
    from app.services import analytics

    analytics.refresh_day(ctx.db, ctx.branch, bdate)  # the closed day's summaries, final as of now (SRS §12)
    return {**summary, "closed": True}
