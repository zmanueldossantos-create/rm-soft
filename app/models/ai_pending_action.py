"""
An action the AI assistant prepared (issue a document, send one by email): the application keeps it here and does it
when the user confirms - by the app's button, or by answering SIM on WhatsApp / Telegram - or at once when the gestor
chose not to confirm. Never done by the AI itself; it expires unconfirmed.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiPendingAction(Base):
    __tablename__ = "ai_pending_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_conversations.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # ISSUE_DOCUMENT | SEND_EMAIL
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # what to do, resolved (ids)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)  # what the user sees on the card
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDENTE")  # PENDENTE | FEITA | CANCELADA | EXPIRADA | FALHOU
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # the document issued / the email sent, or the error
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
