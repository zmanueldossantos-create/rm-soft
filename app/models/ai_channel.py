"""
The AI assistant outside the application: a user's WhatsApp or Telegram linked to his account (proved by a code shown
in the application and sent from the phone), and the codes waiting to be sent. A message from a chat not linked is
answered that it is not linked - never with data.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiChannelLink(Base):
    __tablename__ = "ai_channel_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # TELEGRAM | WHATSAPP
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # Telegram chat id / WhatsApp number
    external_name: Mapped[str | None] = mapped_column(String(150), nullable=True)  # @username, profile name
    # the conversation the chat goes on with (NOVA starts another)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_conversations.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiLinkCode(Base):
    __tablename__ = "ai_link_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
