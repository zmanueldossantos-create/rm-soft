"""
MovementType catalog - platform-wide, SUPER_ADMIN managed (see PARTIE1&2 GESTAO DE
STOCK notes). A stock movement (Entrada/Saida) is a real document, numbered through its
own DocumentSeries-like mechanism, just like an invoice - see StockMovement.

direction: ENTRADA (stock in) or SAIDA (stock out).
is_auto: True when this type is meant to be populated via an Excel import rather than a
manually-filled form (see the "entrada automatica" / "saida automatica" discussion).
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class MovementDirection(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"


class MovementType(Base):
    __tablename__ = "movement_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(4), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[MovementDirection] = mapped_column(Enum(MovementDirection), nullable=False)
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<MovementType {self.code}>"

# Case-insensitive uniqueness (migration h1k8l3m72x04): no duplicate whatever the case. Declared here too, so a
# database built from the models (tests, new installs) has the same protection as a migrated one.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_movement_types_code_ci", _func.lower(MovementType.code), unique=True)
