"""
CustomerOrder (Encomenda) - what a customer orders to be made and handed over later (a birthday cake, bread for a
party, a catering order): who, when and how it is delivered, its lines with a production note each, and where it
stands (ENCOMENDADA -> EM_PRODUCAO -> PRONTA -> ENTREGUE, or CANCELADA with its reason). An internal, non-fiscal
document numbered ENC<year>/n per company; the money goes through the usual documents (FT + Recibo for a deposit,
Recibo or FR at the delivery, NC when cancelled after its FT) - capability ORDERS.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CustomerOrderStatus(str, enum.Enum):
    ENCOMENDADA = "ENCOMENDADA"
    EM_PRODUCAO = "EM_PRODUCAO"
    PRONTA = "PRONTA"
    ENTREGUE = "ENTREGUE"
    CANCELADA = "CANCELADA"


DELIVERY_PICKUP = "LOJA"  # the customer comes to fetch it
DELIVERY_DELIVERY = "ENTREGA"  # taken to the address


class CustomerOrder(Base):
    __tablename__ = "customer_orders"
    __table_args__ = (UniqueConstraint("company_id", "year", "number", name="uq_customer_orders_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)  # who comes / receives, if not the customer
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    delivery_mode: Mapped[str] = mapped_column(String(10), nullable=False, default=DELIVERY_PICKUP)  # LOJA | ENTREGA
    delivery_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[CustomerOrderStatus] = mapped_column(
        SQLEnum(CustomerOrderStatus, name="customer_order_status"), nullable=False, default=CustomerOrderStatus.ENCOMENDADA)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # the money: its Fatura (FT with a deposit / delivered on credit, or the FR of a delivery paid at once) - the
    # receipts (RC) reference it; a cancelled order's credit note, and what was done with the deposit
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    credit_note_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    deposit_outcome: Mapped[str | None] = mapped_column(String(12), nullable=True)  # DEVOLVIDO | RETIDO (cancelled)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CustomerOrderLine(Base):
    __tablename__ = "customer_order_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_orders.id", ondelete="CASCADE"),
                                                nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)  # the article's name when ordered
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # without VAT
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)  # the article's rate when ordered
    production_note: Mapped[str | None] = mapped_column(String(500), nullable=True)  # «Parabéns Ana 30 anos»
