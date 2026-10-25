"""
A «Pedir demonstração» sent from the public site (rmsystem.co.ao): who asked, for what business, which plan, cloud or
own server. The SUPER_ADMIN follows it in «Pedidos»: NOVO -> CONTACTADO -> CONVERTIDO (a client now) or DESCARTADO.
Platform-wide (no company_id): the person is not a client yet.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

DEMO_STATUSES = {"NOVO": "Novo", "CONTACTADO": "Contactado", "CONVERTIDO": "Convertido", "DESCARTADO": "Descartado"}
DEMO_DEPLOYMENTS = {"SAAS": "Na nuvem", "LOCAL": "No servidor do cliente", "NAO_SEI": "Ainda não sabe"}


class DemoRequest(Base):
    __tablename__ = "demo_requests"
    __table_args__ = (Index("ix_demo_requests_ip_created", "ip", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    nif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sectors: Mapped[list[str]] = mapped_column(ARRAY(String(30)), nullable=False, default=list)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"),
                                                      nullable=True)
    deployment: Mapped[str] = mapped_column(String(10), nullable=False, default="NAO_SEI")
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="pt")
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # the anti-spam limit per address
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="NOVO", server_default="NOVO", index=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)  # RM SOFT's own follow-up notes
    handled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    plan = relationship("Plan", lazy="selectin")
    handled_by = relationship("User", lazy="selectin")
