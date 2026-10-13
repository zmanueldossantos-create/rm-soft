"""Point 8 B (billetage): the notes and coins of a transfer between two tills - given by the sending till (their
total is the amount), confirmed by the receiving one (the sender's proposed), printed in both closing reports."""
import io

import pytest
from sqlalchemy import select

from app.models.cash_denomination_count import CashDenominationCount, DenominationCountType
from app.models.cash_movement import CashMovement, CashMovementStatus, CashMovementType
from app.models.currency import Currency
from app.models.denomination import Denomination
from app.models.point_of_sale import PointOfSale
from app.services.cash_denomination_count_service import CountTotalMismatchError, record_denomination_count
from app.services.cash_movement_service import (
    TransferBilletageRequiredError, cancel_cash_movement, create_cash_movement, get_transfer_billetage,
    receive_cash_movement,
)
from app.services.cash_report_service import get_closing_report_data
from app.services.cash_session_service import close_session, open_session
from app.utils.cash_report_pdf import generate_closing_report_pdf


async def _after_rollback(db, *objects):
    """A rollback expires what the session holds: read these again before using them."""
    await db.rollback()
    for obj in objects:
        await db.refresh(obj)


async def _two_tills(db, ctx):
    """Two tills of the activity, both with billetage and open: Caixa Teste with 7 000, Caixa 2 empty."""
    currency = (await db.execute(select(Currency).where(Currency.code == "AOA"))).scalar_one_or_none()
    if currency is None:
        currency = Currency(code="AOA", name="Kwanza")
        db.add(currency)
        await db.flush()
    note_5000 = Denomination(currency_id=currency.id, value=5000, denomination_type="NOTA")
    note_1000 = Denomination(currency_id=currency.id, value=1000, denomination_type="NOTA")
    till_2 = PointOfSale(company_id=ctx["company"].id, activity_id=ctx["activity"].id, name="Caixa 2", billetage_enabled=True)
    ctx["pos"].billetage_enabled = True
    db.add_all([note_5000, note_1000, till_2])
    await db.commit()
    session_1 = await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["gestor"], 7000)
    session_2 = await open_session(db, ctx["company"].id, till_2.id, ctx["gestor"], 0)
    return note_5000, note_1000, till_2, session_1, session_2


def _notes(note, quantity):
    return [{"denomination_id": note.id, "quantity": quantity}]


async def _send(db, ctx, till_2, amount, lines):
    return await create_cash_movement(db, ctx["company"].id, CashMovementType.TRANSFERENCIA, ctx["gestor"], amount,
                                      source_pos_id=ctx["pos"].id, destination_pos_id=till_2.id, denomination_lines=lines)


@pytest.mark.asyncio
async def test_a_transfer_carries_its_notes_to_both_closing_reports(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    note_5000, note_1000, till_2, session_1, session_2 = await _two_tills(db, ctx)

    movement = await _send(db, ctx, till_2, 2000, _notes(note_1000, 2))
    assert movement.status == CashMovementStatus.PENDENTE
    proposed = await get_transfer_billetage(db, company_id, movement.id)  # what the receiving till sees
    assert [(p["denomination_id"], p["quantity"], p["amount"]) for p in proposed] == [(note_1000.id, 2, 2000.0)]
    movement = await receive_cash_movement(db, company_id, movement.id, till_2.id, ctx["gestor"].id,
                                           denomination_lines=_notes(note_1000, 2))
    assert movement.status == CashMovementStatus.RECEBIDO

    for session, note, quantity in ((session_1, note_5000, 1), (session_2, note_1000, 2)):
        await record_denomination_count(db, company_id, session.id, DenominationCountType.FECHO, ctx["gestor"].id,
                                        _notes(note, quantity))
        await close_session(db, company_id, session.id, ctx["gestor"].id)

    line = {"value": 1000.0, "type": "NOTA", "quantity": 2, "amount": 2000.0}
    sent = await get_closing_report_data(db, company_id, session_1.id)
    received = await get_closing_report_data(db, company_id, session_2.id)
    assert sent["transfer_billetage"] == [{"direction": "Enviada", "counterpart": "Caixa 2", "amount": 2000.0, "lines": [line]}]
    assert received["transfer_billetage"] == [{"direction": "Recebida", "counterpart": "Caixa Teste", "amount": 2000.0, "lines": [line]}]
    pypdf = pytest.importorskip("pypdf")
    text = " ".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(generate_closing_report_pdf(sent))).pages)
    assert "Billetagem das transferências" in text and "Caixa 2" in text


@pytest.mark.asyncio
async def test_a_till_with_billetage_sends_only_notes_adding_up_to_the_amount(db, company_with_essentials):
    ctx = company_with_essentials
    _, note_1000, till_2, _, _ = await _two_tills(db, ctx)
    with pytest.raises(TransferBilletageRequiredError):
        await _send(db, ctx, till_2, 2000, None)
    await _after_rollback(db, ctx["company"], ctx["pos"], ctx["gestor"], till_2, note_1000)
    with pytest.raises(CountTotalMismatchError, match="devem somar 2 000.00 Kz"):
        await _send(db, ctx, till_2, 2000, _notes(note_1000, 3))
    await _after_rollback(db, ctx["company"])
    assert (await db.execute(select(CashMovement).where(CashMovement.company_id == ctx["company"].id))).first() is None


@pytest.mark.asyncio
async def test_a_wrong_reception_receives_nothing_and_a_cancel_takes_the_notes_back(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    note_5000, note_1000, till_2, _, _ = await _two_tills(db, ctx)
    movement = await _send(db, ctx, till_2, 2000, _notes(note_1000, 2))
    movement_id = movement.id
    with pytest.raises(CountTotalMismatchError):
        await receive_cash_movement(db, company_id, movement_id, till_2.id, ctx["gestor"].id,
                                    denomination_lines=_notes(note_5000, 1))
    await _after_rollback(db, ctx["pos"])
    movement = (await db.execute(select(CashMovement).where(CashMovement.id == movement_id))).scalar_one()
    assert movement.status == CashMovementStatus.PENDENTE

    await cancel_cash_movement(db, company_id, movement_id, ctx["pos"].id)
    assert (await db.execute(select(CashDenominationCount).where(CashDenominationCount.cash_movement_id == movement_id))).first() is None
