"""An open account belongs to its activity: no till is chosen to open it (the default one is recorded)."""
import pytest

from app.models.point_of_sale import PointOfSale
from app.services.open_account_service import open_account


@pytest.mark.asyncio
async def test_an_account_opened_without_a_till_records_one_of_its_activity(db, company_with_essentials):
    ctx = company_with_essentials
    account = await open_account(db, ctx["company"].id, ctx["activity"].id, None, ctx["gestor"].id, "Mesa 1")
    pos = await db.get(PointOfSale, account.pos_id)
    assert pos is not None and pos.activity_id == ctx["activity"].id
