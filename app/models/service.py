"""
Service model - separate from Product (Video 3 decision: produtos e
servicos sao geridos em ecras distintos, com campos proprios - um servico
nao tem lote/stock/validade/codigo de barras, por exemplo).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, Boolean, DateTime, ForeignKey, Enum, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ProductServiceStatus(str, enum.Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"
    SUSPENSO = "SUSPENSO"
    BLOQUEADO = "BLOQUEADO"
    ESGOTADO = "ESGOTADO"
    DESCONTINUADO = "DESCONTINUADO"


class Service(Base):
    """A sellable service, scoped to a Company (tenant)."""
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_service_company_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    service_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("service_types.id"), nullable=True)
    # Optional link to a ResourceTypeCatalog entry (e.g. "Quarto 30min" only makes
    # sense for a CHAMBRE) - null means a generic service, sellable/bookable
    # regardless of resource type (e.g. "Lavandaria por Peca"). Used by
    # booking_service to filter which services are valid for a given booking's
    # resource, and to enforce ResourceTypeCatalog.requires_service.
    resource_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resource_type_catalog.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    unit_of_measure_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("unit_of_measure_catalog.id"), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    vat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vat_rates.id"), nullable=False)
    # Required whenever the selected VAT rate is 0% (isento) - see Product.exemption_reason_id.
    exemption_reason_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vat_codes.id"), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)  # marca
    withholding_tax_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("withholding_taxes.id"), nullable=True)
    subject_to_return: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # sujeito a devolucao
    not_available_pos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[ProductServiceStatus] = mapped_column(Enum(ProductServiceStatus, name="productservicestatus"), nullable=False, default=ProductServiceStatus.ACTIVO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Service {self.code} - {self.name}>"
