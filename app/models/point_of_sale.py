"""
PointOfSale model - a physical/logical sales point within an Activity.
An Activity (e.g. "Bar", "Padaria") can have several POS (e.g. "Caixa 1",
"Balcao Rua"), each opening its own CashSession independently - all POS
under the same Activity share that Activity''s stock/warehouse (see
Activity.warehouse_id), only the cash register itself is per-POS.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class PointOfSale(Base):
    __tablename__ = "points_of_sale"
    __table_args__ = (
        UniqueConstraint("activity_id", "name", name="uq_pos_activity_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Caixa 1", "Balcao Rua"
    # Denomination breakdown (billetagem) on open/close - toggle per cash point,
    # same field also exists on CashOffice (see cash_office.py).
    billetage_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Printing after a sale at this till: off = nothing printed automatically (as before); on = the ticket, the A4,
    # or - both chosen - the cashier picks one. Set per till: two tills of one activity may differ.
    print_after_sale: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    print_ticket: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    print_a4: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # Closing: accept a difference between the counted and the expected cash (always with a reason), or refuse the
    # closing until they match. And whether the closing report (A4) is proposed right after the closing - it can
    # always be printed again later from the reports, whatever this setting.
    accept_closing_difference: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    print_closing_report: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # The Activity's default cash point - auto-created alongside the Activity (see
    # activity_service.create_activity), never renamable/deactivatable/deletable,
    # same principle as the central Warehouse. Replaces the old separate CashOffice
    # concept - see architecture note in cash_movement.py.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<PointOfSale {self.name}>"
