"""
Customer model.
See specification v6/v7, section 4.1: "Gestion des Clients avec NIF ;
blocage de la vente si le NIF obligatoire n'est pas renseigne".
Extended (Video 2) with the 2-tab fields observed in the reference
legalized software: identificacao, dados fiscais.

Consumidor Final: per the official SAF-T (AO) XSD (CustomerTaxID
documentation), the generic "Consumidor final" customer MUST use NIF
"999999999" for AGT compliance - the reference software's "CF" is a
display label over that same underlying value, not a literal stored NIF.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Enum, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models.company import LegalPersonType

FINAL_CONSUMER_NIF = "999999999"


class CustomerStatus(str, enum.Enum):
    ACTIVO = "ACTIVO"
    APROVADO = "APROVADO"
    BLOQUEADO = "BLOQUEADO"
    ELIMINADO = "ELIMINADO"
    INACTIVO = "INACTIVO"
    NAO_APROVADO = "NAO_APROVADO"
    POR_ACTIVAR = "POR_ACTIVAR"
    POR_AVALIAR = "POR_AVALIAR"
    SUSPENSO = "SUSPENSO"


class Customer(Base):
    """
    A billing customer, scoped to a Company (tenant).
    NIF is required - AGT invoicing cannot proceed without it (section 4.1 v6/v7).
    """
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("company_id", "nif", name="uq_customer_company_nif"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Identificacao (onglet 1)
    customer_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    legal_person_type: Mapped[LegalPersonType] = mapped_column(Enum(LegalPersonType), nullable=False, default=LegalPersonType.JURIDICA)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nif: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_final_consumer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    registration_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    # Dados fiscais (onglet 2)
    fiscal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # denominacao fiscal
    currency_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=True)
    country_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("countries.id"), nullable=True)
    province_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("provinces.id"), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)  # morada
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_terms.id"), nullable=True)
    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_method_catalog.id"), nullable=True)
    # Only meaningful for pessoa coletiva (Video 2 note).
    withholding_tax_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("withholding_taxes.id"), nullable=True)

    status: Mapped[CustomerStatus] = mapped_column(Enum(CustomerStatus), nullable=False, default=CustomerStatus.ACTIVO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Customer {self.name} (NIF={self.nif})>"