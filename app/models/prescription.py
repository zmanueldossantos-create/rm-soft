"""
Prescription (receita médica) - the prescription a pharmacy sale was dispensed against, one per sales document.
Asked at the sale when the cart holds a medicine sold on prescription (Product.dispensing_regime RECEITA or
RECEITA_ESPECIAL, see pharmacy_service.check_prescription); printed on the document and listed by the registo de
receitas. A RECEITA_ESPECIAL (psychotropics, narcotics) always needs the patient and the identity document.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, unique=True)
    number: Mapped[str | None] = mapped_column(String(50), nullable=True)  # n.º da receita
    prescriber: Mapped[str | None] = mapped_column(String(150), nullable=True)  # médico
    health_unit: Mapped[str | None] = mapped_column(String(150), nullable=True)  # unidade de saúde
    patient_name: Mapped[str | None] = mapped_column(String(150), nullable=True)  # utente
    patient_document: Mapped[str | None] = mapped_column(String(50), nullable=True)  # BI / passaporte (receita especial)
    is_special: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # the sale held a receita especial medicine
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
