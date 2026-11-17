"""Orders, items, kitchen tickets (SRS §10.4.7–10.4.9)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin, VersionMixin, check_in
from app.models.catalog import ORDER_TYPES

ORDER_STATUS = ("Draft", "Open", "Completed", "Cancelled")
KITCHEN_STATUS = ("NotSent", "InProgress", "Ready", "Served")
PAYMENT_STATUS = ("Unpaid", "PartiallyPaid", "Paid", "Credit", "Refunded", "PartiallyRefunded")
ITEM_STATUS = ("Pending", "Sent", "InPreparation", "Ready", "Served", "Collected", "Cancelled")
VOID_TYPES = ("BeforePreparation", "AfterPreparation", "Comp")


class Order(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("branch_id", "business_date", "order_no"),
        UniqueConstraint("branch_id", "idempotency_key"),
        CheckConstraint(check_in("order_type", ORDER_TYPES), name="order_type"),
        CheckConstraint(check_in("channel", ("POS", "Online", "QR", "Platform")), name="channel"),
        CheckConstraint(check_in("order_status", ORDER_STATUS), name="order_status"),
        CheckConstraint(check_in("kitchen_status", KITCHEN_STATUS), name="kitchen_status"),
        CheckConstraint(check_in("payment_status", PAYMENT_STATUS), name="payment_status"),
        CheckConstraint("guest_count IS NULL OR guest_count > 0", name="guest_count"),
        Index("ix_orders_branch_date_status", "branch_id", "business_date", "order_status"),
        Index("ix_orders_open_table", "branch_id", "table_id", postgresql_where=text("order_status = 'Open'")),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date] = mapped_column(Date)
    order_no: Mapped[str] = mapped_column(String(20))
    order_type: Mapped[str] = mapped_column(String(10))
    channel: Mapped[str] = mapped_column(String(10), default="POS")
    order_status: Mapped[str] = mapped_column(String(10), default="Draft")
    kitchen_status: Mapped[str] = mapped_column(String(12), default="NotSent")
    payment_status: Mapped[str] = mapped_column(String(20), default="Unpaid")
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("restaurant_tables.id"))
    table_tag: Mapped[str | None] = mapped_column(String(10))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(120))
    customer_phone: Mapped[str | None] = mapped_column(String(20))
    pickup_name: Mapped[str | None] = mapped_column(String(60))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None]  # scheduled pickup or delivery time (FR-DLV-001, A3)
    guest_count: Mapped[int | None] = mapped_column(SmallInteger)
    server_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))
    note: Mapped[str | None] = mapped_column(Text)
    held_label: Mapped[str | None] = mapped_column(String(60))
    gross_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    discount_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    subtotal: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    service_charge_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    delivery_fee: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    rounding_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    grand_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["OrderItem"]] = relationship(lazy="selectin", order_by="OrderItem.created_at", back_populates="order")


class OrderItem(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(check_in("item_status", ITEM_STATUS), name="item_status"),
        CheckConstraint("void_type IS NULL OR " + check_in("void_type", VOID_TYPES), name="void_type"),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("unit_price_snapshot >= 0", name="unit_price"),
        Index("ix_order_items_kds", "branch_id", "station_code", "item_status", postgresql_where=text("item_status IN ('Sent','InPreparation','Ready')")),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"))
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_item_variants.id"))
    item_name_en_snapshot: Mapped[str] = mapped_column(String(150))
    item_name_km_snapshot: Mapped[str | None] = mapped_column(String(150))
    variant_name_snapshot: Mapped[str] = mapped_column(String(60))
    category_name_snapshot: Mapped[str] = mapped_column(String(80))
    unit_price_snapshot: Mapped[Decimal]
    modifiers_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    tax_profile_id_snapshot: Mapped[uuid.UUID] = mapped_column(ForeignKey("tax_profiles.id"))
    station_code: Mapped[str | None] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(9, 3))
    seat_no: Mapped[int | None] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(Text)
    is_allergy: Mapped[bool] = mapped_column(Boolean, default=False)
    item_status: Mapped[str] = mapped_column(String(14), default="Pending")
    void_type: Mapped[str | None] = mapped_column(String(20))
    void_reason: Mapped[str | None] = mapped_column(Text)
    void_approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    waste_outcome: Mapped[str | None] = mapped_column(String(10))
    sent_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    ready_at: Mapped[datetime | None]
    served_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    replaces_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_items.id"))
    line_gross: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    line_discount: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    line_net: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    order: Mapped[Order] = relationship(back_populates="items")
    modifiers: Mapped[list["OrderItemModifier"]] = relationship(lazy="selectin")


class OrderItemModifier(IdMixin, Base):
    __tablename__ = "order_item_modifiers"
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id"), index=True)
    modifier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modifiers.id"))
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modifier_groups.id"))
    name_snapshot: Mapped[str] = mapped_column(String(60))
    price_delta_snapshot: Mapped[Decimal]
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1)


class OrderDiscount(IdMixin, Base):
    """Manual discount on an item or the whole order (BR-009, BR-037). One active per scope."""

    __tablename__ = "order_discounts"
    __table_args__ = (
        CheckConstraint(check_in("kind", ("Percent", "Amount")), name="kind"),
        CheckConstraint("value > 0", name="value"),
        Index("uq_order_discounts_active_scope", "order_id", text("coalesce(order_item_id, '00000000-0000-0000-0000-000000000000'::uuid)"), unique=True, postgresql_where=text("removed_at IS NULL")),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_items.id"))
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal]
    reason: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    promotion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("promotions.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    removed_at: Mapped[datetime | None]


class OrderEvent(IdMixin, Base):
    __tablename__ = "order_events"
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict | None]
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())


class KitchenTicket(IdMixin, Base):
    __tablename__ = "kitchen_tickets"
    __table_args__ = (
        UniqueConstraint("branch_id", "business_date", "ticket_no"),
        CheckConstraint(check_in("ticket_type", ("New", "Addition", "Void", "Change")), name="ticket_type"),
        Index("ix_kitchen_tickets_open", "branch_id", "station_code", "created_at", postgresql_where=text("bumped_at IS NULL")),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date] = mapped_column(Date)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    station_code: Mapped[str] = mapped_column(String(20))
    ticket_no: Mapped[int] = mapped_column(Integer)
    ticket_type: Mapped[str] = mapped_column(String(10), default="New")
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    delivered_at: Mapped[datetime | None]
    printed_at: Mapped[datetime | None]
    bumped_at: Mapped[datetime | None]

    items: Mapped[list["KitchenTicketItem"]] = relationship(lazy="selectin")


class KitchenTicketItem(Base):
    __tablename__ = "kitchen_ticket_items"
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("kitchen_tickets.id"), primary_key=True)
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id"), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(9, 3))
    action: Mapped[str] = mapped_column(String(10), default="Add")
