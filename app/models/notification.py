"""
Notificações (option NOTIFICACOES of the plans): the company's settings, the recipients the gestor types himself (an
email, a Telegram chat, a WhatsApp number - people, not user accounts) with the events each one receives, and the
outbox the server sends from (app/services/notification_service.py) - a sale never waits for an email.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    include_gestor_actions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sale_min_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # VENDA: only above this


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False)  # EMAIL | TELEGRAM | WHATSAPP
    # EMAIL: the address; WHATSAPP: +244...; TELEGRAM: the chat id, once the person opened the link (empty before)
    address: Mapped[str | None] = mapped_column(String(160), nullable=True)
    telegram_name: Mapped[str | None] = mapped_column(String(150), nullable=True)  # @username, shown to the gestor
    link_code: Mapped[str | None] = mapped_column(String(12), nullable=True, unique=True)  # Telegram: NT + 8
    events: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("notification_recipients.id",
                                                           ondelete="SET NULL"), nullable=True)
    recipient_name: Mapped[str] = mapped_column(String(100), nullable=False)  # kept: the history outlives the recipient
    event: Mapped[str] = mapped_column(String(20), nullable=False)  # notification_events code, or TESTE
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    address: Mapped[str] = mapped_column(String(160), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PENDENTE", server_default="PENDENTE")  # ENVIADA, ERRO
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
