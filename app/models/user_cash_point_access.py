"""
UserCashPointAccess model - associates a User to exactly ONE PointOfSale
at a time - see discussion on cash operation permissions: a user with no
association here cannot perform ANY cash operation (open session, sell,
transfer, external entrada/saida), regardless of role, except GESTOR who
bypasses this check entirely and always has full access to every cash point.

ARCHITECTURE NOTE: this used to also allow a separate CashOffice target
(cash_office_id). That concept has been retired - see cash_movement.py for
the full explanation; every Activity's default POS covers that role now.

One row per user (unique on user_id) - reassigning a user to a different
POS updates this row rather than adding a second one, since a user can
only be associated to one cash point at a time.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class UserCashPointAccess(Base):
    __tablename__ = "user_cash_point_access"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_cash_point_access_user"),
        # A POS can only be assigned to one user at a time too - assigning it to a
        # different user requires explicitly unassigning the current one first
        # (enforced in the service, this just guards the data at the DB level).
        UniqueConstraint("pos_id", name="uq_user_cash_point_access_pos"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    pos_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("points_of_sale.id"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<UserCashPointAccess user={self.user_id}>"
