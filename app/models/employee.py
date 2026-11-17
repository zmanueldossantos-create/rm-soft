"""
Recursos Humanos (capability HR): the company's employees (colaboradores) and the tables their file picks from.

HrReference - the company's own lists, one row per value: departments, professional categories, job titles,
contract types, work schedules, education levels, document types. Renamed or switched off, never deleted once used
(an employee keeps the value he has).

Employee - the employee's file: identification, professional data, pay, qualifications; numbered (matrícula) per
company. A departure (left_on + reason) keeps the file: it leaves the active list and can be readmitted. The countries
(nationality), banks and establishments (place of work) are the existing catalogs, not copies.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# HrReference.kind - the lists of the employee's file
REFERENCE_KINDS: dict[str, str] = {
    "DEPARTAMENTO": "Departamentos",
    "CATEGORIA": "Categorias profissionais",
    "FUNCAO": "Funções / cargos",
    "TIPO_CONTRATO": "Tipos de contrato",
    "HORARIO": "Horários de trabalho",
    "ESCOLARIDADE": "Níveis de escolaridade",
    "TIPO_DOCUMENTO": "Documentos do processo",
}

GENDERS = {"M": "Masculino", "F": "Feminino"}
MARITAL_STATUSES = {"SOLTEIRO": "Solteiro(a)", "CASADO": "Casado(a)", "UNIAO_FACTO": "União de facto",
                    "DIVORCIADO": "Divorciado(a)", "VIUVO": "Viúvo(a)"}
ID_DOCUMENT_TYPES = {"BI": "Bilhete de identidade", "PASSAPORTE": "Passaporte", "CARTAO_RESIDENTE": "Cartão de residente"}
PAYMENT_METHODS = {"TRANSFERENCIA": "Transferência bancária", "NUMERARIO": "Numerário", "CHEQUE": "Cheque"}
LEAVING_REASONS = {
    "FIM_CONTRATO": "Fim do contrato",
    "DEMISSAO": "Demissão (iniciativa do trabalhador)",
    "DESPEDIMENTO": "Despedimento",
    "MUTUO_ACORDO": "Revogação por mútuo acordo",
    "PERIODO_EXPERIMENTAL": "Denúncia no período experimental",
    "REFORMA": "Reforma",
    "FALECIMENTO": "Falecimento",
    "OUTRO": "Outro",
}


class HrReference(Base):
    __tablename__ = "hr_references"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # REFERENCE_KINDS
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# one value per list, whatever the case
Index("uq_hr_references_name", HrReference.company_id, HrReference.kind, func.lower(HrReference.name), unique=True)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(20), nullable=False)  # the matrícula, 0001 by default

    # identification
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    nationality_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("countries.id"), nullable=True)
    father_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mother_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    id_document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    id_document_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    id_issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    id_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    nif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    social_security_number: Mapped[str | None] = mapped_column(String(20), nullable=True)  # n.º de segurança social (INSS)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # professional data
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hr_references.id"), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hr_references.id"), nullable=True)
    job_title_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hr_references.id"), nullable=True)
    establishment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("establishments.id"), nullable=True)
    hired_on: Mapped[date] = mapped_column(Date, nullable=False)
    contract_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hr_references.id"), nullable=True)
    contract_ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    probation_ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    work_schedule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hr_references.id"), nullable=True)

    # pay
    base_salary: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(15), nullable=False, default="TRANSFERENCIA")
    bank_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("banks.id"), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)

    # qualifications
    education_level_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hr_references.id"), nullable=True)
    training: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # departure: the file stays, out of the active list
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    left_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    leaving_reason: Mapped[str | None] = mapped_column(String(25), nullable=True)
    leaving_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# unique per company: the matrícula, and each identifier when given (case ignored)
Index("uq_employees_number", Employee.company_id, func.lower(Employee.number), unique=True)
Index("uq_employees_id_document", Employee.company_id, func.lower(Employee.id_document_number), unique=True,
      postgresql_where=Employee.id_document_number.isnot(None))
Index("uq_employees_nif", Employee.company_id, func.lower(Employee.nif), unique=True, postgresql_where=Employee.nif.isnot(None))
Index("uq_employees_social_security", Employee.company_id, Employee.social_security_number, unique=True,
      postgresql_where=Employee.social_security_number.isnot(None))
