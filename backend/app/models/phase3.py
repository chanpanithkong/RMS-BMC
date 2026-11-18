"""Phase 3 tables: multi-branch (BRN)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
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
                      CheckConstraint(check_in("acceptance", ("Received", "Accepted", "Rejected")), name="acceptance"),
                      CheckConstraint("commission_amount >= 0", name="commission"))
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30))
    platform_ref: Mapped[str] = mapped_column(String(60))
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    commission_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    settlement_status: Mapped[str] = mapped_column(String(10), default="Unsettled")
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform_settlements.id"))
    # Imported orders (GrabFood): acceptance by staff, the platform's own state and totals as the platform sent them
    acceptance: Mapped[str] = mapped_column(String(10), default="Accepted", server_default="Accepted")  # Received | Accepted | Rejected
    accept_mode: Mapped[str | None] = mapped_column(String(8))  # AUTO | MANUAL (platform setting)
    external_state: Mapped[str | None] = mapped_column(String(20))
    platform_short_no: Mapped[str | None] = mapped_column(String(30))
    platform_total_minor: Mapped[int | None]
    platform_currency: Mapped[str | None] = mapped_column(String(3))
    platform_exponent: Mapped[int | None]
    payment_type: Mapped[str | None] = mapped_column(String(10))
    mismatch_note: Mapped[str | None] = mapped_column(Text)
    ready_marked_at: Mapped[datetime | None]


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
    gateway_payload: Mapped[str | None] = mapped_column(Text)  # the KHQR string shown to the customer
    gateway_expires_at: Mapped[datetime | None]
    gateway_checked_at: Mapped[datetime | None]
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


# ---------------------------------------------------------------- loyalty (FR-PROMO-011, FR-CUST-008, D-14)
class LoyaltyTransaction(IdMixin, Base):
    """Append-only points ledger. Earn rows are lots: `remaining` is used oldest-first and expires at `expires_at`."""

    __tablename__ = "loyalty_transactions"
    __table_args__ = (
        CheckConstraint(check_in("kind", ("Earn", "Redeem", "RedeemReversal", "Clawback", "Expire", "Adjust")), name="kind"),
        CheckConstraint("points <> 0", name="points"),
        CheckConstraint("remaining IS NULL OR remaining >= 0", name="remaining"),
        Index("uq_loyalty_earn_per_order", "order_id", unique=True, postgresql_where=text("kind = 'Earn'")),
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"), index=True)
    discount_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_discounts.id"), index=True)
    refund_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refunds.id"))
    kind: Mapped[str] = mapped_column(String(14))
    points: Mapped[int]
    remaining: Mapped[int | None]  # Earn and positive Adjust lots only
    expires_at: Mapped[datetime | None]
    value: Mapped[Decimal | None]  # money value of a redemption
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- SMS and customer accounts (NOTIF external, FR-ONL-004/010, FR-RSV-009)
class SmsMessage(IdMixin, Base):
    """Every customer text message: queued here, sent by the worker with retries, never sent twice for the same purpose."""

    __tablename__ = "sms_messages"
    __table_args__ = (
        CheckConstraint(check_in("status", ("Queued", "Sent", "Failed", "Logged")), name="status"),
        Index("uq_sms_messages_dedupe", "dedupe_key", unique=True, postgresql_where=text("dedupe_key IS NOT NULL")),
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    to_msisdn: Mapped[str] = mapped_column(String(20))  # 855XXXXXXXX, no '+'
    purpose: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(8), default="Queued")
    attempts: Mapped[int] = mapped_column(default=0)
    provider: Mapped[str | None] = mapped_column(String(20))
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None]  # exponential back-off after a failure (FR-NOTIF-013)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_at: Mapped[datetime | None]


class PhoneVerification(IdMixin, Base):
    """One-time sign-in code sent by SMS. Only a hash is stored; 10 minutes, 5 tries."""

    __tablename__ = "phone_verifications"
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CustomerSession(IdMixin, Base):
    """Signed-in online customer (FR-ONL-004). Opaque token; only its SHA-256 is stored."""

    __tablename__ = "customer_sessions"
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- delivery platform import: GrabFood (D-13)
class PlatformItemMap(IdMixin, Base):
    """Platform menu IDs -> RMS variant or modifier. Without a row, RMS IDs are used directly as the platform's external IDs."""

    __tablename__ = "platform_item_maps"
    __table_args__ = (UniqueConstraint("platform", "external_id"),
                      CheckConstraint("(variant_id IS NULL) <> (modifier_id IS NULL)", name="one_target"))
    platform: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(64))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("menu_item_variants.id"))
    modifier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("modifiers.id"))


class PlatformInbound(IdMixin, Base):
    """Every webhook a platform sends, kept as received for audit and manual handling."""

    __tablename__ = "platform_inbound"
    platform: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(30))
    external_order_id: Mapped[str | None] = mapped_column(String(80), index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    payload: Mapped[dict] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- customer credit accounts (FR-CUST-011, FR-BILL-017, BR-036, D-07)
class CreditAccount(IdMixin, TimestampMixin, Base):
    """Pay-later account for an approved customer or company. Balance = what the customer owes."""

    __tablename__ = "credit_accounts"
    __table_args__ = (CheckConstraint(check_in("status", ("Active", "Suspended", "Closed")), name="status"), CheckConstraint("credit_limit >= 0", name="limit"),
                      CheckConstraint("terms_days BETWEEN 0 AND 365", name="terms"))
    account_no: Mapped[str] = mapped_column(String(20), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), unique=True)
    company_name: Mapped[str | None] = mapped_column(String(120))
    billing_contact: Mapped[str | None] = mapped_column(String(120))
    credit_limit: Mapped[Decimal]
    terms_days: Mapped[int] = mapped_column(default=30)
    balance: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(10), default="Active")
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)


class CreditTransaction(IdMixin, Base):
    """Append-only account ledger. Charges carry a due date and an open amount that settlements and credits reduce oldest-first."""

    __tablename__ = "credit_transactions"
    __table_args__ = (CheckConstraint(check_in("kind", ("Charge", "Settlement", "Credit", "Reversal", "Adjustment")), name="kind"),
                      CheckConstraint("amount <> 0", name="amount"), CheckConstraint("open_amount IS NULL OR open_amount >= 0", name="open_amount"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_accounts.id"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date]
    txn_no: Mapped[str] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal]  # + increases what the customer owes, - reduces it
    open_amount: Mapped[Decimal | None]  # charges only
    due_date: Mapped[date | None]
    bill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bills.id"))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    refund_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refunds.id"))
    method_code: Mapped[str | None] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- analytics (SRS §12 reporting architecture, NFR-PERF-008/009)
class AnalyticsDaily(Base):
    """Daily summary per branch: one row per business day, dimension (item, category, hour, method, employee, ingredient) and key.
    Rebuilt for a day at day-end and refreshed during the day; never edited by hand."""

    __tablename__ = "analytics_daily"
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), primary_key=True)
    business_date: Mapped[date] = mapped_column(primary_key=True)
    dimension: Mapped[str] = mapped_column(String(12), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(160))
    group_label: Mapped[str | None] = mapped_column(String(80))  # e.g. the item's category
    count: Mapped[int] = mapped_column(default=0)  # orders, payments
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    gross: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    discount: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    net: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    cost: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    refreshed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportJob(IdMixin, Base):
    """NFR-PERF-009: a long report run by the worker into a CSV file, downloadable by the requester until it expires."""

    __tablename__ = "report_jobs"
    __table_args__ = (CheckConstraint(check_in("status", ("Queued", "Running", "Done", "Failed")), name="status"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    report_id: Mapped[str] = mapped_column(String(20))
    params: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(8), default="Queued")
    rows: Mapped[int | None]
    file_name: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
