"""
StockMovementDocument - a real, numbered, printable document (Entrada/Saida) recording
stock coming in or out of a warehouse (see PARTIE1&2 GESTAO DE STOCK notes: "ce sont des
documents comme avec les factures"). DISTINCT from StockMovement (stock_movement.py),
which is the low-level per-product audit ledger row - creating one of these documents is
expected to also write the corresponding StockMovement ledger rows for traceability.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import String, Numeric, Integer, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class StockMovementDocument(Base):
    __tablename__ = "stock_movement_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    movement_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("movement_types.id"), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    # Optional - set on a supplier receipt (Guia de Entrada), left null on an
    # internal transfer between the company's own warehouses (e.g. Armazem
    # Principal -> Hotel), which isn't a purchase. See Supplier model docstring.
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True, index=True)

    series: Mapped[str] = mapped_column(String(20), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)

    total_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    total_value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<StockMovementDocument {self.series}/{self.number}>"


class StockMovementDocumentLine(Base):
    __tablename__ = "stock_movement_document_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_movement_documents.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)

    product_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # The unit the line was entered in (10 SC): quantity and prices per that unit, stock moved quantity x unit_factor.
    sale_unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_sale_units.id"), nullable=True)
    unit_factor: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=1, server_default="1")

    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    purchase_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    sale_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    def __repr__(self) -> str:
        return f"<StockMovementDocumentLine {self.product_code_snapshot} x{self.quantity}>"
