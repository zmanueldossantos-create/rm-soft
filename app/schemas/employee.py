"""Recursos Humanos: what the screens send for an employee's file, a departure, a readmission and the HR tables. The
checks (required fields, dates, IBAN, uniqueness) are in app.services.employee_service, with PT-PT messages."""
import uuid
from datetime import date

from pydantic import BaseModel


class EmployeeRequest(BaseModel):
    number: str | None = None
    full_name: str = ""
    gender: str | None = None
    birth_date: date | None = None
    marital_status: str | None = None
    nationality_id: uuid.UUID | None = None
    father_name: str | None = None
    mother_name: str | None = None
    id_document_type: str | None = None
    id_document_number: str | None = None
    id_issued_on: date | None = None
    id_expires_on: date | None = None
    nif: str | None = None
    social_security_number: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    department_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    job_title_id: uuid.UUID | None = None
    establishment_id: uuid.UUID | None = None
    hired_on: date | None = None
    contract_type_id: uuid.UUID | None = None
    contract_ends_on: date | None = None
    probation_ends_on: date | None = None
    work_schedule_id: uuid.UUID | None = None
    base_salary: float | None = None
    payment_method: str | None = None
    bank_id: uuid.UUID | None = None
    iban: str | None = None
    education_level_id: uuid.UUID | None = None
    training: str | None = None
    experience: str | None = None
    notes: str | None = None


class DepartureRequest(BaseModel):
    left_on: date | None = None
    reason: str = ""
    note: str | None = None


class ReadmissionRequest(BaseModel):
    hired_on: date | None = None


class HrReferenceCreateRequest(BaseModel):
    kind: str
    name: str


class HrReferenceUpdateRequest(BaseModel):
    name: str
    is_active: bool = True
