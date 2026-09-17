"""
MovementSeries - numbering for stock movement documents (Entrada/Saida), same principle
as DocumentSeries for invoices but simpler: no AGT electronic-mode complexity, since a
stock movement is an internal document, never submitted to AGT. Series code format is
{movement_type.code}{year}, e.g. "ES2026" for a Saida in 2026 - matches the "ES 2026/2"
example given for the movement numbering scheme.
"""
import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class MovementSeries(Base):
    __tablename__ = "movement_series"
    __table_args__ = (
        UniqueConstraint("company_id", "movement_type_id", "year", name="uq_movement_series_company_type_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    movement_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("movement_types.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    # e.g. "ES2026" - {movement_type.code}{year}, mirroring the invoice DocumentSeries
    # MANUAL-mode format (see get_or_create_current_series / "{TIPO}{ANO}").
    series_code: Mapped[str] = mapped_column(String(20), nullable=False)
    current_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<MovementSeries {self.series_code}>"
