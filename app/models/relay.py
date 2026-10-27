"""
The relay (P4 step 5) - on the RM SOFT platform only: the public API of a company whose server is installed at the
client's (local mode, behind its internet box, sometimes off).

The client's web site calls the platform with its key, as with a SaaS company. The platform keeps the call
(RelayRequest); the agent of the client's server - which goes OUT to the platform, no port open at the client's -
takes it, runs it on its own API and sends the answer back. The server off: a write waits (202 and a request number),
a read is answered from the last photo the agent sent (catalogue, availability).

RelayLink: one per client company - the agent's secret (its SHA-256 only), the hashes of the company's active keys (the
platform recognises a key without ever knowing it) and the last photo.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RelayLink(Base):
    __tablename__ = "relay_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False,
                                                  unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    secret_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # [{"id", "name", "hash", "scopes"}]: the company's active keys, as its agent last sent them
    keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RelayRequest(Base):
    __tablename__ = "relay_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False,
                                                  index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_name: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    query: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    body: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    callback_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # PENDENTE (waiting for the agent) -> EM_CURSO (taken) -> FEITO (answered)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PENDENTE", index=True)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# one request per Idempotency-Key and company (declared here too: the tests build the database from the models)
Index("uq_relay_requests_idempotency", RelayRequest.company_id, RelayRequest.idempotency_key, unique=True,
      postgresql_where=text("idempotency_key IS NOT NULL"))


class RelayAgentSettings(Base):
    """On the client's server (local installation): where its agent connects - the platform's address and the relay's
    secret (encrypted, app.core.secret_box) - and how its last connection went."""
    __tablename__ = "relay_agent_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    relay_url: Mapped[str] = mapped_column(String(300), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requests_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
