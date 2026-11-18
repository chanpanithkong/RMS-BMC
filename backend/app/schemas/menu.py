import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORM, Strict


class CategoryIn(Strict):
    name_en: str = Field(min_length=1, max_length=80)
    name_km: str | None = Field(None, max_length=80)
    sort_order: int = 0
    is_active: bool = True


class CategoryOut(ORM):
    id: uuid.UUID
    name_en: str
    name_km: str | None
    sort_order: int
    is_active: bool


class VariantIn(Strict):
    name_en: str = Field(min_length=1, max_length=60)
    name_km: str | None = None
    portion_factor: Decimal = Field(Decimal("1"), gt=0)
    price: Decimal | None = Field(None, ge=0, decimal_places=4, description="Initial Standard price, effective now")


class VariantOut(ORM):
    id: uuid.UUID
    name_en: str
    name_km: str | None
    portion_factor: Decimal
    is_active: bool
    price: Decimal | None = None
    regular_price: Decimal | None = Field(None, description="Set when a time-based price list (e.g. happy hour) is in effect: the normal price")
    price_list: str | None = Field(None, description="Name of the time-based price list in effect, if any")


class MenuItemIn(Strict):
    code: str = Field(min_length=1, max_length=20)
    name_en: str = Field(min_length=1, max_length=150)
    name_km: str | None = Field(None, max_length=150)
    description: str | None = None
    category_id: uuid.UUID
    item_type: Literal["Food", "Beverage", "Other", "Combo"] = "Food"
    station_code: str | None = Field(None, description="Kitchen station code; null = no kitchen routing")
    tax_profile_id: uuid.UUID
    barcode: str | None = Field(None, max_length=50)
    image_url: str | None = None
    channels: list[Literal["POS", "Online", "Platform"]] = ["POS"]
    variants: list[VariantIn] = Field(default_factory=lambda: [VariantIn(name_en="Regular")], min_length=1)


class MenuItemUpdate(Strict):
    name_en: str | None = Field(None, min_length=1, max_length=150)
    name_km: str | None = None
    description: str | None = None
    category_id: uuid.UUID | None = None
    item_type: Literal["Food", "Beverage", "Other", "Combo"] | None = None
    station_code: str | None = None
    tax_profile_id: uuid.UUID | None = None
    barcode: str | None = None
    image_url: str | None = None
    channels: list[Literal["POS", "Online", "Platform"]] | None = None
    is_active: bool | None = None
    version: int | None = Field(None, description="Optimistic lock; stale version returns 409")


class ModifierOut(ORM):
    id: uuid.UUID
    name_en: str
    name_km: str | None
    price_delta: Decimal
    is_active: bool


class ModifierGroupOut(ORM):
    id: uuid.UUID
    name_en: str
    name_km: str | None
    min_select: int
    max_select: int
    is_active: bool
    modifiers: list[ModifierOut]


class ModifierIn(Strict):
    name_en: str = Field(min_length=1, max_length=60)
    name_km: str | None = None
    price_delta: Decimal = Field(Decimal("0"), ge=0)


class ModifierGroupIn(Strict):
    name_en: str = Field(min_length=1, max_length=60)
    name_km: str | None = None
    min_select: int = Field(0, ge=0)
    max_select: int = Field(1, ge=1)
    modifiers: list[ModifierIn] = []

    @model_validator(mode="after")
    def _minmax(self):
        if self.min_select > self.max_select:
            raise ValueError("min_select can't exceed max_select")
        return self


class AttachGroupsIn(Strict):
    group_ids: list[uuid.UUID]


class MenuItemOut(ORM):
    id: uuid.UUID
    code: str
    name_en: str
    name_km: str | None
    description: str | None
    category_id: uuid.UUID
    category_name_en: str
    item_type: str
    station_code: str | None
    tax_profile_id: uuid.UUID
    barcode: str | None
    image_url: str | None
    channels: list[str]
    is_active: bool
    version: int
    available: bool
    unavailable_reason: str | None
    variants: list[VariantOut]
    modifier_groups: list[ModifierGroupOut]
    combo_slots: list["ComboSlotOut"] = []


class PriceIn(Strict):
    variant_id: uuid.UUID
    price: Decimal = Field(ge=0, decimal_places=4)
    valid_from: datetime
    valid_to: datetime | None = None
    branch_id: uuid.UUID | None = Field(None, description="Null = restaurant default")
    price_list: str | None = Field(None, description="Price list code; default from billing settings")


class PriceOut(ORM):
    id: uuid.UUID
    variant_id: uuid.UUID
    branch_id: uuid.UUID | None
    price: Decimal
    currency: str
    valid_from: datetime | None
    valid_to: datetime | None
    created_at: datetime
    created_by: uuid.UUID | None


class AvailabilityIn(Strict):
    available: bool
    until: datetime | None = Field(None, description="Default: end of the current business day")
    reason: str | None = Field(None, max_length=120)


class AvailabilityOut(BaseModel):
    menu_item_id: uuid.UUID
    available: bool
    unavailable_until: datetime | None
    reason: str | None


# ---------------------------------------------------------------- price lists and menu schedules (FR-MENU-008, BR-003)
Channel = Literal["POS", "Online", "QR", "Platform"]
OrderType = Literal["DineIn", "Takeaway", "Delivery"]


def _check_window(days, t_from, t_to):
    if days and any(d < 0 or d > 6 for d in days):
        raise ValueError("days_of_week must be 0 (Monday) to 6 (Sunday)")
    if (t_from is None) != (t_to is None):
        raise ValueError("Give both time_from and time_to, or neither")


class PriceListIn(Strict):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    priority: int = Field(10, ge=1, le=1000, description="Higher wins when several automatic lists apply")
    days_of_week: list[int] = Field([], description="0 = Monday; empty = every day")
    time_from: time | None = None
    time_to: time | None = None
    channels: list[Channel] = []
    order_types: list[OrderType] = []
    branch_ids: list[uuid.UUID] = Field([], description="Empty = every branch")
    auto_apply: bool = Field(True, description="False = used only where chosen explicitly (e.g. the online price list setting)")
    is_active: bool = True

    @model_validator(mode="after")
    def _window(self):
        _check_window(self.days_of_week, self.time_from, self.time_to)
        return self


class PriceListPatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=60)
    priority: int | None = Field(None, ge=1, le=1000)
    days_of_week: list[int] | None = None
    time_from: time | None = None
    time_to: time | None = None
    channels: list[Channel] | None = None
    order_types: list[OrderType] | None = None
    branch_ids: list[uuid.UUID] | None = None
    auto_apply: bool | None = None
    is_active: bool | None = None


class PriceListOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool
    priority: int
    days_of_week: list[int]
    time_from: time | None
    time_to: time | None
    channels: list[str]
    order_types: list[str]
    branch_ids: list[str]
    auto_apply: bool


class ScheduleIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    days_of_week: list[int] = Field([], description="0 = Monday; empty = every day")
    time_from: time | None = None
    time_to: time | None = None
    date_from: date | None = None
    date_to: date | None = None
    branch_ids: list[uuid.UUID] = Field([], description="Empty = every branch")
    is_active: bool = True
    item_ids: list[uuid.UUID] = []

    @model_validator(mode="after")
    def _rules(self):
        _check_window(self.days_of_week, self.time_from, self.time_to)
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to can't be before date_from")
        return self


class ScheduleOut(ORM):
    id: uuid.UUID
    name: str
    days_of_week: list[int]
    time_from: time | None
    time_to: time | None
    date_from: date | None
    date_to: date | None
    branch_ids: list[str]
    is_active: bool
    item_ids: list[uuid.UUID] = []


# ---------------------------------------------------------------- combo slots (FR-MENU-005)
class ComboOptionIn(Strict):
    variant_id: uuid.UUID
    price_delta: Decimal = Field(Decimal("0"), ge=0, decimal_places=4, description="Extra charge when this item is chosen")


class ComboSlotIn(Strict):
    name_en: str = Field(min_length=1, max_length=60)
    name_km: str | None = Field(None, max_length=60)
    min_select: int = Field(1, ge=0, le=10)
    max_select: int = Field(1, ge=1, le=10)
    options: list[ComboOptionIn] = Field(min_length=1, max_length=60)


class ComboSlotsIn(Strict):
    slots: list[ComboSlotIn] = Field(min_length=1, max_length=10)


class ComboOptionOut(ORM):
    id: uuid.UUID
    variant_id: uuid.UUID
    menu_item_id: uuid.UUID
    item_name_en: str
    item_name_km: str | None
    variant_name: str
    price_delta: Decimal
    available: bool


class ComboSlotOut(ORM):
    id: uuid.UUID
    name_en: str
    name_km: str | None
    min_select: int
    max_select: int
    options: list[ComboOptionOut]


MenuItemOut.model_rebuild()
