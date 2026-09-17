"""
DocumentSeries - one numbering series per (company, document type, year).
See decision on Video 4/8: always one row per document type - in MANUAL
mode all of a year's rows simply share the same series_code (either the
year itself, if "auto_series_year" is on, or a value the GESTOR typed
freely), while in ELETRONICA mode each row gets its own AGT-issued code
via a simulated "Solicitar Serie AGT" action, tied to an Establishment.

InvoiceNo format (SAF-T XSD requires the space): "{DocType} {series_code}/{number}",
e.g. manual "FT 2026/1", electronic "FT FT7826S4635N/1".
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import String, Integer, Boolean, Date, DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ContingencyIndicator(str, enum.Enum):
    NORMAL = "NORMAL"
    CONTINGENCIA = "CONTINGENCIA"


class DocumentSeries(Base):
    __tablename__ = "document_series"
    __table_args__ = (
        # issuance_mode is part of the uniqueness key: a company may legitimately hold two
        # rows for the same (doctype, year) - one MANUAL, one ELETRONICA - e.g. right after
        # switching modes, without the old row blocking creation of the new one.
        UniqueConstraint("company_id", "document_type_id", "year", "issuance_mode", name="uq_series_company_doctype_year_mode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    establishment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("establishments.id"), nullable=True)
    document_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_types.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    # Snapshotted from Company.issuance_mode at creation time - the reference series table
    # ("Modo Emissao" column) stores this explicitly per series rather than inferring it,
    # since a company could change modes later without retroactively altering past series.
    issuance_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    series_code: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    number_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    number_end: Mapped[int] = mapped_column(Integer, nullable=False, default=999999999)
    date_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_end: Mapped[date] = mapped_column(Date, nullable=False)
    contingency_indicator: Mapped[ContingencyIndicator | None] = mapped_column(Enum(ContingencyIndicator), nullable=True)
    is_predefined: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_facturacao: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_tesouraria: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_compras: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<DocumentSeries {self.series_code} ({self.year})>"
