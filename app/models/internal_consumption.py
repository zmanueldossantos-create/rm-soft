"""
InternalConsumption - a generic record of stock leaving a warehouse for
internal operational use rather than a sale (e.g. towels/soap used for
housekeeping, cleaning supplies used in a kitchen) - no invoice, no
customer, not a fiscal document. Deliberately generic across sectors: the
same model serves Hotel housekeeping, Restaurant kitchen consumables, Spa
supplies, etc. - see the road-map discussion "Consumo Interno: modulo
generico reutilizavel entre secteurs".

Optionally attributable to a Resource (which room/table consumed it) for
reporting - null when the consumption isn't tied to one specific resource
(e.g. general cleaning supplies, not room-specific).
"""
import uuid
from datetime import datetime

from sqlalchemy import Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class InternalConsumption(Base):
    __tablename__ = "internal_consumptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    reason_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("consumption_reason_catalog.id"), nullable=False)
    # Which room/table/resource consumed this, when attributable - see docstring.
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=True, index=True)
    consumed_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<InternalConsumption {self.quantity} of {self.product_id}>"
