"""
Company model - root of the multi-tenant hierarchy.
See specification v7, section 2.8 (Entity hierarchy), extended with the
fields observed in the reference legalized software (Video 1: 3 tabs -
dados da empresa, informacoes fiscais, coordenadas bancarias).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class LegalPersonType(str, enum.Enum):
    JURIDICA = "JURIDICA"  # pessoa coletiva (company)
    FISICA = "FISICA"      # pessoa singular (individual)


class InvoiceIssuanceMode(str, enum.Enum):
    MANUAL = "MANUAL"
    ELETRONICA = "ELETRONICA"


class Company(Base):
    """
    Client company (tenant).
    Local mode: a single active Company per installation.
    SaaS mode: multiple Company rows isolated within the same database (section 2.5 v7).
    """
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)  # denominacao fiscal
    # Short/display name (nome curto) - falls back to `name` in the UI when not set.
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    legal_person_type: Mapped[LegalPersonType] = mapped_column(Enum(LegalPersonType), nullable=False, default=LegalPersonType.JURIDICA)
    nif: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)  # phone 1
    phone_number_2: Mapped[str | None] = mapped_column(String(20), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)  # morada
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)  # cidade
    province_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("provinces.id"), nullable=True)
    municipality_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("municipalities.id"), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Numero de registo comercial - required for SAF-T CompanyID (section on SAF-T generator), not required at creation.
    commercial_registration_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Currencies - a currency already picked in one slot can't appear in the other (enforced at service layer).
    primary_currency_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=True)
    secondary_currency_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=True)

    # Determines which VAT rates (NOR/RED/ISE) this company may use - see FiscalRegime.
    # Nullable for now (existing companies predate this field) - set by SUPER_ADMIN at creation.
    fiscal_regime_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_regimes.id"), nullable=True)

    # Invoicing behaviour toggles (Video 1) - the 3 sub-toggles only matter/show in the
    # UI when uses_invoicing is True; they stay at their default otherwise.
    uses_invoicing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_series_year: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allows_future_sale_date: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suggests_last_document_date: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Sale unit consistency checks, each 'off' / 'warn' (confirm explicitly) / 'block' - see product_sale_unit_service.
    sale_unit_check_above_base: Mapped[str] = mapped_column(String(5), default="warn", server_default="warn", nullable=False)
    sale_unit_check_below_cost: Mapped[str] = mapped_column(String(5), default="warn", server_default="warn", nullable=False)
    sale_unit_check_same_factor: Mapped[str] = mapped_column(String(5), default="warn", server_default="warn", nullable=False)

    # Fiscal issuance mode - electronic mode requires the AGT-issued private
    # key and turns OFF auto_series_year (series are solicited from AGT instead).
    issuance_mode: Mapped[InvoiceIssuanceMode] = mapped_column(Enum(InvoiceIssuanceMode), nullable=False, default=InvoiceIssuanceMode.MANUAL)
    electronic_signature_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Company {self.name} (NIF={self.nif})>"