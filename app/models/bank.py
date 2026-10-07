"""Bank catalog - platform-wide, SUPER_ADMIN managed. Used by Company bank account setup (see onglet 3)."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Bank(Base):
    __tablename__ = "banks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    acronym: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "BAI"
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)  # e.g. "Banco Angolano de Investimentos"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Bank {self.acronym}>"

# Case-insensitive uniqueness (migration h1k8l3m72x04): no duplicate whatever the case. Declared here too, so a
# database built from the models (tests, new installs) has the same protection as a migrated one.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_banks_acronym_ci", _func.lower(Bank.acronym), unique=True)
