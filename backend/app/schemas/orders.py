import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORM, Strict

OrderType = Literal["DineIn", "Takeaway", "Delivery"]


class ModifierPick(Strict):
    modifier_id: uuid.UUID


class ItemIn(Strict):
    variant_id: uuid.UUID
    quantity: Decimal = Field(gt=0, le=999, decimal_places=3)
    modifiers: list[ModifierPick] = []
    seat_no: int | None = Field(None, ge=1, le=50)
    note: str | None = Field(None, max_length=300)


class DeliveryIn(Strict):
    zone_id: uuid.UUID
    address: str = Field(min_length=3, max_length=500)
    landmark: str | None = Field(None, max_length=300)
    latitude: Decimal | None = Field(None, ge=-90, le=90)
    longitude: Decimal | None = Field(None, ge=-180, le=180)
    fee_override: Decimal | None = Field(None, ge=0, description="Needs delivery.fee_override; otherwise the zone rule sets the fee")


class OrderCreate(Strict):
    order_type: OrderType
    table_id: uuid.UUID | None = None
    table_tag: str | None = Field(None, max_length=10, description="Counter mode table number (FR-TBL-013)")
    guest_count: int | None = Field(None, ge=1, le=200)
    pickup_name: str | None = Field(None, max_length=60)
    customer_name: str | None = Field(None, max_length=120)
    customer_phone: str | None = Field(None, max_length=20)
    delivery_address: str | None = None
    delivery: DeliveryIn | None = Field(None, description="Required for delivery orders (BR-052)")
    scheduled_at: datetime | None = Field(None, description="Scheduled pickup or delivery time (FR-DLV-001)")
    note: str | None = Field(None, max_length=500)
    items: list[ItemIn] = []


class OrderUpdate(Strict):
    guest_count: int | None = Field(None, ge=1, le=200)
    pickup_name: str | None = Field(None, max_length=60)
    customer_name: str | None = Field(None, max_length=120)
    customer_phone: str | None = Field(None, max_length=20)
    delivery_address: str | None = None
    note: str | None = Field(None, max_length=500)
    table_tag: str | None = Field(None, max_length=10)
    version: int | None = None


class ItemUpdate(Strict):
    quantity: Decimal | None = Field(None, gt=0, le=999, decimal_places=3)
    seat_no: int | None = Field(None, ge=1, le=50)
    note: str | None = Field(None, max_length=300)


class CancelIn(Strict):
    reason: str = Field(min_length=2, max_length=300)
    approval_id: uuid.UUID | None = Field(None, description="Required for prepared items (BR-006)")


class HoldIn(Strict):
    label: str = Field(min_length=1, max_length=60)


class DiscountIn(Strict):
    order_item_id: uuid.UUID | None = Field(None, description="Null = order-level discount")
    kind: Literal["Percent", "Amount"]
    value: Decimal = Field(gt=0, decimal_places=4)
    reason: str = Field(min_length=2, max_length=200)
    approval_id: uuid.UUID | None = None


class TransferIn(Strict):
    table_id: uuid.UUID


class ServeIn(Strict):
    order_item_ids: list[uuid.UUID] | None = None


class ItemModifierOut(ORM):
    modifier_id: uuid.UUID
    name_snapshot: str
    price_delta_snapshot: Decimal


class OrderItemOut(ORM):
    id: uuid.UUID
    menu_item_id: uuid.UUID
    variant_id: uuid.UUID
    item_name_en_snapshot: str
    item_name_km_snapshot: str | None
    variant_name_snapshot: str
    unit_price_snapshot: Decimal
    modifiers_total: Decimal
    quantity: Decimal
    seat_no: int | None
    note: str | None
    is_allergy: bool
    station_code: str | None
    item_status: str
    void_type: str | None
    void_reason: str | None
    waste_outcome: str | None
    sent_at: datetime | None
    started_at: datetime | None
    ready_at: datetime | None
    served_at: datetime | None
    line_gross: Decimal
    line_discount: Decimal
    line_net: Decimal
    version: int
    modifiers: list[ItemModifierOut]


class DiscountOut(ORM):
    id: uuid.UUID
    order_item_id: uuid.UUID | None
    kind: str
    value: Decimal
    reason: str
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None
    promotion_id: uuid.UUID | None = None


class Totals(BaseModel):
    gross: Decimal
    discount_total: Decimal
    subtotal: Decimal
    service_charge: Decimal
    tax: Decimal
    delivery_fee: Decimal
    rounding: Decimal
    grand_total: Decimal
    paid: Decimal
    balance: Decimal
    currency: str


class OrderOut(BaseModel):
    id: uuid.UUID
    order_no: str
    business_date: date
    version: int
    order_type: str
    channel: str
    order_status: str
    kitchen_status: str
    payment_status: str
    table_id: uuid.UUID | None
    table_code: str | None
    table_tag: str | None
    guest_count: int | None
    pickup_name: str | None
    customer_name: str | None
    customer_phone: str | None
    delivery_address: str | None
    server_user_id: uuid.UUID
    note: str | None
    held_label: str | None
    scheduled_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    items: list[OrderItemOut]
    discounts: list[DiscountOut]
    totals: Totals


class OrderSummary(BaseModel):
    id: uuid.UUID
    order_no: str
    business_date: date
    order_type: str
    order_status: str
    kitchen_status: str
    payment_status: str
    table_code: str | None
    pickup_name: str | None
    server_user_id: uuid.UUID
    grand_total: Decimal
    created_at: datetime
    held_label: str | None


class SendOut(BaseModel):
    order_id: uuid.UUID
    tickets: list[dict]


class OrderEventOut(ORM):
    id: uuid.UUID
    event_type: str
    data: dict | None
    user_id: uuid.UUID | None
    occurred_at: datetime


class ItemStatusIn(Strict):
    status: Literal["InPreparation", "Ready", "Served", "Collected"]
    version: int | None = None


class PriorityIn(Strict):
    priority: int = Field(ge=0, le=9)


class WasteOutcomeIn(Strict):
    outcome: Literal["Wastage", "Reusable"]


class TicketItemOut(BaseModel):
    order_item_id: uuid.UUID
    name_en: str
    name_km: str | None
    variant: str
    quantity: Decimal
    modifiers: list[str]
    note: str | None
    is_allergy: bool
    status: str
    version: int
    void_type: str | None = None
    waste_outcome: str | None = None
    started_at: datetime | None = None
    ready_at: datetime | None = None


class TicketOut(BaseModel):
    ticket_id: uuid.UUID
    ticket_no: int
    ticket_type: str
    station_code: str
    priority: int
    order_id: uuid.UUID
    order_no: str
    order_type: str
    table_code: str | None
    pickup_name: str | None
    server_user_id: uuid.UUID
    created_at: datetime
    age_seconds: int
    items: list[TicketItemOut]
