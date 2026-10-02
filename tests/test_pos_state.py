"""A point of sale is used according to its state: an inactive one opens no session, one with an open session
cannot be deactivated."""
import pytest

from app.services.cash_session_service import open_session
from app.services.point_of_sale_service import PosStateError, create_point_of_sale, toggle_pos_status


@pytest.mark.asyncio
async def test_an_inactive_point_of_sale_opens_no_session(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    pos = await create_point_of_sale(db, company.id, setup["activity"].id, "Caixa Teste Inativa")
    await toggle_pos_status(db, company.id, pos.id)  # deactivated
    with pytest.raises(PosStateError, match="esta inativo"):
        await open_session(db, company.id, pos.id, setup["gestor"], opening_amount=0)


@pytest.mark.asyncio
async def test_a_point_of_sale_with_an_open_session_cannot_be_deactivated(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    pos = await create_point_of_sale(db, company.id, setup["activity"].id, "Caixa Teste Aberta")
    await open_session(db, company.id, pos.id, setup["gestor"], opening_amount=0)
    with pytest.raises(PosStateError, match="Feche a sessao"):
        await toggle_pos_status(db, company.id, pos.id)
