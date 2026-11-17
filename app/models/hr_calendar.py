"""
Recursos Humanos, step 3a / 3b: the company's work calendar and its absence types - what an absence is counted on.

HrHoliday - a day off for everybody: a national holiday, a «ponte» (the Monday or Friday next to a holiday on a
Tuesday or Thursday), a tolerance decreed by the Government, a local holiday. Generated year by year from the law,
then changed by the company (a ponte that does not apply, a tolerance announced at the last minute).

AbsenceType - what an absence can be (holidays, sickness, marriage, mourning, maternity, unpaid leave, unjustified
absence...): its category, whether it is paid, whether it takes holiday days, whether it counts working days or
calendar days, the most days it may last, whether a document must justify it. The company's own list, given a
starting set to be confirmed by its accountant.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

HOLIDAY_KINDS = {"FERIADO": "Feriado nacional", "PONTE": "Ponte", "TOLERANCIA": "Tolerância de ponto", "LOCAL": "Feriado local"}
ABSENCE_CATEGORIES = {
    "FERIAS": "Férias",
    "JUSTIFICADA": "Falta justificada",
    "INJUSTIFICADA": "Falta injustificada",
    "LICENCA": "Licença",
}


class HrHoliday(Base):
    __tablename__ = "hr_holidays"
    __table_args__ = (UniqueConstraint("company_id", "day", name="uq_hr_holidays_day"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False, default="FERIADO")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AbsenceType(Base):
    __tablename__ = "hr_absence_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(15), nullable=False)  # ABSENCE_CATEGORIES
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    takes_holiday_days: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # counts against the holiday balance
    working_days: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # False: calendar days (maternity)
    max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # per absence; none: no limit
    requires_document: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
