"""
CompanyDocumentTypePreference - per-company override of a DocumentType rule that the platform catalog
(DocumentType) sets as a default. The first such rule is requires_payment_term (see DocumentType docstring):
the global catalog default is set by SUPER_ADMIN, but each company's own GESTOR may turn it off (or on) for
that company - same split as CompanyPaymentMethodPreference for available_at_pos.

One row per (company_id, document_type_id) pair - absence of a row means "follow the platform catalog default"
(see company_document_type_service.list_document_type_preferences).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CompanyDocumentTypePreference(Base):
    __tablename__ = "company_document_type_preferences"
    __table_args__ = (
        UniqueConstraint("company_id", "document_type_id", name="uq_company_document_type_pref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    document_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_types.id"), nullable=False, index=True)
    requires_payment_term: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<CompanyDocumentTypePreference company={self.company_id} document_type={self.document_type_id}>"