"""
Recursos Humanos - the payroll settings of a company (step 2: everything the salary calculation reads, nothing coded):

PayrollSettings - one per company: the INSS rates (employee / employer), the hours and days of a month (hourly and
daily value), whether the employee's INSS is deducted from the IRT base, the working days of the week.

IrtTable - the IRT table, valid from a date: its brackets (from, to, fixed amount, rate, applied above). A new law
(the next OGE, the IRPS) is a new table from its date; the months already paid keep theirs.

PayrollItem (rubrica) - an amount of the payslip: an allowance (ABONO) or a deduction (DESCONTO), computed as a fixed
amount, a percentage of the base salary, a formula, or typed each month; whether it enters the INSS base and the IRT
base, and the part of it exempt from IRT (an allowance above its limit is taxed on the excess). For a deduction the
same two boxes mean «reduces the base» (an unpaid absence).

A rubrica applies to every employee or only to those it is given to; one typed each month (MENSAL) applies to whoever
gets a value that month.

EmployeePayrollItem - a rubrica given to one employee, with his own amount or rate (the transport allowance of
15 000 Kz of this one).
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

NATURE_ALLOWANCE = "ABONO"
NATURE_DEDUCTION = "DESCONTO"
NATURES = {NATURE_ALLOWANCE: "Abono", NATURE_DEDUCTION: "Desconto"}
CALC_METHODS = {
    "FIXO": "Valor fixo",
    "PERCENTAGEM": "Percentagem do salário base",
    "FORMULA": "Fórmula",
    "MENSAL": "Valor indicado em cada mês",
}


class PayrollSettings(Base):
    __tablename__ = "payroll_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True)
    inss_employee_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=3)
    inss_employer_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=8)
    monthly_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=190.66)  # 44 h x 52 / 12
    monthly_days: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=22)  # working days
    inss_deducted_from_irt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # the working days of the week, 0 = Monday ... 6 = Sunday (Monday to Friday by default; a bakery adds Saturday)
    work_weekdays: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: [0, 1, 2, 3, 4])
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IrtTable(Base):
    __tablename__ = "irt_tables"
    __table_args__ = (UniqueConstraint("company_id", "valid_from", name="uq_irt_tables_valid_from"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)  # «OGE 2026 - Lei n.º 14/25»
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    # [{"from": 150000, "to": 200000, "fixed": 12500, "rate": 16, "over": 150000}, ...] - by «from»
    brackets: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayrollItem(Base):
    __tablename__ = "payroll_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)  # used in the formulas: SUB_ALIM
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    nature: Mapped[str] = mapped_column(String(10), nullable=False)  # ABONO | DESCONTO
    calc_method: Mapped[str] = mapped_column(String(12), nullable=False)  # CALC_METHODS
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # FIXO: the default amount
    rate: Mapped[float | None] = mapped_column(Numeric(7, 3), nullable=True)  # PERCENTAGEM: % of the base salary
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)  # FORMULA: as typed
    formula_ast: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # FORMULA: parsed (never eval)
    subject_inss: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subject_irt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    irt_exempt_limit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # an allowance: exempt up to
    # every employee gets it (his own amount or rate if he has one), or only the employees it is given to
    applies_to_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("uq_payroll_items_code", PayrollItem.company_id, func.upper(PayrollItem.code), unique=True)


class EmployeePayrollItem(Base):
    __tablename__ = "employee_payroll_items"
    __table_args__ = (UniqueConstraint("employee_id", "item_id", name="uq_employee_payroll_item"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"),
                                                   nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payroll_items.id"), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # FIXO: his amount
    rate: Mapped[float | None] = mapped_column(Numeric(7, 3), nullable=True)  # PERCENTAGEM: his rate
