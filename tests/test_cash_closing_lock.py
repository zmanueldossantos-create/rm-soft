"""A till that does not accept a difference at closing refuses it, even with a reason: the manager turns the
setting on to let it close. An exact count always closes."""
import pytest

from app.models.cash_session import CashSessionStatus
from app.services.cash_session_service import ClosingDifferenceNotAllowedError, close_session, open_session


async def _locked_session(db, setup):
    setup["pos"].accept_closing_difference = False
    await db.commit()
    return await open_session(db, setup["company"].id, setup["pos"].id, setup["gestor"], opening_amount=1000)


@pytest.mark.asyncio
async def test_a_locked_till_refuses_a_difference_even_with_a_reason(db, company_with_essentials):
    setup = company_with_essentials
    session = await _locked_session(db, setup)
    with pytest.raises(ClosingDifferenceNotAllowedError):
        await close_session(db, setup["company"].id, session.id, setup["gestor"].id,
                            closing_amount_counted=900, closing_notes="Troco mal dado")
    await db.refresh(session)
    assert session.status == CashSessionStatus.ABERTA


@pytest.mark.asyncio
async def test_a_locked_till_closes_on_an_exact_count(db, company_with_essentials):
    setup = company_with_essentials
    session = await _locked_session(db, setup)
    closed = await close_session(db, setup["company"].id, session.id, setup["gestor"].id, closing_amount_counted=1000)
    assert closed.status == CashSessionStatus.FECHADA
