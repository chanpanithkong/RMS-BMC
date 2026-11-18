"""Phase 4 additions: menu schedules, combos, payment reconciliation, recurring expenses, report schedules, notification preferences."""
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, SmallInteger, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class MenuSchedule(IdMixin, TimestampMixin, Base):
    """FR-MENU-008 / BR-003: when scheduled items may be sold (days, time window, date range, branches). Items with no schedule are always sellable."""

    __tablename__ = "menu_schedules"
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"))
    name: Mapped[str] = mapped_column(String(80))
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=list)  # 0 = Monday; empty = every day
    time_from: Mapped[time | None] = mapped_column(Time)
    time_to: Mapped[time | None] = mapped_column(Time)
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    branch_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class MenuScheduleItem(Base):
    __tablename__ = "menu_schedule_items"
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_schedules.id"), primary_key=True)
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"), primary_key=True, index=True)


class ComboSlot(IdMixin, Base):
    """FR-MENU-005: one choice in a combo or set menu (e.g. Main, Drink), with the items that may fill it."""

    __tablename__ = "combo_slots"
    combo_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"), index=True)
    name_en: Mapped[str] = mapped_column(String(60))
    name_km: Mapped[str | None] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    min_select: Mapped[int] = mapped_column(SmallInteger, default=1)
    max_select: Mapped[int] = mapped_column(SmallInteger, default=1)


class ComboSlotOption(IdMixin, Base):
    __tablename__ = "combo_slot_options"
    __table_args__ = (UniqueConstraint("slot_id", "variant_id"),)
    slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("combo_slots.id"), index=True)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_item_variants.id"))
    price_delta: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)  # extra charge for this choice (e.g. large drink)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- payment reconciliation (FR-BILL-018)
class PaymentReconciliation(IdMixin, TimestampMixin, Base):
    """One business day and one electronic payment method, compared with the bank or provider statement. Closed = locked."""

    __tablename__ = "payment_reconciliations"
    __table_args__ = (UniqueConstraint("branch_id", "business_date", "method_code"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date] = mapped_column(Date)
    method_code: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(8), default="Open")  # Open | Closed
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None]


class ReconciliationLine(IdMixin, Base):
    """A statement entry typed or imported by the accountant. Payments themselves are never changed by reconciliation."""

    __tablename__ = "reconciliation_lines"
    __table_args__ = (UniqueConstraint("reconciliation_id", "reference"),)
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_reconciliations.id"), index=True)
    reference: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    received_at: Mapped[datetime | None]
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"), index=True)
    match_status: Mapped[str] = mapped_column(String(14))  # Matched | AmountMismatch | NotRecorded
    matched_manually: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- recurring expenses (FR-EXP-008)
class ExpenseTemplate(IdMixin, TimestampMixin, Base):
    """Generates a Draft expense on a schedule; a person still reviews and submits it."""

    __tablename__ = "expense_templates"
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String(80))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expense_categories.id"))
    description: Mapped[str] = mapped_column(Text)
    payee: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    frequency: Mapped[str] = mapped_column(String(8))  # Weekly | Monthly
    day_of_week: Mapped[int | None] = mapped_column(SmallInteger)  # 0 = Monday (Weekly)
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger)  # 1-28 (Monthly)
    next_run_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class ExpenseTemplateRun(Base):
    """One draft per template and date, so a repeated or overlapping run never creates a duplicate."""

    __tablename__ = "expense_template_runs"
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expense_templates.id"), primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, primary_key=True)
    expense_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expenses.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- scheduled report emails (FR-RPT-027)
class ReportSchedule(IdMixin, TimestampMixin, Base):
    """Runs a report for each recipient with that person's own permissions, then emails them a link (no report data in the email)."""

    __tablename__ = "report_schedules"
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    report_id: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))
    frequency: Mapped[str] = mapped_column(String(8))  # Daily | Weekly | Monthly
    day_of_week: Mapped[int | None] = mapped_column(SmallInteger)
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger)
    hour: Mapped[int] = mapped_column(SmallInteger, default=7)  # branch local time
    recipient_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    next_run_at: Mapped[datetime]
    last_run_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- notification preferences (FR-NOTIF-011)
class NotificationPreference(Base):
    """Only optional kinds can be switched off; mandatory ones (safety and money) are always delivered."""

    __tablename__ = "notification_preferences"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
