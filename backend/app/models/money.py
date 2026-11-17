"""Bills, payments, refunds, receipts and cashier sessions (SRS §10.4.10, 10.4.11, 10.4.17)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, Rate, TimestampMixin, VersionMixin, check_in

BILL_STATUS = ("Open", "PartiallyPaid", "Paid", "Credit", "Void", "Refunded")
PAYMENT_STATE = ("Pending", "Confirmed", "Failed", "Voided")


class Bill(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("branch_id", "bill_no"),
        CheckConstraint(check_in("status", BILL_STATUS), name="status"),
        CheckConstraint("balance = total - paid_total", name="balance"),
        CheckConstraint("paid_total >= 0 AND refunded_total >= 0", name="non_negative"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date] = mapped_column(Date)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    bill_no: Mapped[str] = mapped_column(String(24))
    split_index: Mapped[int] = mapped_column(SmallInteger, default=1)
    split_count: Mapped[int] = mapped_column(SmallInteger, default=1)
    status: Mapped[str] = mapped_column(String(14), default="Open")
    gross_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    discount_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    subtotal: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    service_charge_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    delivery_fee: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    rounding_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    paid_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    refunded_total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    balance: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    printed_count: Mapped[int] = mapped_column(Integer, default=0)
    finalised_at: Mapped[datetime | None]

    lines: Mapped[list["BillLine"]] = relationship(lazy="selectin")
    charges: Mapped[list["BillCharge"]] = relationship(lazy="selectin")


class BillLine(IdMixin, Base):
    __tablename__ = "bill_lines"
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id"), index=True)
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id"))
    quantity_share: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    amount_gross: Mapped[Decimal]
    amount_discount: Mapped[Decimal]
    amount_net: Mapped[Decimal]


class BillCharge(IdMixin, Base):
    __tablename__ = "bill_charges"
    __table_args__ = (CheckConstraint(check_in("charge_type", ("ServiceCharge", "Tax", "Rounding", "DeliveryFee")), name="charge_type"),)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id"), index=True)
    charge_type: Mapped[str] = mapped_column(String(14))
    name: Mapped[str] = mapped_column(String(60))
    tax_profile_rate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tax_profile_rates.id"))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    base_amount: Mapped[Decimal]
    amount: Mapped[Decimal]


class AppliedDiscount(IdMixin, Base):
    __tablename__ = "applied_discounts"
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id"), index=True)
    order_discount_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_discounts.id"))
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_items.id"))
    amount: Mapped[Decimal]


class CashierSession(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "cashier_sessions"
    __table_args__ = (
        CheckConstraint(check_in("status", ("Open", "ClosingPendingApproval", "Closed", "ForceClosed")), name="status"),
        Index("uq_cashier_sessions_one_open", "branch_id", "user_id", unique=True, postgresql_where=text("status = 'Open'")),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))
    business_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="Open")
    opened_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]
    witness_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    variance_reason: Mapped[str | None] = mapped_column(Text)

    floats: Mapped[list["SessionFloat"]] = relationship(lazy="selectin")
    results: Mapped[list["SessionResult"]] = relationship(lazy="selectin")


class SessionFloat(Base):
    __tablename__ = "session_floats"
    __table_args__ = (CheckConstraint("amount >= 0", name="amount"),)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cashier_sessions.id"), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    amount: Mapped[Decimal]


class CashCount(IdMixin, Base):
    __tablename__ = "cash_counts"
    __table_args__ = (UniqueConstraint("session_id", "currency"), CheckConstraint("counted_amount >= 0", name="amount"))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cashier_sessions.id"))
    currency: Mapped[str] = mapped_column(String(3))
    counted_amount: Mapped[Decimal]
    denominations: Mapped[dict | None]
    counted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    counted_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SessionResult(Base):
    __tablename__ = "session_results"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cashier_sessions.id"), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    expected: Mapped[Decimal]
    counted: Mapped[Decimal]
    variance: Mapped[Decimal]


class CashMovement(IdMixin, Base):
    __tablename__ = "cash_movements"
    __table_args__ = (CheckConstraint(check_in("kind", ("PaidOut", "PaidIn", "Drop")), name="kind"), CheckConstraint("amount > 0", name="amount"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cashier_sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal]
    reason: Mapped[str] = mapped_column(Text)
    expense_id: Mapped[uuid.UUID | None]  # FK added with EXP (Phase 2)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Payment(IdMixin, Base):
    """Never edited or deleted; corrected by void/refund (BR-011, BR-022). No card data (A-17)."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(check_in("status", PAYMENT_STATE), name="status"),
        CheckConstraint("amount_applied > 0", name="amount_applied"),
        CheckConstraint("card_last4 IS NULL OR card_last4 ~ '^[0-9]{4}$'", name="card_last4"),
        UniqueConstraint("idempotency_key"),
        Index("uq_payments_method_ref", "method_id", "external_ref", unique=True, postgresql_where=text("external_ref IS NOT NULL")),
        Index("ix_payments_branch_date_method", "branch_id", "business_date", "method_id"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date] = mapped_column(Date)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id"), index=True)
    method_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_methods.id"))
    method_code: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    amount_tendered: Mapped[Decimal]
    amount_applied: Mapped[Decimal]
    change_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    change_currency: Mapped[str | None] = mapped_column(String(3))
    exchange_rate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exchange_rates.id"))
    rate: Mapped[Decimal | None] = mapped_column(Rate)
    amount_base: Mapped[Decimal]
    rounding_base: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    refunded_base: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(10), default="Confirmed")
    external_ref: Mapped[str | None] = mapped_column(String(80))
    approval_code: Mapped[str | None] = mapped_column(String(30))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    cashier_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cashier_sessions.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    received_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None] = mapped_column(Text)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class PaymentAllocation(IdMixin, Base):
    __tablename__ = "payment_allocations"
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id"), index=True)
    amount_base: Mapped[Decimal]


class Refund(IdMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint(check_in("status", ("Requested", "Completed", "Rejected")), name="status"),
        CheckConstraint("amount_base > 0", name="amount"),
        CheckConstraint("approved_by IS NULL OR approved_by <> requested_by", name="separation_of_duties"),
        Index("uq_refunds_idempotency", "idempotency_key", unique=True, postgresql_where=text("idempotency_key IS NOT NULL")),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date] = mapped_column(Date)
    refund_no: Mapped[str] = mapped_column(String(24))
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id"))
    amount_base: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal]
    method_code: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(10), default="Requested")
    cashier_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cashier_sessions.id"), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]


class Receipt(IdMixin, Base):
    __tablename__ = "receipts"
    __table_args__ = (UniqueConstraint("branch_id", "series", "receipt_no"), UniqueConstraint("bill_id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    series: Mapped[str] = mapped_column(String(10), default="R")
    receipt_no: Mapped[str] = mapped_column(String(30))
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id"))
    issued_at: Mapped[datetime] = mapped_column(server_default=func.now())
    issued_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reprint_count: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(5), default="en")
