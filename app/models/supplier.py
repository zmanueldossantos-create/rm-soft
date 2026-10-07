"""
Supplier model (Fornecedor) - an external entity the company purchases stock
from. The purchase-side counterpart to Customer, deliberately much simpler:
no AGT NIF requirement (a supplier receipt/Guia de Entrada is NOT a
regulated MovementType per the SAF-T Angola XSD - only GR/GT/GA/GD
outbound movements are - see the "Guia de Entrada e documento fiscal?"
discussion), so none of Customer's fiscal-compliance fields apply here.

v1 scope is intentionally minimal - a catalog + linking suppliers to
StockMovementDocument (Guia de Entrada) for traceability. No purchase-order
workflow, no accounts-payable/payment tracking, no delivery/logistics
tracking - those would be separate future chantiers if the need arises.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_supplier_company_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)  # free text v1 - e.g. "30 dias", "a vista"
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Supplier {self.name}>"
