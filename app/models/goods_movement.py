"""
GoodsMovement / GoodsMovementLine - the documents that travel with the goods (SAF-T MovementOfGoods), issued by the
company like an invoice: an AGT series per document type (GR2026/1), a hash and an ATCUD.

- GR, Guia de Remessa: goods sent to a customer, invoiced later - the stock leaves the warehouse with the guide; the
  invoice made from it (step 1b) does not take it out again.
- GT, Guia de Transporte: goods travelling between two warehouses of the company - a transfer.
- GD, Guia de Devolução: goods returned to a supplier (optionally referring to its purchase invoice) - a stock exit.

Each has the start of the transport (date and time, required by the SAF-T), where the goods are loaded and unloaded,
the vehicle. Never deleted: a guide is cancelled (ANULADA) with its reason and its stock comes back; an invoiced GR
cannot be cancelled.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GoodsMovementStatus(str, enum.Enum):
    EMITIDA = "EMITIDA"
    FATURADA = "FATURADA"  # a GR invoiced (SAF-T MovementStatus F)
    ANULADA = "ANULADA"


class GoodsMovement(Base):
    __tablename__ = "goods_movements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    document_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_types.id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(2), nullable=False)  # GR, GT, GD
    series: Mapped[str] = mapped_column(String(30), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_periods.id"), nullable=False, index=True)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # start of the transport

    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)  # GR
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True, index=True)  # GD
    purchase_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_invoices.id"), nullable=True)  # GD
    origin_warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    destination_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=True)  # GT
    load_address: Mapped[str] = mapped_column(String(250), nullable=False)
    unload_address: Mapped[str] = mapped_column(String(250), nullable=False)
    vehicle_plate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)

    net_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    vat_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    gross_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    atcud: Mapped[str] = mapped_column(String(50), nullable=False)
    document_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[GoodsMovementStatus] = mapped_column(Enum(GoodsMovementStatus), nullable=False, default=GoodsMovementStatus.EMITIDA)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)  # a GR invoiced
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GoodsMovementLine(Base):
    __tablename__ = "goods_movement_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goods_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("goods_movements.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    sale_unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_sale_units.id"), nullable=True)
    unit_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_factor: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=1)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)  # without VAT, per unit of the line
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(3), nullable=False)
    exemption_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    exemption_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line_net: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_vat: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
