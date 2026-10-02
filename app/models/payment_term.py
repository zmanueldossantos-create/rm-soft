"""
PaymentTerm (Condicao de pagamento) catalog - platform-wide, SUPER_ADMIN
managed (see reference list: A 60 dias, A 90 dias, Ate 8 dia do mes
seguinte, etc). Determines how a Customer/Invoice data de vencimento
gets calculated.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Numeric, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class PaymentTerm(Base):
    __tablename__ = "payment_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    fixed_days: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    months_fixed_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<PaymentTerm {self.name}>"

# Case-insensitive uniqueness (migration h1k8l3m72x04): no duplicate whatever the case. Declared here too, so a
# database built from the models (tests, new installs) has the same protection as a migrated one.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_payment_terms_name_ci", _func.lower(PaymentTerm.name), unique=True)
