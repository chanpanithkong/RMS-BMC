"""Configuration, menu and seating tables (SRS §10.2 Menu, Billing setup, Tables)."""
import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, Time, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, TSTZRANGE, Range
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, Rate, TimestampMixin, VersionMixin, check_in

ORDER_TYPES = ("DineIn", "Takeaway", "Delivery")
TABLE_STATES = ("Available", "Reserved", "Seated", "Ordering", "Served", "AwaitingPayment", "Cleaning")


# ---------------------------------------------------------------- configuration
class TaxProfile(IdMixin, TimestampMixin, Base):
    __tablename__ = "tax_profiles"
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rates: Mapped[list["TaxProfileRate"]] = relationship(lazy="selectin", order_by="TaxProfileRate.charge_kind")


class TaxProfileRate(IdMixin, TimestampMixin, Base):
    """Effective-dated tax or service-charge rule (BR-010). Overlap is excluded by a GiST constraint in the migration."""

    __tablename__ = "tax_profile_rates"
    __table_args__ = (
        CheckConstraint(check_in("charge_kind", ("Tax", "ServiceCharge")), name="charge_kind"),
        CheckConstraint(check_in("base_rule", ("DiscountedSubtotal", "SubtotalPlusServiceCharge")), name="base_rule"),
        CheckConstraint("rate >= 0 AND rate < 1", name="rate"),
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tax_profiles.id"))
    charge_kind: Mapped[str] = mapped_column(String(15))
    name: Mapped[str] = mapped_column(String(60))
    rate: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    base_rule: Mapped[str] = mapped_column(String(30))
    inclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    applies_to_order_types: Mapped[list[str]] = mapped_column(ARRAY(String(10)))
    valid_during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_ref: Mapped[str | None] = mapped_column(Text)


class ExchangeRate(IdMixin, Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("base_currency", "quote_currency", "effective_from"), CheckConstraint("rate > 0", name="rate"))
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Rate)
    effective_from: Mapped[datetime]
    source: Mapped[str] = mapped_column(String(60))
    entered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PaymentMethod(IdMixin, TimestampMixin, Base):
    __tablename__ = "payment_methods"
    __table_args__ = (CheckConstraint(check_in("kind", ("Cash", "QR", "Bank", "Card", "Credit")), name="kind"),)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(10))
    currencies: Mapped[list[str]] = mapped_column(ARRAY(String(3)))
    reference_required: Mapped[bool] = mapped_column(Boolean, default=False)
    change_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class KitchenStation(IdMixin, TimestampMixin, Base):
    __tablename__ = "kitchen_stations"
    __table_args__ = (UniqueConstraint("branch_id", "code"), CheckConstraint("critical_minutes > warn_minutes", name="thresholds"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(60))
    warn_minutes: Mapped[int] = mapped_column(SmallInteger, default=10)
    critical_minutes: Mapped[int] = mapped_column(SmallInteger, default=20)
    backup_printer: Mapped[str | None] = mapped_column(String(60))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReasonCode(IdMixin, Base):
    __tablename__ = "reason_codes"
    __table_args__ = (UniqueConstraint("kind", "code"), CheckConstraint(check_in("kind", ("Void", "Cancel", "Discount", "Refund", "Adjustment", "Wastage", "CashMovement", "Variance")), name="kind"))
    kind: Mapped[str] = mapped_column(String(15))
    code: Mapped[str] = mapped_column(String(30))
    name_en: Mapped[str] = mapped_column(String(80))
    name_km: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- menu
class MenuCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "menu_categories"
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"))
    name_en: Mapped[str] = mapped_column(String(80))
    name_km: Mapped[str | None] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MenuItem(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "menu_items"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code"),
        CheckConstraint(check_in("item_type", ("Food", "Beverage", "Other", "Combo")), name="item_type"),
        Index("uq_menu_items_barcode", "barcode", unique=True, postgresql_where=text("barcode IS NOT NULL")),
        Index("ix_menu_items_category_active", "category_id", "is_active"),
        Index("ix_menu_items_name_trgm", "name_en", "name_km", postgresql_using="gin", postgresql_ops={"name_en": "gin_trgm_ops", "name_km": "gin_trgm_ops"}),
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_categories.id"))
    code: Mapped[str] = mapped_column(String(20))
    name_en: Mapped[str] = mapped_column(String(150))
    name_km: Mapped[str | None] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(10), default="Food")
    station_code: Mapped[str | None] = mapped_column(String(20))  # routes to kitchen_stations.code within the branch; NULL = no kitchen routing
    tax_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tax_profiles.id"))
    barcode: Mapped[str | None] = mapped_column(String(50))
    image_url: Mapped[str | None] = mapped_column(String(300))
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=lambda: ["POS"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    variants: Mapped[list["MenuItemVariant"]] = relationship(lazy="selectin", order_by="MenuItemVariant.sort_order")
    category: Mapped[MenuCategory] = relationship(lazy="joined")


class MenuItemVariant(IdMixin, TimestampMixin, Base):
    __tablename__ = "menu_item_variants"
    __table_args__ = (CheckConstraint("portion_factor > 0", name="portion_factor"),)
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"))
    name_en: Mapped[str] = mapped_column(String(60))
    name_km: Mapped[str | None] = mapped_column(String(60))
    portion_factor: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=Decimal("1"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PriceList(IdMixin, Base):
    """FR-MENU-008: Standard plus time-based lists (happy hour, delivery, staff...). A list with no rules is only used where it is
    chosen explicitly (e.g. the online price list setting); a list with rules applies automatically while they match, highest priority first."""

    __tablename__ = "price_lists"
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=list, server_default="{}")  # 0 = Monday; empty = every day
    time_from: Mapped[time | None] = mapped_column(Time)
    time_to: Mapped[time | None] = mapped_column(Time)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")  # POS, Online, QR, Platform; empty = all
    order_types: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")  # DineIn, Takeaway, Delivery; empty = all
    branch_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")  # empty = all branches
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class MenuPrice(IdMixin, Base):
    """Effective-dated price per variant, price list and branch (BR-048). Never overwritten; overlap excluded in migration."""

    __tablename__ = "menu_prices"
    __table_args__ = (CheckConstraint("price >= 0", name="price"),)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_item_variants.id"))
    price_list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("price_lists.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    price: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    valid_during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ModifierGroup(IdMixin, TimestampMixin, Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (CheckConstraint("min_select >= 0 AND min_select <= max_select AND max_select >= 1", name="selection"),)
    name_en: Mapped[str] = mapped_column(String(60))
    name_km: Mapped[str | None] = mapped_column(String(60))
    min_select: Mapped[int] = mapped_column(SmallInteger, default=0)
    max_select: Mapped[int] = mapped_column(SmallInteger, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    modifiers: Mapped[list["Modifier"]] = relationship(lazy="selectin", order_by="Modifier.sort_order")


class Modifier(IdMixin, TimestampMixin, Base):
    __tablename__ = "modifiers"
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modifier_groups.id"))
    name_en: Mapped[str] = mapped_column(String(60))
    name_km: Mapped[str | None] = mapped_column(String(60))
    price_delta: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ItemModifierGroup(Base):
    __tablename__ = "item_modifier_groups"
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"), primary_key=True)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modifier_groups.id"), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class BranchMenuItem(Base):
    """Branch assignment and '86' availability (FR-MENU-009, BR-003)."""

    __tablename__ = "branch_menu_items"
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), primary_key=True)
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"), primary_key=True)
    is_assigned: Mapped[bool] = mapped_column(Boolean, default=True)
    unavailable_until: Mapped[datetime | None]
    unavailable_reason: Mapped[str | None] = mapped_column(String(120))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------- seating
class DiningArea(IdMixin, TimestampMixin, Base):
    __tablename__ = "dining_areas"
    __table_args__ = (UniqueConstraint("branch_id", "name"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TableGroup(IdMixin, Base):
    __tablename__ = "table_groups"
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    dissolved_at: Mapped[datetime | None]


class RestaurantTable(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "restaurant_tables"
    __table_args__ = (
        Index("uq_restaurant_tables_branch_code_active", "branch_id", "table_code", unique=True, postgresql_where=text("is_active")),
        CheckConstraint("capacity BETWEEN 1 AND 50", name="capacity"),
        CheckConstraint(check_in("service_state", TABLE_STATES), name="service_state"),
        CheckConstraint(check_in("shape", ("square", "round", "rect")), name="shape"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    dining_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dining_areas.id"))
    table_code: Mapped[str] = mapped_column(String(10))
    capacity: Mapped[int] = mapped_column(SmallInteger)
    shape: Mapped[str] = mapped_column(String(10), default="square")
    layout_x: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    layout_y: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    service_state: Mapped[str] = mapped_column(String(16), default="Available")
    is_out_of_service: Mapped[bool] = mapped_column(Boolean, default=False)
    out_of_service_reason: Mapped[str | None] = mapped_column(String(120))
    current_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("table_groups.id"))
    guest_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    server_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    seated_at: Mapped[datetime | None]
    qr_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)  # FR-ONL-013; the token itself is shown once
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
