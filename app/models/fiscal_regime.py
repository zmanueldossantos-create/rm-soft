"""
Fiscal regime reference table - platform-wide (not company-scoped), managed
by SUPER_ADMIN. Angola's tax law defines several VAT regimes (Regime Geral,
Regime de Exclusao, Regime Simplificado, and possibly others) that each
permit a different subset of VAT rates - see discussion following a real
support conversation with Kiami (an AGT-certified vendor): a company under
Regime de Exclusao cannot even be offered the 14% (NOR) rate, for example.

Rather than hardcoding these categories and their allowed rates in code
(risking an incorrect assumption about Angolan tax law), SUPER_ADMIN
manages the list of regimes and which rates each one allows here - fully
editable, and new regimes can be added without a code change.
"""
from sqlalchemy import ForeignKey
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class FiscalRegime(Base):
    __tablename__ = "fiscal_regimes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Which SAF-T TaxCode categories a company under this regime may use.
    # Kept as simple booleans (matching our current 3 real rates in use,
    # section on SAF-T TaxTable) rather than a free-form list, for clarity.
    allows_nor: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 14% Taxa normal
    allows_red: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 5% Taxa reduzida
    allows_ise: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 0% Isento
    # INT (Taxa Intermedia) and OUT (Outros - special regimes) have no fixed
    # canonical percentage in our system - when a regime allows one of these,
    # SUPER_ADMIN must still manually add the company's specific VAT rate
    # value via the VAT management screen; this flag only controls whether
    # the category is permitted for that regime, not its percentage.
    allows_int: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Exemption motive every exempt article must carry under this regime (M00 Simplificado, M04 Exclusao) - set
    # by the SUPER_ADMIN, never written in the code; None = each article chooses its own motive.
    required_exemption_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vat_codes.id"), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<FiscalRegime {self.name}>"

# Case-insensitive uniqueness (migration h1k8l3m72x04): no duplicate whatever the case. Declared here too, so a
# database built from the models (tests, new installs) has the same protection as a migrated one.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_fiscal_regimes_name_ci", _func.lower(FiscalRegime.name), unique=True)
