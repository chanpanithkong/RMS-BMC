"""Phase 3 tables: multi-branch (BRN)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, Qty, TimestampMixin, check_in


class InterBranchTransfer(IdMixin, TimestampMixin, Base):
    """FR-BRN-006: dispatch at the source branch, in transit, received at the destination with variance."""

    __tablename__ = "inter_branch_transfers"
    __table_args__ = (
        UniqueConstraint("from_branch_id", "transfer_no"),
        CheckConstraint("from_branch_id <> to_branch_id", name="different_branches"),
        CheckConstraint(check_in("status", ("InTransit", "Received", "Cancelled")), name="status"),
    )
    transfer_no: Mapped[str] = mapped_column(String(24))
    from_branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    from_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    to_branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    to_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inventory_locations.id"))
    status: Mapped[str] = mapped_column(String(10), default="InTransit")
    note: Mapped[str | None] = mapped_column(Text)
    dispatched_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    dispatched_at: Mapped[datetime]
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[list["InterBranchTransferLine"]] = relationship(lazy="selectin", order_by="InterBranchTransferLine.id")


class InterBranchTransferLine(IdMixin, Base):
    __tablename__ = "inter_branch_transfer_lines"
    __table_args__ = (CheckConstraint("qty_dispatched > 0 AND (qty_received IS NULL OR qty_received >= 0)", name="quantities"),)
    transfer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inter_branch_transfers.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    qty_dispatched: Mapped[Decimal] = mapped_column(Qty)  # in the ingredient's stock unit
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))  # source weighted average cost at dispatch
    qty_received: Mapped[Decimal | None] = mapped_column(Qty)
    variance_reason: Mapped[str | None] = mapped_column(String(200))


# ---------------------------------------------------------------- delivery (DLV)
DELIVERY_STATUS = ("PendingAssignment", "Assigned", "OutForDelivery", "Delivered", "Failed", "Cancelled")


class DeliveryZone(IdMixin, TimestampMixin, Base):
    """FR-DLV-003: fee by zone, with an optional order value above which delivery is free and a minimum order."""

    __tablename__ = "delivery_zones"
    __table_args__ = (UniqueConstraint("branch_id", "name"), CheckConstraint("fee >= 0", name="fee"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String(60))
    fee: Mapped[Decimal]
    free_over: Mapped[Decimal | None]
    min_order: Mapped[Decimal | None]
    tax_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tax_profiles.id"))  # BR-044: the fee's own tax profile
    estimated_minutes: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True)


class Delivery(IdMixin, TimestampMixin, Base):
    """§10 'deliveries': one per delivery order, with an address snapshot, fee, rider and status timestamps."""

    __tablename__ = "deliveries"
    __table_args__ = (CheckConstraint(check_in("status", DELIVERY_STATUS), name="status"),)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("delivery_zones.id"))
    address: Mapped[str] = mapped_column(Text)
    landmark: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    phone: Mapped[str] = mapped_column(String(20))
    fee: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    fee_rule: Mapped[str] = mapped_column(String(20), default="Zone")  # Zone | FreeOver | Manual | Platform
    fee_overridden_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(18), default="PendingAssignment")
    rider_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_at: Mapped[datetime | None]
    out_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    failed_at: Mapped[datetime | None]
    failure_reason: Mapped[str | None] = mapped_column(Text)
    recipient_name: Mapped[str | None] = mapped_column(String(120))
    proof_path: Mapped[str | None] = mapped_column(String(300))


class PlatformOrder(IdMixin, TimestampMixin, Base):
    """FR-DLV-007, BR-044: third-party platform order with its reference and commission (a cost, never a discount)."""

    __tablename__ = "platform_orders"
    __table_args__ = (UniqueConstraint("platform", "platform_ref"), CheckConstraint(check_in("settlement_status", ("Unsettled", "Settled", "Disputed")), name="settlement_status"),
                      CheckConstraint("commission_amount >= 0", name="commission"))
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30))
    platform_ref: Mapped[str] = mapped_column(String(60))
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    commission_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    settlement_status: Mapped[str] = mapped_column(String(10), default="Unsettled")
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform_settlements.id"))


class PlatformSettlement(IdMixin, TimestampMixin, Base):
    """FR-DLV-010: a platform payout statement, reconciled line by line against recorded platform orders."""

    __tablename__ = "platform_settlements"
    __table_args__ = (UniqueConstraint("platform", "statement_ref"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    platform: Mapped[str] = mapped_column(String(30))
    statement_ref: Mapped[str] = mapped_column(String(60))
    period_from: Mapped[date]
    period_to: Mapped[date]
    amount_paid: Mapped[Decimal]
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    lines: Mapped[list["PlatformSettlementLine"]] = relationship(lazy="selectin", order_by="PlatformSettlementLine.id")


class PlatformSettlementLine(IdMixin, Base):
    __tablename__ = "platform_settlement_lines"
    settlement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform_settlements.id"), index=True)
    platform_ref: Mapped[str] = mapped_column(String(60))
    gross: Mapped[Decimal]
    commission: Mapped[Decimal]
    net: Mapped[Decimal]
    platform_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform_orders.id"))


# ---------------------------------------------------------------- online and QR ordering (ONL)
class OnlineOrder(IdMixin, TimestampMixin, Base):
    """FR-ONL-003..011: an order placed from the public menu or a table QR code, with its acceptance and payment state."""

    __tablename__ = "online_orders"
    __table_args__ = (
        CheckConstraint(check_in("source", ("Online", "QR")), name="source"),
        CheckConstraint(check_in("fulfilment", ("Pickup", "Delivery", "DineIn")), name="fulfilment"),
        CheckConstraint(check_in("status", ("Received", "Accepted", "Rejected")), name="status"),
        CheckConstraint(check_in("payment_mode", ("Online", "PayLater")), name="payment_mode"),
        CheckConstraint(check_in("payment_status", ("NotRequired", "Pending", "Paid", "Failed")), name="payment_status"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    source: Mapped[str] = mapped_column(String(6))
    fulfilment: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(8), default="Received")
    customer_email: Mapped[str | None] = mapped_column(String(254))
    payment_mode: Mapped[str] = mapped_column(String(8), default="PayLater")
    payment_status: Mapped[str] = mapped_column(String(11), default="NotRequired")
    gateway: Mapped[str | None] = mapped_column(String(20))
    gateway_session: Mapped[str | None] = mapped_column(String(80), unique=True)
    gateway_txn: Mapped[str | None] = mapped_column(String(80))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None]
    reject_reason: Mapped[str | None] = mapped_column(Text)


class TrackingToken(IdMixin, Base):
    """FR-ONL-009, BR-046: unguessable, time-limited order tracking links. Only the SHA-256 of the token is stored."""

    __tablename__ = "tracking_tokens"
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
