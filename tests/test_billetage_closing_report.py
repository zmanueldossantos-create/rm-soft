"""Point 8 (billetage): the drawer is counted at the closing; the closing report prints that count, note by note.
A count only goes to an open session of the company."""
import io

import pytest
from sqlalchemy import select

from app.models.cash_denomination_count import DenominationCountType
from app.models.currency import Currency
from app.models.denomination import Denomination
from app.services.cash_denomination_count_service import CountSessionNotFoundError, record_denomination_count
from app.services.cash_report_service import get_closing_report_data
from app.services.cash_session_service import close_session, open_session
from app.utils.cash_report_pdf import generate_closing_report_pdf


async def _denominations(db):
    currency = (await db.execute(select(Currency).where(Currency.code == "AOA"))).scalar_one_or_none()
    if currency is None:
        currency = Currency(code="AOA", name="Kwanza")
        db.add(currency)
        await db.flush()
    note_5000 = Denomination(currency_id=currency.id, value=5000, denomination_type="NOTA")
    note_1000 = Denomination(currency_id=currency.id, value=1000, denomination_type="NOTA")
    db.add_all([note_5000, note_1000])
    await db.commit()
    return note_5000, note_1000


@pytest.mark.asyncio
async def test_the_closing_report_prints_the_notes_and_coins_counted(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, pos = ctx["company"].id, ctx["pos"]
    note_5000, note_1000 = await _denominations(db)
    pos.billetage_enabled = True
    await db.commit()
    session = await open_session(db, company_id, pos.id, ctx["gestor"], 7000)
    await record_denomination_count(db, company_id, session.id, DenominationCountType.FECHO, ctx["gestor"].id,
                                    [{"denomination_id": note_1000.id, "quantity": 2}, {"denomination_id": note_5000.id, "quantity": 1}])
    await close_session(db, company_id, session.id, ctx["gestor"].id)

    data = await get_closing_report_data(db, company_id, session.id)
    assert data["billetage"] == [
        {"value": 5000.0, "type": "NOTA", "quantity": 1, "amount": 5000.0},
        {"value": 1000.0, "type": "NOTA", "quantity": 2, "amount": 2000.0},
    ]
    pypdf = pytest.importorskip("pypdf")
    text = " ".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(generate_closing_report_pdf(data))).pages)
    assert "Billetagem (contagem do fecho)" in text and "Total contado" in text


@pytest.mark.asyncio
async def test_a_closing_without_billetage_prints_no_table(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    session = await open_session(db, company_id, ctx["pos"].id, ctx["gestor"], 0)
    await close_session(db, company_id, session.id, ctx["gestor"].id, closing_amount_counted=0)
    assert (await get_closing_report_data(db, company_id, session.id))["billetage"] == []


@pytest.mark.asyncio
async def test_a_count_goes_only_to_an_open_session(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, pos = ctx["company"].id, ctx["pos"]
    note_5000, _ = await _denominations(db)
    session = await open_session(db, company_id, pos.id, ctx["gestor"], 0)
    await close_session(db, company_id, session.id, ctx["gestor"].id, closing_amount_counted=0)
    with pytest.raises(CountSessionNotFoundError):
        await record_denomination_count(db, company_id, session.id, DenominationCountType.FECHO, ctx["gestor"].id,
                                        [{"denomination_id": note_5000.id, "quantity": 1}])
