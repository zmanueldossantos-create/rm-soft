"""
UnitOfMeasureCatalog - platform-wide, SUPER_ADMIN managed (Video 3: select
unidade administrable) - e.g. UN, KG, L, CX. Distinct from Product.unit_of_measure
(free text) - reconciling the two is a separate future step.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class UnitOfMeasureCatalog(Base):
    __tablename__ = "unit_of_measure_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Universal units always hold the same count (a dozen is 12): a product's sale unit in it must use that factor.
    fixed_factor: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    # A fractional unit (KG, L) takes decimal quantities (1.250 kg); any other is sold in whole units only.
    is_fractional: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<UnitOfMeasureCatalog {self.code}>"

# Case-insensitive uniqueness (migration h1k8l3m72x04): no duplicate whatever the case. Declared here too, so a
# database built from the models (tests, new installs) has the same protection as a migrated one.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_units_code_ci", _func.lower(UnitOfMeasureCatalog.code), unique=True)
