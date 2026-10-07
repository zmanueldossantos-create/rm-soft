"""A difference between the counted cash and the expected one never blocks the closing of a till, but it is always
explained: without a reason the closing is refused (the session stays open), with one it is recorded as it is."""
import pytest

from app.models.cash_session import CashSessionStatus
from app.services.cash_session_service import ClosingReasonRequiredError, close_session, open_session


async def _open(db, setup, amount=1000):
    return await open_session(db, setup["company"].id, setup["pos"].id, setup["gestor"], opening_amount=amount)


@pytest.mark.asyncio
async def test_a_shortfall_without_a_reason_is_refused_and_the_session_stays_open(db, company_with_essentials):
    setup = company_with_essentials
    session = await _open(db, setup)
    with pytest.raises(ClosingReasonRequiredError):
        await close_session(db, setup["company"].id, session.id, setup["gestor"].id, closing_amount_counted=900)
    await db.refresh(session)
    assert session.status == CashSessionStatus.ABERTA


@pytest.mark.asyncio
async def test_a_reason_made_of_spaces_is_no_reason(db, company_with_essentials):
    setup = company_with_essentials
    session = await _open(db, setup)
    with pytest.raises(ClosingReasonRequiredError):
        await close_session(db, setup["company"].id, session.id, setup["gestor"].id,
                            closing_amount_counted=1100, closing_notes="   ")


@pytest.mark.asyncio
async def test_a_shortfall_with_a_reason_closes_and_is_recorded(db, company_with_essentials):
    setup = company_with_essentials
    session = await _open(db, setup)
    closed = await close_session(db, setup["company"].id, session.id, setup["gestor"].id,
                                 closing_amount_counted=900, closing_notes="  Troco mal dado  ")
    assert closed.status == CashSessionStatus.FECHADA
    assert float(closed.closing_amount_expected) == 1000
    assert float(closed.closing_difference) == -100
    assert closed.closing_notes == "Troco mal dado"


@pytest.mark.asyncio
async def test_an_exact_count_needs_no_reason(db, company_with_essentials):
    setup = company_with_essentials
    session = await _open(db, setup)
    closed = await close_session(db, setup["company"].id, session.id, setup["gestor"].id, closing_amount_counted=1000)
    assert closed.status == CashSessionStatus.FECHADA and float(closed.closing_difference) == 0
    assert closed.closing_notes is None
