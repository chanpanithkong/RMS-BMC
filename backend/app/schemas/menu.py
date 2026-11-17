import uuid
from datetime import datetime
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
