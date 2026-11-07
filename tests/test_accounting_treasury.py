"""
Contabilidade - the entries the system makes from the treasury: a till's exit with a reason (waiting until the reason
has its account), a deposit, a bank movement and its cancellation, the transfers between banks (through «em trânsito»,
or straight within one bank) and the cancellation of one, the difference found at a till's closing.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.bank import Bank
from app.models.cash_movement import CashMovementType
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.models.journal import JournalEntry
from app.models.movement_type import MovementDirection
from app.services.account_mapping_service import set_mapping, set_reason_account
from app.services.accounting_integration_service import integrate_company, integration_status
from app.services.bank_transfer_service import cancel_bank_transfer, confirm_funds_available, create_bank_transfer
from app.services.bank_treasury_service import cancel_bank_movement, create_bank_movement, set_opening_balance
from app.services.cash_movement_service import create_cash_movement, create_cash_movement_reason
from app.services.cash_session_service import close_session, get_open_session, open_session
from app.services.chart_of_accounts_service import get_chart, start_chart
from app.services.journal_service import get_entry


async def _lines(db, company_id, kind, source_id):
    """[(label, [(code, debit, credit)])] of the entries of one source (and their estorno)."""
    out = []
    ids = (await db.execute(select(JournalEntry.id).where(JournalEntry.source_kind == kind, JournalEntry.source_id == source_id))).scalars().all()
    for entry_id in ids:
        while entry_id is not None:
            entry = await get_entry(db, company_id, entry_id)
            out.append((entry["label"], [(l["account_code"], float(l["debit"]), float(l["credit"])) for l in entry["lines"]]))
            entry_id = (await db.execute(select(JournalEntry.id).where(JournalEntry.reversal_of_id == entry_id))).scalar_one_or_none()
    return out


@pytest.mark.asyncio
async def test_treasury_entries(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user, pos_id, today = ctx["company"].id, ctx["gestor"], ctx["pos"].id, date.today()
    bai, bfa, kz = Bank(acronym="BAI", full_name="BAI"), Bank(acronym="BFA", full_name="BFA"), Currency(code="AOA", name="Kwanza")
    db.add_all([bai, bfa, kz])
    await db.flush()
    accounts = [CompanyBankAccount(company_id=company_id, bank_id=bank.id, account_number=number, iban="AO06" + number,
                                   currency_id=kz.id) for bank, number in ((bai, "0001"), (bai, "0002"), (bfa, "0003"))]
    db.add_all(accounts)
    await db.commit()
    bai1, bai2, bfa1 = (a.id for a in accounts)  # 43.1.1, 43.1.2, 43.1.3
    for account_id in (bai1, bai2, bfa1):
        await set_opening_balance(db, company_id, account_id, 100000, today)
    await start_chart(db, company_id, "PGC")
    light = await create_cash_movement_reason(db, company_id, "Eletricidade", MovementDirection.SAIDA)
    fees = await create_cash_movement_reason(db, company_id, "Comissões", MovementDirection.SAIDA, for_cash=False, for_bank=True)
    light_id, fees_id = light.id, fees.id

    await open_session(db, company_id, pos_id, user, opening_amount=5000)
    await db.refresh(user)
    exit_ = await create_cash_movement(db, company_id, CashMovementType.SAIDA_EXTERNA, user, 1000, source_pos_id=pos_id, reason_id=light_id)
    deposit = await create_cash_movement(db, company_id, CashMovementType.SAIDA_EXTERNA, user, 2000, source_pos_id=pos_id, bank_account_id=bai1)
    commission = await create_bank_movement(db, company_id, user, bai1, fees_id, 150, today)
    exit_id, deposit_id, commission_id = exit_.id, deposit.id, commission.id
    to_bfa = await create_bank_transfer(db, company_id, user, bai1, bfa1, 10000, today)
    to_bfa_id = to_bfa.id
    await confirm_funds_available(db, company_id, to_bfa_id, user, today)
    within = await create_bank_transfer(db, company_id, user, bai1, bai2, 5000, today)
    within_id = within.id

    assert await integrate_company(db, company_id) == {"posted": 4, "pending": 2}
    reasons = sorted(p["reason"] for p in (await integration_status(db, company_id))["pending"])
    assert "«Comissões»" in reasons[0] and "«Eletricidade»" in reasons[1]
    chart = {a["code"]: a["id"] for a in (await get_chart(db, company_id))["accounts"]}
    await set_reason_account(db, company_id, light_id, chart["75.2"])
    await set_reason_account(db, company_id, fees_id, chart["76.7"])
    assert await integrate_company(db, company_id) == {"posted": 2, "pending": 0}

    assert (await _lines(db, company_id, "CASH_MOVEMENT", exit_id))[0][1] == [("45.1.1", 0.0, 1000.0), ("75.2", 1000.0, 0.0)]
    assert (await _lines(db, company_id, "CASH_MOVEMENT", deposit_id))[0][1] == [("43.1.1", 2000.0, 0.0), ("45.1.1", 0.0, 2000.0)]
    assert (await _lines(db, company_id, "BANK_MOVEMENT", commission_id))[0][1] == [("43.1.1", 0.0, 150.0), ("76.7", 150.0, 0.0)]
    assert (await _lines(db, company_id, "BANK_TRANSFER", to_bfa_id))[0][1] == [("48", 10000.0, 0.0), ("43.1.1", 0.0, 10000.0)]
    assert (await _lines(db, company_id, "BANK_TRANSFER_IN", to_bfa_id))[0][1] == [("43.1.3", 10000.0, 0.0), ("48", 0.0, 10000.0)]
    assert (await _lines(db, company_id, "BANK_TRANSFER", within_id))[0][1] == [("43.1.2", 5000.0, 0.0), ("43.1.1", 0.0, 5000.0)]
    assert await _lines(db, company_id, "BANK_TRANSFER_IN", within_id) == []  # within one bank: no arrival of its own

    # cancelled after their entries: the estorno
    await cancel_bank_movement(db, company_id, commission_id, user, "Engano")
    pending = await create_bank_transfer(db, company_id, user, bai1, bfa1, 300, today)
    pending_id = pending.id
    assert (await integrate_company(db, company_id))["posted"] == 2  # the estorno, the new transfer
    await cancel_bank_transfer(db, company_id, pending_id, user, "Engano")
    assert (await integrate_company(db, company_id))["posted"] == 1
    entries = await _lines(db, company_id, "BANK_MOVEMENT", commission_id)
    assert len(entries) == 2 and entries[1][1] == [("43.1.1", 150.0, 0.0), ("76.7", 0.0, 150.0)]
    assert len(await _lines(db, company_id, "BANK_TRANSFER", pending_id)) == 2

    # the closing: 5000 - 1000 - 2000 expected, 1900 counted - a shortage of 100
    session_id = (await get_open_session(db, company_id, pos_id)).id
    await close_session(db, company_id, session_id, user.id, closing_amount_counted=1900, closing_notes="Nota perdida")
    assert await integrate_company(db, company_id) == {"posted": 0, "pending": 1}  # «Falta de caixa» not set
    await set_mapping(db, company_id, "CASH_SHORTAGE", chart["78.4.1"])
    assert (await integrate_company(db, company_id))["posted"] == 1
    assert (await _lines(db, company_id, "CASH_CLOSING", session_id))[0][1] == [("78.4.1", 100.0, 0.0), ("45.1.1", 0.0, 100.0)]
