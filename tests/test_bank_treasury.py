"""
Tesouraria - Bancos: a bank account's balance and statement read from the documents that name it (a receipt
collected on it, a supplier payment made from it and its cancellation), from its opening balance on.
"""
from datetime import date, timedelta

import pytest

from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.services.bank_treasury_service import (
    InvalidOpeningBalanceError, get_bank_statement, list_bank_positions, set_opening_balance,
)
from app.services.invoice_service import create_receipt
from app.services.supplier_payment_service import cancel_supplier_payment, create_supplier_payment
from tests.test_credit_note_restock_and_caps import _ids, _sold_product
from tests.test_supplier_payments import _setup


async def _account(db, company_id):
    bank, currency = Bank(acronym="BAI", full_name="Banco Angolano de Investimentos"), Currency(code="AOX", name="Kwanza teste")
    db.add_all([bank, currency])
    await db.flush()
    account = CompanyBankAccount(company_id=company_id, bank_id=bank.id, account_number="0001", iban="000600001",
                                 currency_id=currency.id)
    db.add(account)
    await db.commit()
    return account.id


@pytest.mark.asyncio
async def test_the_statement_follows_receipts_and_supplier_payments(db, company_with_essentials):
    ctx = company_with_essentials
    ctx["pm_mb"].uses_bank_account = True  # Multicaixa lands on a bank account
    await db.commit()
    company_id, user = ctx["company"].id, ctx["gestor"]
    account_id = await _account(db, company_id)
    await set_opening_balance(db, company_id, account_id, 5000, date.today())

    ids = _ids(ctx)
    _product_id, invoice_id = await _sold_product(db, ids)
    await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=1000.0,
                         payment_method_id=ctx["pm_mb"].id, bank_account_id=account_id)
    _company, supplier_id, ft1, *_rest = await _setup(db, ctx)
    payment = await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": ft1, "amount": 1140}],
                                            ctx["pm_mb"].id, bank_account_id=account_id)

    [position] = await list_bank_positions(db, company_id)
    assert (position["bank"], position["balance"], position["movements"]) == ("BAI", 4860.0, 2)  # 5000 + 1000 - 1140

    await cancel_supplier_payment(db, company_id, payment.id, user, "Erro de valor")
    statement = await get_bank_statement(db, company_id, account_id)
    assert statement["opening"] == 5000.0 and statement["closing"] == 6000.0
    assert [(line["amount_in"], line["amount_out"]) for line in statement["lines"]] == [(1000.0, 0.0), (0.0, 1140.0), (1140.0, 0.0)]
    assert statement["lines"][-1]["balance"] == 6000.0 and "Anulação" in statement["lines"][-1]["description"]


@pytest.mark.asyncio
async def test_movements_before_the_opening_day_are_inside_the_opening_balance(db, company_with_essentials):
    ctx = company_with_essentials
    ctx["pm_mb"].uses_bank_account = True
    await db.commit()
    account_id = await _account(db, ctx["company"].id)
    ids = _ids(ctx)
    _product_id, invoice_id = await _sold_product(db, ids)
    await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=500.0,
                         payment_method_id=ctx["pm_mb"].id, bank_account_id=account_id)
    account = await db.get(CompanyBankAccount, account_id)
    account.opening_date, account.opening_balance = date.today() + timedelta(days=1), 800  # set directly: a later start
    await db.commit()
    statement = await get_bank_statement(db, ctx["company"].id, account_id)
    assert statement["lines"] == [] and statement["closing"] == 800.0
    with pytest.raises(InvalidOpeningBalanceError):
        await set_opening_balance(db, ctx["company"].id, account_id, 100, date.today() + timedelta(days=1))


@pytest.mark.asyncio
async def test_a_typed_bank_movement_and_its_cancellation(db, company_with_essentials):
    from app.models.movement_type import MovementDirection
    from app.services.bank_treasury_service import BankMovementError, cancel_bank_movement, create_bank_movement
    from app.services.cash_movement_service import create_cash_movement_reason
    ctx = company_with_essentials
    company_id, user = ctx["company"].id, ctx["gestor"]
    account_id = await _account(db, company_id)
    await set_opening_balance(db, company_id, account_id, 10000, date.today())
    fees = await create_cash_movement_reason(db, company_id, "Comissões bancárias", MovementDirection.SAIDA,
                                             for_cash=False, for_bank=True)
    till_only = await create_cash_movement_reason(db, company_id, "Fundo de maneio", MovementDirection.ENTRADA)

    movement = await create_bank_movement(db, company_id, user, account_id, fees.id, 250, date.today(), "EXT-11")
    assert (movement.series, movement.number) == (f"BCO{date.today().year}", 1)
    statement = await get_bank_statement(db, company_id, account_id)
    [line] = statement["lines"]
    assert (line["amount_out"], line["balance"], line["movement_id"]) == (250.0, 9750.0, movement.id)

    with pytest.raises(BankMovementError, match="motivo"):  # a reason of the tills only
        await create_bank_movement(db, company_id, user, account_id, till_only.id, 100, date.today())
    with pytest.raises(BankMovementError, match="saldo inicial"):  # before the opening day: already in that balance
        await create_bank_movement(db, company_id, user, account_id, fees.id, 100, date.today() - timedelta(days=1))

    await cancel_bank_movement(db, company_id, movement.id, user, "Comissão estornada pelo banco")
    statement = await get_bank_statement(db, company_id, account_id)
    assert [(l["amount_in"], l["amount_out"], l["movement_id"]) for l in statement["lines"]] == [(0.0, 250.0, None), (250.0, 0.0, None)]
    assert statement["closing"] == 10000.0
    with pytest.raises(BankMovementError, match="já está anulado"):
        await cancel_bank_movement(db, company_id, movement.id, user, "de novo")


@pytest.mark.asyncio
async def test_a_bank_reason_is_refused_at_the_till(db, company_with_essentials):
    from app.models.movement_type import MovementDirection
    from app.services.cash_movement_service import InvalidCashMovementError, create_cash_movement_reason
    ctx = company_with_essentials
    with pytest.raises(InvalidCashMovementError, match="onde o motivo"):
        await create_cash_movement_reason(db, ctx["company"].id, "Nada", MovementDirection.SAIDA, for_cash=False, for_bank=False)


@pytest.mark.asyncio
async def test_a_purchase_fatura_recibo_paid_from_the_bank(db, company_with_essentials):
    from app.models.supplier import Supplier
    from app.services.purchase_invoice_service import register_purchase_invoice
    from app.services.supplier_payment_service import supplier_statement
    from tests.test_purchase_invoices import _line, _rates
    ctx = company_with_essentials
    ctx["pm_mb"].uses_bank_account = True
    company_id, user = ctx["company"].id, ctx["gestor"]
    supplier = Supplier(company_id=company_id, name="Grossista do Kinaxixi", nif="5000333666")
    db.add(supplier)
    nor, _ = await _rates(db)
    await db.commit()
    supplier_id = supplier.id
    account_id = await _account(db, company_id)
    await set_opening_balance(db, company_id, account_id, 5000, date.today())
    fr = await register_purchase_invoice(
        db, company_id, user.id, supplier_id, "FR K/9", date.today(), [_line(nor)], purchase_type="FR", user=user,
        payment={"payment_method_id": ctx["pm_mb"].id, "bank_account_id": account_id, "reference": "TRF-9"})
    statement = await get_bank_statement(db, company_id, account_id)
    [line] = statement["lines"]
    assert line["amount_out"] == float(fr.total) and statement["closing"] == round(5000 - float(fr.total), 2)
    assert "TRF-9" in line["description"]
    # the supplier's account: the FR and its payment, never a second «Pago na emissão»
    descriptions = [e["description"] for e in (await supplier_statement(db, company_id, supplier_id))["lines"]]
    assert not any("Pago na emissão" in d for d in descriptions) and any(d.startswith("Pagamento") for d in descriptions)


@pytest.mark.asyncio
async def test_a_credit_note_refund_by_transfer_leaves_its_bank_account(db, company_with_essentials):
    from app.services.invoice_service import RefundNotAllowedError, create_credit_note
    from sqlalchemy import select as _select
    from app.models.invoice_line import InvoiceLine
    ctx = company_with_essentials
    ctx["pm_mb"].uses_bank_account = True
    await db.commit()
    company_id = ctx["company"].id
    account_id = await _account(db, company_id)
    await set_opening_balance(db, company_id, account_id, 0, date.today())
    ids = _ids(ctx)
    _product_id, invoice_id = await _sold_product(db, ids)
    await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=4560.0,
                         payment_method_id=ctx["pm_mb"].id, bank_account_id=account_id)  # paid in full on the bank
    line_id = (await db.execute(_select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice_id))).scalars().first()
    kwargs = dict(company_id=company_id, activity_id=ids["activity"], reference_invoice_id=invoice_id,
                  credit_note_reason="ANL", credit_note_cause="Devolução", lines_input=[{"invoice_line_id": line_id, "quantity": 1}],
                  refunds=[{"payment_method_id": ctx["pm_mb"].id, "amount": 1140.0}])
    with pytest.raises(RefundNotAllowedError, match="conta bancária"):
        await create_credit_note(db, **kwargs)
    await create_credit_note(db, **kwargs, refund_bank_account_id=account_id)
    statement = await get_bank_statement(db, company_id, account_id)
    assert [(l["amount_in"], l["amount_out"]) for l in statement["lines"]] == [(4560.0, 0.0), (0.0, 1140.0)]
