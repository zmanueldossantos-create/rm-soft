"""
CompanyModule - grants a Company access to a Module (e.g. this company may
use the "Padaria" and "Bar" modules). SUPER_ADMIN manages these grants,
at company creation and afterward (a client may add a module later).
The GESTOR can only create Activities for modules the company has been
granted here - see activity_service.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CompanyModule(Base):
    __tablename__ = "company_modules"
    __table_args__ = (
        UniqueConstraint("company_id", "module_id", name="uq_company_module"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    module_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("modules.id"), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CompanyModule company={self.company_id} module={self.module_id}>"
