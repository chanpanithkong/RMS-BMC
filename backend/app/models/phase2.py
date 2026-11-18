"""Phase 2 tables (SRS §10.2): customers, reservations, staff, expenses, recipes, counts, transfers, batches, purchasing, promotions."""
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, Time, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, TSTZRANGE, Range
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, Qty, TimestampMixin, VersionMixin, check_in


# ---------------------------------------------------------------- customers (CUST)
class Customer(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("uq_customers_phone", "phone_e164", unique=True, postgresql_where=text("phone_e164 IS NOT NULL AND merged_into_id IS NULL")),
        Index("ix_customers_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        CheckConstraint(check_in("classification", ("Regular", "VIP", "Corporate")), name="classification"),
        CheckConstraint("preferred_language IN ('en','km')", name="language"),
    )
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    preferred_language: Mapped[str] = mapped_column(String(2), default="km")
    classification: Mapped[str] = mapped_column(String(12), default="Regular")
    preferences: Mapped[str | None] = mapped_column(Text)
    allergy_notes: Mapped[str | None] = mapped_column(Text)
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None]
    consent_channel: Mapped[str | None] = mapped_column(String(20))
    no_show_count: Mapped[int] = mapped_column(Integer, default=0)
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    anonymised_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    addresses: Mapped[list["CustomerAddress"]] = relationship(lazy="selectin")


class CustomerAddress(IdMixin, Base):
    __tablename__ = "customer_addresses"
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    label: Mapped[str] = mapped_column(String(40), default="Home")
    address: Mapped[str] = mapped_column(Text)
    landmark: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- reservations (RSV)
class Reservation(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "table_reservations"
    __table_args__ = (
        CheckConstraint(check_in("status", ("Requested", "Confirmed", "Seated", "Completed", "Cancelled", "NoShow")), name="status"),
        CheckConstraint("party_size > 0", name="party_size"),
        Index("ix_table_reservations_branch_time", "branch_id", "reserved_at"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    guest_name: Mapped[str] = mapped_column(String(120))
    guest_phone: Mapped[str | None] = mapped_column(String(20))
    reserved_at: Mapped[datetime]
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, default=90)
    party_size: Mapped[int] = mapped_column(SmallInteger)
    reminder_sent_at: Mapped[datetime | None]  # FR-RSV-009 SMS reminder
    status: Mapped[str] = mapped_column(String(10), default="Confirmed")
    notes: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    tables: Mapped[list["ReservationTable"]] = relationship(lazy="selectin")


class ReservationTable(IdMixin, Base):
    """BR-028: EXCLUDE USING gist (table_id WITH =, slot WITH &&) WHERE active — added in the migration."""

    __tablename__ = "reservation_tables"
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("table_reservations.id"), index=True)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurant_tables.id"))
    slot: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WaitlistEntry(IdMixin, Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (CheckConstraint(check_in("status", ("Waiting", "Notified", "Seated", "Left")), name="status"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    party_name: Mapped[str] = mapped_column(String(80))
    party_size: Mapped[int] = mapped_column(SmallInteger)
    phone: Mapped[str | None] = mapped_column(String(20))
    quoted_minutes: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(10), default="Waiting")
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    notified_at: Mapped[datetime | None]
    seated_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- staff (STAFF)
class Department(IdMixin, Base):
    __tablename__ = "departments"
    name: Mapped[str] = mapped_column(String(60), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Position(IdMixin, Base):
    __tablename__ = "positions"
    name: Mapped[str] = mapped_column(String(60), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Employee(IdMixin, TimestampMixin, Base):
    """Separate from user accounts (BR-051)."""

    __tablename__ = "employees"
    __table_args__ = (CheckConstraint(check_in("status", ("Active", "Inactive")), name="status"),)
    employee_code: Mapped[str] = mapped_column(String(20), unique=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_km: Mapped[str | None] = mapped_column(String(120))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("positions.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(String(10), default="Active")
    start_date: Mapped[date] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(20))


class ShiftSchedule(IdMixin, Base):
    __tablename__ = "shift_schedules"
    __table_args__ = (CheckConstraint("end_time <> start_time", name="times"), Index("ix_shift_schedules_branch_date", "branch_id", "shift_date"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    shift_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    note: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Attendance(IdMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = (Index("uq_attendance_open", "employee_id", unique=True, postgresql_where=text("clock_out IS NULL")),)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    clock_in: Mapped[datetime] = mapped_column(server_default=func.now())
    clock_out: Mapped[datetime | None]


# ---------------------------------------------------------------- expenses (EXP)
class ExpenseCategory(IdMixin, Base):
    __tablename__ = "expense_categories"
    name_en: Mapped[str] = mapped_column(String(60), unique=True)
    name_km: Mapped[str | None] = mapped_column(String(60))
    attachment_required: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Expense(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint(check_in("status", ("Draft", "Submitted", "Approved", "Rejected", "Paid", "Reversed")), name="status"),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("approved_by IS NULL OR approved_by <> submitted_by", name="separation_of_duties"),
        Index("ix_expenses_branch_date", "branch_id", "expense_date"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    expense_no: Mapped[str] = mapped_column(String(24))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expense_categories.id"))
    expense_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3))
    amount_base: Mapped[Decimal]
    payee: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10), default="Draft")
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None]
    decision_reason: Mapped[str | None] = mapped_column(Text)
    payment_method: Mapped[str | None] = mapped_column(String(30))
    paid_at: Mapped[datetime | None]
    payment_ref: Mapped[str | None] = mapped_column(String(80))
    paid_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    attachments: Mapped[list["ExpenseAttachment"]] = relationship(lazy="selectin")


class ExpenseAttachment(IdMixin, Base):
    __tablename__ = "expense_attachments"
    expense_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expenses.id"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(120), unique=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- recipes (RCP)
class Recipe(IdMixin, TimestampMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (CheckConstraint("(variant_id IS NOT NULL)::int + (modifier_id IS NOT NULL)::int = 1", name="exactly_one_target"),
                      UniqueConstraint("variant_id"), UniqueConstraint("modifier_id"))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("menu_item_variants.id"))
    modifier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("modifiers.id"))
    name: Mapped[str] = mapped_column(String(150))
    versions: Mapped[list["RecipeVersion"]] = relationship(lazy="selectin", order_by="RecipeVersion.version_no")


class RecipeVersion(IdMixin, TimestampMixin, Base):
    """Published versions are immutable; the one in effect is the latest published with effective_from <= now (BR-041)."""

    __tablename__ = "recipe_versions"
    __table_args__ = (
        UniqueConstraint("recipe_id", "version_no"),
        CheckConstraint(check_in("status", ("Draft", "Published", "Retired")), name="status"),
        CheckConstraint("yield_qty > 0", name="yield"),
        Index("uq_recipe_versions_published_effective", "recipe_id", "effective_from", unique=True, postgresql_where=text("status = 'Published'")),
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipes.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="Draft")
    effective_from: Mapped[datetime | None]
    yield_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal("1"))
    method_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None]
    lines: Mapped[list["RecipeIngredient"]] = relationship(lazy="selectin")


class RecipeIngredient(IdMixin, Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity"), CheckConstraint("prep_loss_pct BETWEEN 0 AND 90 AND cook_loss_pct BETWEEN 0 AND 90", name="loss"))
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipe_versions.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    prep_loss_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    cook_loss_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))


# ---------------------------------------------------------------- inventory documents (INV advanced)
class StockCount(IdMixin, TimestampMixin, Base):
    __tablename__ = "stock_counts"
    __table_args__ = (CheckConstraint(check_in("status", ("Draft", "Submitted", "Posted", "Rejected")), name="status"),
                      CheckConstraint("approved_by IS NULL OR approved_by <> counted_by", name="separation_of_duties"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    count_no: Mapped[str] = mapped_column(String(24))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    status: Mapped[str] = mapped_column(String(10), default="Draft")
    counted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None]
    lines: Mapped[list["StockCountLine"]] = relationship(lazy="selectin")


class StockCountLine(IdMixin, Base):
    __tablename__ = "stock_count_lines"
    __table_args__ = (UniqueConstraint("count_id", "ingredient_id"),)
    count_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_counts.id"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    counted_qty: Mapped[Decimal | None] = mapped_column(Qty)  # stock unit
    system_qty: Mapped[Decimal | None] = mapped_column(Qty)  # snapshot at submit; hidden until then (blind count)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))


class StockTransfer(IdMixin, TimestampMixin, Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (CheckConstraint("from_location_id <> to_location_id", name="different_locations"),
                      CheckConstraint(check_in("status", ("Draft", "Posted")), name="status"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    transfer_no: Mapped[str] = mapped_column(String(24))
    from_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    to_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    status: Mapped[str] = mapped_column(String(10), default="Draft")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None]
    lines: Mapped[list["StockTransferLine"]] = relationship(lazy="selectin")


class StockTransferLine(IdMixin, Base):
    __tablename__ = "stock_transfer_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity"),)
    transfer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_transfers.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))


class StockBatch(IdMixin, Base):
    """Batch and expiry tracking (FR-INV-011)."""

    __tablename__ = "stock_batches"
    __table_args__ = (Index("ix_stock_batches_expiry", "branch_id", "expiry_date"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    batch_no: Mapped[str] = mapped_column(String(40))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    quantity_received: Mapped[Decimal] = mapped_column(Qty)
    source_type: Mapped[str] = mapped_column(String(30))
    source_line_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------- purchasing (PUR)
class Supplier(IdMixin, TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (CheckConstraint(check_in("status", ("Active", "Inactive")), name="status"),)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    contact_person: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    address: Mapped[str | None] = mapped_column(Text)
    tax_id: Mapped[str | None] = mapped_column(String(50))
    payment_terms: Mapped[str] = mapped_column(String(20), default="Net 30")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(10), default="Active")
    branch_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")  # FR-BRN-005: empty = shared by all branches


class SupplierItem(IdMixin, Base):
    __tablename__ = "supplier_items"
    __table_args__ = (UniqueConstraint("supplier_id", "ingredient_id"),)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)


PO_STATUS = ("Draft", "Submitted", "Approved", "Sent", "PartiallyReceived", "Received", "Closed", "Cancelled")


class PurchaseRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "purchase_requests"
    __table_args__ = (CheckConstraint(check_in("status", ("Submitted", "Approved", "Rejected", "Converted")), name="status"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    request_no: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(20), default="Manual")
    status: Mapped[str] = mapped_column(String(10), default="Submitted")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id"))
    lines: Mapped[list["PurchaseRequestLine"]] = relationship(lazy="selectin")


class PurchaseRequestLine(IdMixin, Base):
    __tablename__ = "purchase_request_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity"),)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_requests.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))


class PurchaseOrder(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("branch_id", "po_no"),
        CheckConstraint(check_in("status", PO_STATUS), name="status"),
        CheckConstraint("approved_by IS NULL OR approved_by <> created_by", name="separation_of_duties"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    po_no: Mapped[str] = mapped_column(String(24))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    status: Mapped[str] = mapped_column(String(18), default="Draft")
    delivery_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[list["PurchaseOrderItem"]] = relationship(lazy="selectin")


class PurchaseOrderItem(IdMixin, Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (CheckConstraint("qty_ordered > 0 AND unit_price >= 0 AND qty_received >= 0", name="quantities"),)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    qty_ordered: Mapped[Decimal] = mapped_column(Qty)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    qty_received: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))  # in the line's uom


class GoodsReceipt(IdMixin, TimestampMixin, Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (UniqueConstraint("branch_id", "gr_no"), CheckConstraint(check_in("status", ("Draft", "PendingApproval", "Posted", "Reversed")), name="status"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    gr_no: Mapped[str] = mapped_column(String(24))
    po_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    status: Mapped[str] = mapped_column(String(16), default="Draft")
    is_direct: Mapped[bool] = mapped_column(Boolean, default=False)
    exception_note: Mapped[str | None] = mapped_column(Text)
    total_value: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    received_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None]
    lines: Mapped[list["GoodsReceiptItem"]] = relationship(lazy="selectin")


class GoodsReceiptItem(IdMixin, Base):
    __tablename__ = "goods_receipt_items"
    __table_args__ = (CheckConstraint("qty_received >= 0 AND qty_rejected >= 0 AND unit_cost >= 0", name="quantities"),)
    gr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goods_receipts.id"), index=True)
    po_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_order_items.id"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    qty_received: Mapped[Decimal] = mapped_column(Qty)
    qty_rejected: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    batch_no: Mapped[str | None] = mapped_column(String(40))
    expiry_date: Mapped[date | None] = mapped_column(Date)


class PurchaseReturn(IdMixin, TimestampMixin, Base):
    __tablename__ = "purchase_returns"
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    return_no: Mapped[str] = mapped_column(String(24))
    gr_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goods_receipts.id"))
    reason: Mapped[str] = mapped_column(Text)
    total_value: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    lines: Mapped[list["PurchaseReturnLine"]] = relationship(lazy="selectin")


class PurchaseReturnLine(IdMixin, Base):
    __tablename__ = "purchase_return_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity"),)
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_returns.id"), index=True)
    gr_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goods_receipt_items.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)  # in the receipt line's uom


class SupplierInvoice(IdMixin, TimestampMixin, Base):
    __tablename__ = "supplier_invoices"
    __table_args__ = (UniqueConstraint("supplier_id", "invoice_no"),
                      CheckConstraint(check_in("match_status", ("Matched", "Difference", "ForReview")), name="match_status"),
                      CheckConstraint(check_in("status", ("Unpaid", "PartiallyPaid", "Paid")), name="status"),
                      CheckConstraint("amount > 0 AND paid_amount >= 0 AND paid_amount <= amount", name="amounts"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    invoice_no: Mapped[str] = mapped_column(String(40))
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    gr_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    matched_value: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    match_status: Mapped[str] = mapped_column(String(10), default="ForReview")
    status: Mapped[str] = mapped_column(String(14), default="Unpaid")
    paid_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class SupplierPayment(IdMixin, Base):
    __tablename__ = "supplier_payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount"),)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("supplier_invoices.id"), index=True)
    amount: Mapped[Decimal]
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(80))
    paid_at: Mapped[datetime] = mapped_column(server_default=func.now())
    paid_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- promotions (PROMO)
class Promotion(IdMixin, TimestampMixin, Base):
    __tablename__ = "promotions"
    __table_args__ = (
        CheckConstraint(check_in("promo_type", ("Percent", "Amount", "FixedPrice", "BuyXGetY")), name="promo_type"),
        CheckConstraint(check_in("scope", ("Order", "Item", "Category")), name="scope"),
        CheckConstraint("value >= 0", name="value"),
    )
    name: Mapped[str] = mapped_column(String(120))
    promo_type: Mapped[str] = mapped_column(String(12))
    scope: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal]
    target_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)  # menu item or category ids
    buy_qty: Mapped[int | None] = mapped_column(SmallInteger)
    get_qty: Mapped[int | None] = mapped_column(SmallInteger)
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime | None]
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=list)  # 0 = Monday; empty = every day
    time_from: Mapped[time | None] = mapped_column(Time)
    time_to: Mapped[time | None] = mapped_column(Time)
    order_types: Mapped[list[str]] = mapped_column(ARRAY(String(10)), default=list)
    classifications: Mapped[list[str]] = mapped_column(ARRAY(String(12)), default=list)
    branch_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)
    combinable: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class PromotionCode(IdMixin, Base):
    __tablename__ = "promotion_codes"
    __table_args__ = (Index("uq_promotion_codes_code", text("lower(code)"), unique=True), CheckConstraint("uses >= 0 AND (max_uses IS NULL OR uses <= max_uses)", name="uses"))
    promotion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("promotions.id"))
    code: Mapped[str] = mapped_column(String(30))
    max_uses: Mapped[int | None] = mapped_column(Integer)
    max_uses_per_customer: Mapped[int | None] = mapped_column(Integer)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PromotionRedemption(IdMixin, Base):
    __tablename__ = "promotion_redemptions"
    __table_args__ = (UniqueConstraint("code_id", "order_id"),)
    promotion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("promotions.id"))
    code_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("promotion_codes.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    cancelled_at: Mapped[datetime | None]
