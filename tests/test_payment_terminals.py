"""
Tesouraria - the payment terminals (TPA / Multicaixa Express): a card payment at the till lands on the bank account of
its terminal - taken by itself when only one fits, chosen by the cashier when several do; the bank statement shows it.
"""
import pytest

from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.stock import Stock
from app.models.company_payment_method_preference import CompanyPaymentMethodPreference
from app.services.bank_treasury_service import get_bank_statement
from app.services.cash_session_service import open_session
from app.services.payment_terminal_service import (
    PaymentTerminalError, TerminalChoiceError, create_terminal, list_pos_terminals, toggle_terminal,
)
from app.services.pos_service import checkout
from tests.test_bank_treasury import _account
from tests.test_pos_service import _make_product


async def _till(db, ctx):
    """A product in stock, an open till, a card method (lands on a bank) next to cash and Multicaixa."""
    company = ctx["company"]
    card = PaymentMethodCatalog(code="CD", name="Cartão de débito", uses_bank_account=True)
    db.add(card)
    await db.flush()
    db.add(CompanyPaymentMethodPreference(company_id=company.id, payment_method_id=card.id, available_at_pos=True))
    ctx["pm_mb"].uses_bank_account = True
    product = await _make_product(db, company, ctx["vat_ise"], exemption_reason_id=ctx["exemption_m11"].id, price=1000.0)
    db.add(Stock(company_id=company.id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=50))
    await db.commit()
    await open_session(db, company.id, ctx["pos"].id, ctx["gestor"], opening_amount=0)
    return card, product


async def _sell(db, ctx, product, payments, terminal_id=None):
    return await checkout(db, ctx["company"].id, ctx["pos"].id, ctx["gestor"], None,
                          [{"product_id": product.id, "quantity": 1}], payments, terminal_id=terminal_id)


@pytest.mark.asyncio
async def test_a_card_payment_lands_on_the_bank_of_its_terminal(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    card, product = await _till(db, ctx)
    account_id = await _account(db, company_id)
    terminal = await create_terminal(db, company_id, "TPA Balcão", "TPA", account_id, ctx["pos"].id, [card.id])

    # cash + card: the card part goes through the only terminal there is
    invoice = await _sell(db, ctx, product, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 400.0},
                                             {"payment_method_id": card.id, "amount": 600.0}])
    await db.commit()
    assert (invoice.bank_account_id, invoice.terminal_id) == (account_id, terminal["id"])
    statement = await get_bank_statement(db, company_id, account_id)
    [line] = statement["lines"]
    assert line["amount_in"] == 600.0 and "TPA Balcão" in line["description"]

    # cash only: no terminal, no bank
    invoice = await _sell(db, ctx, product, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 1000.0}])
    assert (invoice.bank_account_id, invoice.terminal_id) == (None, None)


@pytest.mark.asyncio
async def test_with_several_terminals_the_cashier_chooses(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    card, product = await _till(db, ctx)
    account_id = await _account(db, company_id)
    await create_terminal(db, company_id, "TPA 1", "TPA", account_id, ctx["pos"].id, [card.id])
    second = await create_terminal(db, company_id, "TPA móvel", "TPA", account_id, None, [card.id])  # any till
    assert [t["name"] for t in await list_pos_terminals(db, company_id, ctx["pos"].id)] == ["TPA 1", "TPA móvel"]

    card_payment = [{"payment_method_id": card.id, "amount": 1000.0}]
    with pytest.raises(TerminalChoiceError, match="Escolha o terminal"):
        await _sell(db, ctx, product, card_payment)
    invoice = await _sell(db, ctx, product, card_payment, terminal_id=second["id"])
    assert invoice.terminal_id == second["id"]

    await toggle_terminal(db, company_id, second["id"])  # deactivated: the other one is taken by itself again
    with pytest.raises(TerminalChoiceError, match="não recebe"):
        await _sell(db, ctx, product, card_payment, terminal_id=second["id"])
    invoice = await _sell(db, ctx, product, card_payment)
    assert invoice.terminal_id != second["id"] and invoice.terminal_id is not None


@pytest.mark.asyncio
async def test_one_document_one_terminal_and_the_terminal_rules(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    card, product = await _till(db, ctx)
    account_id = await _account(db, company_id)
    await create_terminal(db, company_id, "TPA", "TPA", account_id, None, [card.id])
    await create_terminal(db, company_id, "Express", "EXPRESS", account_id, None, [ctx["pm_mb"].id])
    with pytest.raises(TerminalChoiceError, match="só pode passar por um terminal"):
        await _sell(db, ctx, product, [{"payment_method_id": card.id, "amount": 500.0},
                                       {"payment_method_id": ctx["pm_mb"].id, "amount": 500.0}])

    with pytest.raises(PaymentTerminalError, match="Já existe"):
        await create_terminal(db, company_id, "tpa", "TPA", account_id, None, [card.id])
    with pytest.raises(PaymentTerminalError, match="entram numa conta bancária"):  # cash has no bank
        await create_terminal(db, company_id, "Outro", "TPA", account_id, None, [ctx["pm_numerario"].id])
    with pytest.raises(PaymentTerminalError, match="pelo menos uma"):
        await create_terminal(db, company_id, "Outro", "TPA", account_id, None, [])


@pytest.mark.asyncio
async def test_a_supplier_keeps_the_iban_of_its_transfers(db, company_with_essentials):
    from app.services.supplier_service import create_supplier, update_supplier
    company_id = company_with_essentials["company"].id
    supplier = await create_supplier(db, company_id, "Moagem do Sul", nif="5000000001", iban="ao06 0040 0000 1234")
    assert supplier.iban == "AO06004000001234"  # without spaces, in capitals
    supplier = await update_supplier(db, company_id, supplier.id, "Moagem do Sul", nif="5000000001", iban="  ")
    assert supplier.iban is None
