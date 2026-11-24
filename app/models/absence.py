"""
Recursos Humanos, step 3c: an employee's absence - holidays, sickness, marriage, unpaid leave, unjustified absence -
from one day to another (or half a day), with the days it counts (working or calendar days, by its type, without the
holidays), the reason, the justifying document, and where it stands:

    PEDIDA  -> APROVADA | RECUSADA          (registered already approved by who may approve)
    PEDIDA / APROVADA -> CANCELADA

Only an approved absence counts: in the holiday balance (step 3d) and in the month's variables of the payslip (3e).
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AbsenceStatus(str, enum.Enum):
    PEDIDA = "PEDIDA"
    APROVADA = "APROVADA"
    RECUSADA = "RECUSADA"
    CANCELADA = "CANCELADA"


class Absence(Base):
    __tablename__ = "hr_absences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"),
                                                   nullable=False, index=True)
    type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hr_absence_types.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    half_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # one day only
    days: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)  # as counted when registered
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employee_files.id", ondelete="SET NULL"),
                                                          nullable=True)
    status: Mapped[AbsenceStatus] = mapped_column(SQLEnum(AbsenceStatus, name="absence_status"), nullable=False,
                                                  default=AbsenceStatus.PEDIDA)
    decision_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VacationAdjustment(Base):
    """A correction of an employee's holiday balance for a year: the balance brought from before RM SOFT, days given
    or taken by agreement - with its reason and who made it."""
    __tablename__ = "hr_vacation_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"),
                                                   nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    days: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)  # + given, - taken away
    note: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
