"""
The AI assistant for one company: switched on and given its channels by the SUPER_ADMIN (the platform pays the AI
provider, a monthly message limit per company), its confirmations chosen by the company's gestor.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyAiSettings(Base):
    __tablename__ = "company_ai_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True)

    # set by the SUPER_ADMIN
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    monthly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = the platform's default

    # set by the gestor: the assistant prepares, the gestor confirms before it is done
    confirm_documents: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    confirm_sends: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
