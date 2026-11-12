"""The float of a till's first opening is its cash in the imported opening balances (its 45.1.x sub-account), 0
without one; afterwards, what was counted at the last closing. A session opened by mistake is cancelled while
nothing happened in it."""
import io
from datetime import date

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.models.account import AccountLink, Account
from app.models.cash_movement import CashMovementType
from app.models.cash_session import CashSession
from app.services.account_mapping_service import sync_subaccounts
from app.services.cash_movement_service import create_cash_movement
from app.services.cash_session_service import (
    SessionNotEmptyError, cancel_empty_session, close_session, get_carry_forward, get_session_summary, open_session,
)
from app.services.chart_of_accounts_service import start_chart
from app.services.opening_balances_service import import_opening_balances


def _xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Saldos iniciais"
    ws.append(("Código", "Descrição", "Débito", "Crédito"))
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


async def _till_code(db, company_id, pos_id) -> str:
    return (await db.execute(select(Account.code).join(AccountLink, AccountLink.account_id == Account.id).where(
        AccountLink.company_id == company_id, AccountLink.entity_kind == "TILL", AccountLink.entity_id == pos_id))).scalar_one()


@pytest.mark.asyncio
async def test_the_first_opening_takes_the_imported_opening_balance(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, pos_id, gestor = ctx["company"].id, ctx["pos"].id, ctx["gestor"]
    assert await get_carry_forward(db, company_id, pos_id) == (0.0, "NONE")  # no import: starts empty

    await start_chart(db, company_id, "PGC")
    await sync_subaccounts(db, company_id)
    code = await _till_code(db, company_id, pos_id)
    await import_opening_balances(db, company_id, None, _xlsx([(code, "Caixa", 5_000, None), ("51", "", None, 5_000)]), date.today())
    assert await get_carry_forward(db, company_id, pos_id) == (5_000.0, "OPENING_BALANCES")

    session = await open_session(db, company_id, pos_id, gestor)
    assert float(session.opening_amount) == 5_000
    await close_session(db, company_id, session.id, gestor.id, closing_amount_counted=3_100, closing_notes="Contado")
    assert await get_carry_forward(db, company_id, pos_id) == (3_100.0, "LAST_CLOSING")  # the count wins from now on


@pytest.mark.asyncio
async def test_an_opening_by_mistake_is_cancelled_while_nothing_happened(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, pos_id, gestor = ctx["company"].id, ctx["pos"].id, ctx["gestor"]
    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    assert (await get_session_summary(db, company_id, pos_id))["cancellable"]
    await cancel_empty_session(db, company_id, session.id)
    assert await db.get(CashSession, session.id) is None

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=1_000)
    await create_cash_movement(db, company_id, CashMovementType.SAIDA_EXTERNA, gestor, amount=100,
                               source_pos_id=pos_id, reason_id=None, description="x") if False else None
    from app.models.cash_movement_reason import CashMovementReason
    reason = CashMovementReason(company_id=company_id, name="Despesas", direction="SAIDA")
    db.add(reason)
    await db.commit()
    await create_cash_movement(db, company_id, CashMovementType.SAIDA_EXTERNA, gestor, amount=100,
                               source_pos_id=pos_id, reason_id=reason.id)
    assert not (await get_session_summary(db, company_id, pos_id))["cancellable"]
    with pytest.raises(SessionNotEmptyError):
        await cancel_empty_session(db, company_id, session.id)


@pytest.mark.asyncio
async def test_the_opening_balance_heads_the_till_history_without_being_a_movement(db, company_with_essentials):
    from app.models.cash_movement import CashMovement
    from app.services.opening_balances_service import cancel_opening_balances
    from app.services.treasury_overview_service import list_treasury_movements
    ctx = company_with_essentials
    company_id, pos_id = ctx["company"].id, ctx["pos"].id
    await start_chart(db, company_id, "PGC")
    await sync_subaccounts(db, company_id)
    code = await _till_code(db, company_id, pos_id)
    await import_opening_balances(db, company_id, None, _xlsx([(code, "Caixa", 5_000, None), ("51", "", None, 5_000)]), date.today())

    [row] = await list_treasury_movements(db, company_id, pos_id=pos_id)
    assert (row["movement_type"], row["amount"], row["destination"]["id"], row["source"]) == ("SALDO_INICIAL", 5_000, pos_id, None)
    assert (await db.execute(select(CashMovement.id).where(CashMovement.company_id == company_id))).first() is None
    assert await list_treasury_movements(db, company_id, movement_type=CashMovementType.ENTRADA_EXTERNA) == []

    await cancel_opening_balances(db, company_id, None)
    assert await list_treasury_movements(db, company_id, pos_id=pos_id) == []  # follows the import
