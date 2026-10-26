"""
Ecrã do cliente (option ECRA_CLIENTE of the plans): what the second screen of a till shows when no sale is going on -
per activity (the Padaria and the Hotel of one company speak to different customers): a welcome message and up to
MAX_IMAGES pictures turning every slide_seconds. The screen itself is fed by the Caixa, in the browser (no table).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CustomerDisplaySettings(Base):
    __tablename__ = "customer_display_settings"

    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    welcome_message: Mapped[str | None] = mapped_column(String(200), nullable=True)
    slide_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default="8")


class CustomerDisplayImage(Base):
    __tablename__ = "customer_display_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(300), nullable=False)  # /uploads/ecra/<company>/<id>.<ext>
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
