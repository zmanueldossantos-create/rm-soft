"""
Tesouraria: a till's cash deposited on a bank account, and cash withdrawn from a bank account into a till (or the
cofre) - the till's balance and the bank statement move together; no reason needed.
"""
from datetime import date, timedelta

import pytest

from app.models.cash_movement import CashMovementType
from app.services.bank_treasury_service import get_bank_statement, list_bank_positions, set_opening_balance
from app.services.cash_movement_service import (
    DestinationPosNotOpenError, InsufficientFundsError, InvalidCashMovementError, create_cash_movement,
)
from app.services.cash_session_service import get_current_expected_cash_balance, get_open_session, open_session
from tests.test_bank_treasury import _account


@pytest.mark.asyncio
async def test_a_deposit_and_a_withdrawal(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user, pos = ctx["company"].id, ctx["gestor"], ctx["pos"]
    account_id = await _account(db, company_id)
    await set_opening_balance(db, company_id, account_id, 1000, date.today())
    await open_session(db, company_id, pos.id, user, opening_amount=5000)

    await create_cash_movement(db, company_id, CashMovementType.SAIDA_EXTERNA, user, 3000, source_pos_id=pos.id,
                               bank_account_id=account_id, description="Talão 123")
    await create_cash_movement(db, company_id, CashMovementType.ENTRADA_EXTERNA, user, 500, destination_pos_id=pos.id,
                               bank_account_id=account_id)
    session = await get_open_session(db, company_id, pos.id)
    assert await get_current_expected_cash_balance(db, company_id, pos.id, session) == 2500.0  # 5000 - 3000 + 500
    [position] = await list_bank_positions(db, company_id)
    assert position["balance"] == 3500.0  # 1000 + 3000 - 500
    lines = (await get_bank_statement(db, company_id, account_id))["lines"]
    assert [(l["document"], l["amount_in"], l["amount_out"]) for l in lines] == [("Depósito", 3000.0, 0.0), ("Levantamento", 0.0, 500.0)]
    assert lines[0]["description"].startswith("De ") and "Talão 123" in lines[0]["description"]


@pytest.mark.asyncio
async def test_the_deposit_and_withdrawal_rules(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user, pos = ctx["company"].id, ctx["gestor"], ctx["pos"]
    account_id = await _account(db, company_id)
    await set_opening_balance(db, company_id, account_id, 0, date.today())
    with pytest.raises(DestinationPosNotOpenError):  # the withdrawn cash is counted in an open till
        await create_cash_movement(db, company_id, CashMovementType.ENTRADA_EXTERNA, user, 100, destination_pos_id=pos.id,
                                   bank_account_id=account_id)
    await open_session(db, company_id, pos.id, user, opening_amount=200)
    with pytest.raises(InsufficientFundsError):  # never more than the till holds
        await create_cash_movement(db, company_id, CashMovementType.SAIDA_EXTERNA, user, 500, source_pos_id=pos.id,
                                   bank_account_id=account_id)
    with pytest.raises(InvalidCashMovementError, match="saldo inicial"):
        await create_cash_movement(db, company_id, CashMovementType.SAIDA_EXTERNA, user, 100, source_pos_id=pos.id,
                                   bank_account_id=account_id, movement_date=date.today() - timedelta(days=1))
