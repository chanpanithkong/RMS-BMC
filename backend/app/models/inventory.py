"""Inventory ledger (SRS §10.4.13, 10.4.15; BR-015, BR-016, BR-040)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, Qty, Rate, TimestampMixin, VersionMixin, check_in

TXN_TYPES = ("OPENING", "RECEIPT", "RETURN_TO_SUPPLIER", "SALE_CONSUMPTION", "SALE_REVERSAL", "WASTE", "ISSUE", "TRANSFER_OUT", "TRANSFER_IN", "COUNT_ADJUSTMENT", "ADJUSTMENT", "REVERSAL")
POSITIVE = {"OPENING", "RECEIPT", "SALE_REVERSAL", "TRANSFER_IN"}
NEGATIVE = {"RETURN_TO_SUPPLIER", "SALE_CONSUMPTION", "WASTE", "ISSUE", "TRANSFER_OUT"}


class UnitOfMeasure(IdMixin, Base):
    __tablename__ = "units_of_measure"
    __table_args__ = (CheckConstraint(check_in("dimension", ("Mass", "Volume", "Count")), name="dimension"), CheckConstraint("factor_to_base > 0", name="factor"))
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(40))
    dimension: Mapped[str] = mapped_column(String(8))
    factor_to_base: Mapped[Decimal] = mapped_column(Rate)


class Ingredient(IdMixin, TimestampMixin, Base):
    __tablename__ = "ingredients"
    __table_args__ = (CheckConstraint("reorder_level >= 0 AND reorder_qty >= 0", name="reorder"),)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_km: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    stock_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    reorder_level: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))
    reorder_qty: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))
    track_batch: Mapped[bool] = mapped_column(Boolean, default=False)
    track_expiry: Mapped[bool] = mapped_column(Boolean, default=False)
    default_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inventory_locations.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_uom: Mapped[UnitOfMeasure] = relationship(lazy="joined")


class UnitConversion(IdMixin, Base):
    """Ingredient-specific cross-dimension conversion, e.g. 1 egg = 50 g (BR-015)."""

    __tablename__ = "unit_conversions"
    __table_args__ = (UniqueConstraint("ingredient_id", "from_uom_id", "to_uom_id"), CheckConstraint("factor > 0", name="factor"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    from_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    to_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    factor: Mapped[Decimal] = mapped_column(Rate)


class InventoryLocation(IdMixin, TimestampMixin, Base):
    __tablename__ = "inventory_locations"
    __table_args__ = (UniqueConstraint("branch_id", "name"),)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryTransaction(IdMixin, Base):
    """Append-only ledger. UPDATE/DELETE are rejected by a trigger (BR-016, FR-INV-003/004)."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        CheckConstraint(check_in("txn_type", TXN_TYPES), name="txn_type"),
        CheckConstraint("quantity <> 0", name="quantity"),
        UniqueConstraint("source_type", "source_line_id", "txn_type"),
        UniqueConstraint("reverses_txn_id"),
        Index("ix_inventory_transactions_item_loc_time", "ingredient_id", "location_id", "posted_at"),
        Index("ix_inventory_transactions_source", "source_type", "source_id"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    business_date: Mapped[date] = mapped_column(Date)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    txn_type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    total_cost: Mapped[Decimal]
    balance_after: Mapped[Decimal] = mapped_column(Qty)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[uuid.UUID]
    source_line_id: Mapped[uuid.UUID]
    reverses_txn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inventory_transactions.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    posted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StockBalance(VersionMixin, Base):
    """Derived from the ledger, updated in the same transaction (§10.6)."""

    __tablename__ = "stock_balances"
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"), primary_key=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class StockDocument(IdMixin, TimestampMixin, Base):
    """Stock receipt without PO, manual issue, adjustment or wastage. Posted exactly once (BR-016, BR-018, BR-019)."""

    __tablename__ = "stock_documents"
    __table_args__ = (
        UniqueConstraint("branch_id", "doc_no"),
        CheckConstraint(check_in("doc_type", ("Receipt", "Issue", "Adjustment", "Wastage", "Opening")), name="doc_type"),
        CheckConstraint(check_in("status", ("Draft", "PendingApproval", "Posted", "Rejected")), name="status"),
        CheckConstraint("approved_by IS NULL OR approved_by <> created_by", name="separation_of_duties"),
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    doc_no: Mapped[str] = mapped_column(String(24))
    doc_type: Mapped[str] = mapped_column(String(12))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventory_locations.id"))
    status: Mapped[str] = mapped_column(String(16), default="Draft")
    reason: Mapped[str | None] = mapped_column(Text)
    total_value: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None]
    lines: Mapped[list["StockDocumentLine"]] = relationship(lazy="selectin")


class StockDocumentLine(IdMixin, Base):
    __tablename__ = "stock_document_lines"
    __table_args__ = (CheckConstraint("quantity <> 0", name="quantity"),)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_documents.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(Qty)  # in uom_id; sign only meaningful for Adjustment
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units_of_measure.id"))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    batch_no: Mapped[str | None] = mapped_column(String(40))
    expiry_date: Mapped[date | None] = mapped_column(Date)
