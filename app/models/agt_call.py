"""
The journal of the calls to the AGT (Faturação Eletrónica): what was sent, what the AGT answered (or why it could not
be reached) and how long it took - the evidence asked during the homologation, and what the gestor reads when a document
is refused. Kept 90 days (app.services.agt_client.KEEP_DAYS).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgtCall(Base):
    __tablename__ = "agt_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
                                                         nullable=True)
    service: Mapped[str] = mapped_column(String(40), nullable=False)  # registarFactura, obterEstado, listarSeries...
    environment: Mapped[str] = mapped_column(String(20), nullable=False)  # HOMOLOGACAO | PRODUCAO
    request_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None: the AGT was not reached
    response_body: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
