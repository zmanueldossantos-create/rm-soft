"""
Contabilidade - the entries the system makes from the purchases and the supplier payments: the cost of each line by
kind (goods, raw materials, services), the deductible VAT, the supplier's sub-account; a supplier's credit note
reversed; a payment from the bank (BCO) and from a till (CX); a cancelled purchase or payment reversed (estorno).
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.models.fiscal_regime import FiscalRegime
from app.models.journal import JournalEntry
from app.models.product import Product, ProductType
from app.models.supplier import Supplier
from app.services.accounting_integration_service import integrate_company
from app.services.cash_session_service import open_session
from app.services.chart_of_accounts_service import start_chart
from app.services.journal_service import get_entry
from app.services.purchase_invoice_service import cancel_purchase_invoice, register_purchase_invoice
from app.services.supplier_payment_service import cancel_supplier_payment, create_supplier_payment
from tests.test_purchase_invoices import _line, _rates


async def _entries_of(db, company_id, source_id):
    """The entries of a document: its own, then its estorno - [(label, [(code, debit, credit)])]."""
    out = []
    entry_id = (await db.execute(select(JournalEntry.id).where(JournalEntry.source_id == source_id))).scalar_one_or_none()
    while entry_id is not None:
        entry = await get_entry(db, company_id, entry_id)
        out.append((entry["label"], [(l["account_code"], float(l["debit"]), float(l["credit"])) for l in entry["lines"]]))
        entry_id = (await db.execute(select(JournalEntry.id).where(JournalEntry.reversal_of_id == entry_id))).scalar_one_or_none()
    return out


async def _setup(db, ctx):
    company = ctx["company"]
    regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id))).scalar_one()
    regime.input_vat_deductible_pct = 100
    ctx["pm_mb"].uses_bank_account = True
    supplier = Supplier(company_id=company.id, name="Grossista Lda", nif="5000111222")
    goods = Product(company_id=company.id, code="AGUA", name="Água", vat_id=ctx["vat_nor"].id, price=100,
                    min_stock_threshold=0, product_type=ProductType.BEM)
    flour = Product(company_id=company.id, code="FAR", name="Farinha", vat_id=ctx["vat_nor"].id, price=100,
                    min_stock_threshold=0, product_type=ProductType.BEM, is_raw_material=True)
    bank, kz = Bank(acronym="BAI", full_name="BAI"), Currency(code="AOA", name="Kwanza")
    db.add_all([supplier, goods, flour, bank, kz])
    nor, _ise = await _rates(db)
    await db.flush()
    account = CompanyBankAccount(company_id=company.id, bank_id=bank.id, account_number="0001", iban="AO060001", currency_id=kz.id)
    db.add(account)
    await db.commit()
    await start_chart(db, company.id, "PGC")
    return company.id, supplier.id, goods.id, flour.id, account.id, nor


@pytest.mark.asyncio
async def test_purchases_and_their_credit_note(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, supplier_id, goods_id, flour_id, _bank, nor = await _setup(db, ctx)
    user_id, today = ctx["gestor"].id, date.today()
    ft = await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT A/1", today, [
        _line(nor, product_id=goods_id),                            # 1000 + 140
        _line(nor, quantity=5, product_id=flour_id),                # 500 + 70
        _line(nor, quantity=1, price=200, description="Limpeza"),   # 200 + 28: a service
    ])
    ft_id = ft.id
    nc = await register_purchase_invoice(db, company_id, user_id, supplier_id, "NC A/1", today,
                                         [_line(nor, quantity=1, product_id=goods_id)], purchase_type="NC",
                                         reference_invoice_id=ft_id)
    nc_id = nc.id
    assert await integrate_company(db, company_id) == {"posted": 2, "pending": 0}
    year = today.year
    [(label, lines)] = await _entries_of(db, company_id, ft_id)
    assert label == f"CMP {year}/0001"
    assert lines == [("21.2", 1000.0, 0.0), ("21.1", 500.0, 0.0), ("75.2", 200.0, 0.0), ("34.5.2", 238.0, 0.0),
                     ("32.1.2.1", 0.0, 1938.0)]
    [(_label, lines)] = await _entries_of(db, company_id, nc_id)
    assert lines == [("21.2", 0.0, 100.0), ("34.5.2", 0.0, 14.0), ("32.1.2.1", 114.0, 0.0)]


@pytest.mark.asyncio
async def test_payments_and_cancellations_are_reversed(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, supplier_id, goods_id, _flour, bank_id, nor = await _setup(db, ctx)
    user, today = ctx["gestor"], date.today()
    ft1 = await register_purchase_invoice(db, company_id, user.id, supplier_id, "FT A/1", today, [_line(nor, product_id=goods_id)])
    ft2 = await register_purchase_invoice(db, company_id, user.id, supplier_id, "FT A/2", today, [_line(nor)])
    ft1_id, ft2_id = ft1.id, ft2.id
    by_bank = await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": ft1_id, "amount": 1140}],
                                            ctx["pm_mb"].id, bank_account_id=bank_id)
    by_bank_id = by_bank.id
    await db.refresh(user)
    await open_session(db, company_id, ctx["pos"].id, user, 1000)
    await db.refresh(user)
    in_cash = await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": ft2_id, "amount": 500}],
                                            ctx["pm_numerario"].id, pos_id=ctx["pos"].id)
    in_cash_id = in_cash.id
    assert await integrate_company(db, company_id) == {"posted": 4, "pending": 0}
    year = today.year
    [(label, lines)] = await _entries_of(db, company_id, by_bank_id)
    assert label == f"BCO {year}/0001" and lines == [("32.1.2.1", 1140.0, 0.0), ("43.1.1", 0.0, 1140.0)]
    [(label, lines)] = await _entries_of(db, company_id, in_cash_id)
    assert label == f"CX {year}/0001" and lines == [("32.1.2.1", 500.0, 0.0), ("45.1.1", 0.0, 500.0)]

    # cancelled after their entries: the payment, then its invoice - each entry gets its estorno
    await db.refresh(user)
    await cancel_supplier_payment(db, company_id, in_cash_id, user, "Valor errado")
    await cancel_purchase_invoice(db, company_id, ft2_id, user.id, "Fatura em duplicado")
    assert await integrate_company(db, company_id) == {"posted": 2, "pending": 0}
    entries = await _entries_of(db, company_id, in_cash_id)
    assert [label for label, _ in entries] == [f"CX {year}/0001", f"CX {year}/0002"]
    assert entries[1][1] == [("32.1.2.1", 0.0, 500.0), ("45.1.1", 500.0, 0.0)]
    entries = await _entries_of(db, company_id, ft2_id)
    assert [label for label, _ in entries] == [f"CMP {year}/0002", f"CMP {year}/0003"]
    assert (await integrate_company(db, company_id))["posted"] == 0  # reversed once
