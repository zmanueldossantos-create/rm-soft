"""
PharmaceuticalForm - the managed list of dosage forms of a pharmacy's medicines (Comprimido, Cápsula, Xarope,
Injetável, Pomada...). Company-scoped, managed by the GESTOR through the generic catalog screen (Categorias.jsx), never
deleted - only deactivated. Part of the Farmácia capability (app.core.capabilities, PHARMACY).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PharmaceuticalForm(Base):
    __tablename__ = "pharmaceutical_forms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<PharmaceuticalForm {self.name}>"


# Case-insensitive uniqueness per company, the same protection as the other managed lists.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_pharmaceutical_forms_company_name_ci", PharmaceuticalForm.company_id, _func.lower(PharmaceuticalForm.name), unique=True)
