"""
Tesouraria - transfers between two bank accounts of the company: immediate within one bank; between two banks the
money leaves the first account and stays em trânsito until «Fundos disponíveis»; a cancellation reverses it.
"""
from datetime import date, timedelta

import pytest

from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.services.bank_transfer_service import (
    cancel_bank_transfer, confirm_funds_available, create_bank_transfer, list_transfers_in_transit,
)
from app.services.bank_treasury_service import (
    BankMovementError, get_bank_statement, list_bank_positions, set_opening_balance,
)


async def _accounts(db, company_id):
    """BAI 1 and BAI 2 (one bank), BFA (another bank) - each opened today with 10 000; and an account in dollars."""
    bai, bfa = Bank(acronym="BAI", full_name="BAI"), Bank(acronym="BFA", full_name="BFA")
    kz, usd = Currency(code="AOX", name="Kwanza teste"), Currency(code="USX", name="Dólar teste")
    db.add_all([bai, bfa, kz, usd])
    await db.flush()
    rows = [CompanyBankAccount(company_id=company_id, bank_id=bank.id, account_number=number, iban="AO06" + number,
                               currency_id=currency.id)
            for bank, number, currency in [(bai, "1", kz), (bai, "2", kz), (bfa, "3", kz), (bfa, "4", usd)]]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await set_opening_balance(db, company_id, row.id, 10000, date.today())
    return [row.id for row in rows]


def _balances(positions):
    return {p["account_number"]: (p["balance"], p["in_transit_in"]) for p in positions}


@pytest.mark.asyncio
async def test_within_one_bank_the_money_is_there_at_once(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user = ctx["company"].id, ctx["gestor"]
    bai1, bai2, _bfa, _usd = await _accounts(db, company_id)
    transfer = await create_bank_transfer(db, company_id, user, bai1, bai2, 2500, date.today(), "OP-1")
    assert (transfer.status.value, transfer.series, transfer.number) == ("DISPONIVEL", f"TRF{date.today().year}", 1)
    balances = _balances(await list_bank_positions(db, company_id))
    assert balances["1"] == (7500.0, 0.0) and balances["2"] == (12500.0, 0.0)
    [line] = (await get_bank_statement(db, company_id, bai2))["lines"]
    assert line["amount_in"] == 2500.0 and line["description"].startswith("Transferência de BAI · 1")


@pytest.mark.asyncio
async def test_between_two_banks_it_stays_in_transit_until_the_funds_are_available(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user = ctx["company"].id, ctx["gestor"]
    bai1, _bai2, bfa, _usd = await _accounts(db, company_id)
    transfer = await create_bank_transfer(db, company_id, user, bai1, bfa, 4000, date.today())
    assert transfer.status.value == "EM_TRANSITO"
    balances = _balances(await list_bank_positions(db, company_id))
    assert balances["1"] == (6000.0, 0.0) and balances["3"] == (10000.0, 4000.0)  # left, not yet arrived
    [line] = (await get_bank_statement(db, company_id, bai1))["lines"]
    assert line["in_transit"] and line["transfer_id"] == transfer.id
    assert [t["document"] for t in await list_transfers_in_transit(db, company_id)] == [f"TRF{date.today().year}/1"]

    with pytest.raises(BankMovementError, match="antes de a transferência sair"):
        await confirm_funds_available(db, company_id, transfer.id, user, date.today() - timedelta(days=1))
    await confirm_funds_available(db, company_id, transfer.id, user, date.today())
    balances = _balances(await list_bank_positions(db, company_id))
    assert balances["3"] == (14000.0, 0.0) and await list_transfers_in_transit(db, company_id) == []
    with pytest.raises(BankMovementError, match="não está em trânsito"):
        await confirm_funds_available(db, company_id, transfer.id, user, date.today())


@pytest.mark.asyncio
async def test_a_cancelled_transfer_gives_the_money_back(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user = ctx["company"].id, ctx["gestor"]
    bai1, bai2, bfa, _usd = await _accounts(db, company_id)
    in_transit = await create_bank_transfer(db, company_id, user, bai1, bfa, 1000, date.today())
    arrived = await create_bank_transfer(db, company_id, user, bai1, bai2, 3000, date.today())
    await cancel_bank_transfer(db, company_id, in_transit.id, user, "Conta errada")
    await cancel_bank_transfer(db, company_id, arrived.id, user, "Valor errado")
    balances = _balances(await list_bank_positions(db, company_id))
    assert balances["1"] == (10000.0, 0.0) and balances["2"] == (10000.0, 0.0) and balances["3"] == (10000.0, 0.0)
    statement = await get_bank_statement(db, company_id, bai2)
    assert [(l["amount_in"], l["amount_out"], l["transfer_id"]) for l in statement["lines"]] == [(3000.0, 0.0, None), (0.0, 3000.0, None)]
    with pytest.raises(BankMovementError, match="já está anulada"):
        await cancel_bank_transfer(db, company_id, arrived.id, user, "de novo")


@pytest.mark.asyncio
async def test_the_transfer_rules(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user = ctx["company"].id, ctx["gestor"]
    bai1, _bai2, bfa, usd = await _accounts(db, company_id)
    with pytest.raises(BankMovementError, match="duas contas diferentes"):
        await create_bank_transfer(db, company_id, user, bai1, bai1, 100, date.today())
    with pytest.raises(BankMovementError, match="mesma moeda"):
        await create_bank_transfer(db, company_id, user, bfa, usd, 100, date.today())
    with pytest.raises(BankMovementError, match="maior que zero"):
        await create_bank_transfer(db, company_id, user, bai1, bfa, 0, date.today())
    with pytest.raises(BankMovementError, match="saldo inicial"):
        await create_bank_transfer(db, company_id, user, bai1, bfa, 100, date.today() - timedelta(days=1))
