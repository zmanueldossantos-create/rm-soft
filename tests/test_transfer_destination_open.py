"""A TRANSFERENCIA is refused if the destination POS has no open cash session (the money would land uncounted)."""
import pytest

from app.models.point_of_sale import PointOfSale
from app.models.cash_movement import CashMovementType
from app.services.cash_movement_service import DestinationPosNotOpenError, create_cash_movement
from app.services.cash_session_service import open_session


@pytest.mark.asyncio
async def test_transfer_refused_when_destination_has_no_open_session(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    closed_pos = PointOfSale(company_id=company_id, activity_id=activity_id, name="Caixa fechada", is_default=False, billetage_enabled=False)
    db.add(closed_pos)
    await db.commit()
    await db.refresh(closed_pos)

    await open_session(db, company_id, pos_id, gestor, opening_amount=1000.0)  # the source needs a session too

    with pytest.raises(DestinationPosNotOpenError):
        await create_cash_movement(
            db, company_id, CashMovementType.TRANSFERENCIA, gestor, 100.0,
            source_pos_id=pos_id, destination_pos_id=closed_pos.id,
        )