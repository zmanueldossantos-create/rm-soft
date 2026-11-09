"""
Contabilidade - the entries the system makes from the sales documents: FR (sale and payment in one entry), FT
(goods), RC (on the bank, journal BCO), NC (returns); a document waiting with its reason until its account is set;
the start day and the Modo formação documents left out; the withholding kept by the customer.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.account import AccountingSettings
from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.models.customer import Customer, LegalPersonType
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.journal import JournalEntry
from app.models.product import Product, ProductType
from app.models.service import Service
from app.models.stock import Stock
from app.models.withholding_tax import WithholdingTax
from app.services.account_mapping_service import set_mapping
from app.services.accounting_integration_service import integrate_company, integration_status
from app.services.cash_session_service import open_session
from app.services.chart_of_accounts_service import get_chart, start_chart
from app.services.invoice_service import create_credit_note, create_invoice, create_receipt
from app.services.journal_service import get_entry


async def _entry_of(db, company_id, invoice_id):
    entry_id = (await db.execute(select(JournalEntry.id).where(JournalEntry.source_id == invoice_id))).scalar_one_or_none()
    if entry_id is None:
        return None
    entry = await get_entry(db, company_id, entry_id)
    return entry, [(l["account_code"], float(l["debit"]), float(l["credit"])) for l in entry["lines"]]


async def _setup(db, ctx):
    company_id = ctx["company"].id
    ctx["pm_mb"].uses_bank_account = True
    bank, kz = Bank(acronym="BAI", full_name="BAI"), Currency(code="AOA", name="Kwanza")
    db.add_all([bank, kz])
    await db.flush()
    account = CompanyBankAccount(company_id=company_id, bank_id=bank.id, account_number="0001", iban="AO060001", currency_id=kz.id)
    customer = Customer(company_id=company_id, name="Hotel Atlântico", nif="5000111999", registration_date=date.today())
    service = Service(company_id=company_id, code="SRV-INT", name="Alojamento", price=1000.0, vat_id=ctx["vat_nor"].id)
    product = Product(company_id=company_id, code="PRD-INT", name="Água", vat_id=ctx["vat_nor"].id, price=500.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add_all([account, customer, service, product])
    await db.commit()
    db.add(Stock(company_id=company_id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=100))
    await db.commit()
    await start_chart(db, company_id, "PGC")
    return {"company": company_id, "activity": ctx["activity"].id, "bank": account.id, "customer": customer.id,
            "service": service.id, "product": product.id}


@pytest.mark.asyncio
async def test_sales_documents_are_posted(db, company_with_essentials):
    ctx = company_with_essentials
    ids = await _setup(db, ctx)
    company_id = ids["company"]
    session = await open_session(db, company_id, ctx["pos"].id, ctx["gestor"], opening_amount=0)
    fr = await create_invoice(db, company_id, ids["activity"], customer_id=ids["customer"], invoice_type="FACTURA_RECIBO",
                              lines_input=[{"service_id": ids["service"], "quantity": 1}], cash_session_id=session.id)
    ft = await create_invoice(db, company_id, ids["activity"], customer_id=ids["customer"], invoice_type="FACTURA",
                              lines_input=[{"product_id": ids["product"], "quantity": 4}])
    fr_id, ft_id = fr.id, ft.id
    rc = await create_receipt(db, company_id, ids["activity"], reference_invoice_id=ft_id, amount=1140.0,
                              payment_method_id=ctx["pm_mb"].id, bank_account_id=ids["bank"])
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == ft_id))).scalar_one()
    nc = await create_credit_note(db, company_id, ids["activity"], reference_invoice_id=ft_id, credit_note_reason="RTF",
                                  credit_note_cause="Devolução", lines_input=[{"invoice_line_id": line_id, "quantity": 1}])
    rc_id, nc_id = rc.id, nc.id

    assert await integrate_company(db, company_id) == {"posted": 4, "pending": 0}
    assert (await integrate_company(db, company_id))["posted"] == 0  # once per document

    year = date.today().year
    entry, lines = await _entry_of(db, company_id, fr_id)
    # the customer's sub-account (31.1.2.1.1 - Consumidor final is .2, made after it), the till of the cash session
    assert entry["label"] == f"VND {year}/0001" and entry["automatic"] and entry["document_ref"].startswith("FR ")
    assert entry["description"] == "Fatura-recibo - Hotel Atlântico"
    assert lines == [("31.1.2.1.1", 1140.0, 0.0), ("62.1.1", 0.0, 1000.0), ("34.5.3", 0.0, 140.0),
                     ("45.1.1", 1140.0, 0.0), ("31.1.2.1.1", 0.0, 1140.0)]
    entry, lines = await _entry_of(db, company_id, ft_id)
    assert entry["label"] == f"VND {year}/0002"
    assert lines == [("31.1.2.1.1", 2280.0, 0.0), ("61.3.1", 0.0, 2000.0), ("34.5.3", 0.0, 280.0)]
    entry, lines = await _entry_of(db, company_id, rc_id)
    assert entry["label"] == f"BCO {year}/0001"
    assert lines == [("43.1.1", 1140.0, 0.0), ("31.1.2.1.1", 0.0, 1140.0)]
    entry, lines = await _entry_of(db, company_id, nc_id)
    assert lines == [("31.1.2.1.1", 0.0, 570.0), ("61.7.1", 500.0, 0.0), ("34.5.3", 70.0, 0.0)]


@pytest.mark.asyncio
async def test_a_document_waits_until_its_account_is_set(db, company_with_essentials):
    ctx = company_with_essentials
    ids = await _setup(db, ctx)
    company_id = ids["company"]
    await set_mapping(db, company_id, "SALES_GOODS", None)
    ft = await create_invoice(db, company_id, ids["activity"], customer_id=None, invoice_type="FACTURA",
                              lines_input=[{"product_id": ids["product"], "quantity": 1}])
    ft_id = ft.id
    assert await integrate_company(db, company_id) == {"posted": 0, "pending": 1}
    status = await integration_status(db, company_id)
    assert status["waiting"] == 1 and "Vendas de mercadorias" in status["pending"][0]["reason"]
    chart = {a["code"]: a["id"] for a in (await get_chart(db, company_id))["accounts"]}
    await set_mapping(db, company_id, "SALES_GOODS", chart["61.3.1"])
    assert await integrate_company(db, company_id) == {"posted": 1, "pending": 0}
    assert (await integration_status(db, company_id))["pending"] == []
    _entry, lines = await _entry_of(db, company_id, ft_id)
    assert lines[0] == ("31.1.2.1.2", 570.0, 0.0)  # no customer: «Consumidor final»


@pytest.mark.asyncio
async def test_the_start_day_and_the_training_documents(db, company_with_essentials):
    ctx = company_with_essentials
    ids = await _setup(db, ctx)
    company_id = ids["company"]
    ft = await create_invoice(db, company_id, ids["activity"], customer_id=None, invoice_type="FACTURA",
                              lines_input=[{"product_id": ids["product"], "quantity": 1}])
    training = await create_invoice(db, company_id, ids["activity"], customer_id=None, invoice_type="FACTURA",
                                    lines_input=[{"product_id": ids["product"], "quantity": 1}])
    ft_id, training_id = ft.id, training.id
    (await db.get(Invoice, training_id)).issuance_mode = "FORMACAO"  # Modo formação: never in the accounting
    settings = await db.get(AccountingSettings, company_id)
    settings.integration_start = date.today() + timedelta(days=1)
    await db.commit()
    assert await integrate_company(db, company_id) == {"posted": 0, "pending": 0}
    settings.integration_start = date.today()
    await db.commit()
    assert await integrate_company(db, company_id) == {"posted": 1, "pending": 0}
    assert await _entry_of(db, company_id, ft_id) is not None and await _entry_of(db, company_id, training_id) is None


@pytest.mark.asyncio
async def test_the_withholding_kept_by_the_customer(db, company_with_essentials):
    ctx = company_with_essentials
    ids = await _setup(db, ctx)
    company_id = ids["company"]
    tax = WithholdingTax(name="Retenção", rate=6.5, tax_type="II")
    db.add(tax)
    customer = Customer(company_id=company_id, name="Empresa PJ", nif="5000111888", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    service = Service(company_id=company_id, code="SRV-RET", name="Consultoria", price=1000.0, vat_id=ctx["vat_nor"].id,
                      withholding_tax_id=tax.id)
    db.add(service)
    await db.commit()
    fr = await create_invoice(db, company_id, ids["activity"], customer_id=customer.id, invoice_type="FACTURA_RECIBO",
                              lines_input=[{"service_id": service.id, "quantity": 2}])  # 2280, withholding 130, paid 2150
    fr_id = fr.id
    status = await integrate_company(db, company_id)
    assert status == {"posted": 0, "pending": 1}  # «Retenção na fonte sofrida» has no account by default
    chart = {a["code"]: a["id"] for a in (await get_chart(db, company_id))["accounts"]}
    await set_mapping(db, company_id, "WITHHOLDING_SUFFERED", chart["34.1"])
    assert (await integrate_company(db, company_id))["posted"] == 1
    _entry, lines = await _entry_of(db, company_id, fr_id)
    sub = lines[0][0]
    assert lines == [(sub, 2280.0, 0.0), ("62.1.1", 0.0, 2000.0), ("34.5.3", 0.0, 280.0), ("45.1.1", 2150.0, 0.0),
                     (sub, 0.0, 2150.0), ("34.1", 130.0, 0.0), (sub, 0.0, 130.0)]
    assert sum(Decimal(str(l[1])) for l in lines) == sum(Decimal(str(l[2])) for l in lines)


@pytest.mark.asyncio
async def test_the_training_documents_in_a_demonstration(db, company_with_essentials):
    """A company in Modo formação may have its documents in the accounting; once they are no longer in it (the option
    off, or the company out of Modo formação), their entries get their estorno."""
    from app.models.company import Company
    from app.services.accounting_integration_service import IntegrationError, set_include_training
    ctx = company_with_essentials
    ids = await _setup(db, ctx)
    company_id = ids["company"]
    with pytest.raises(IntegrationError, match="Modo formação"):
        await set_include_training(db, company_id, True)
    (await db.get(Company, company_id)).training_mode = True
    await db.commit()
    ft = await create_invoice(db, company_id, ids["activity"], customer_id=None, invoice_type="FACTURA",
                              lines_input=[{"product_id": ids["product"], "quantity": 1}])
    ft_id = ft.id
    assert (await db.get(Invoice, ft_id)).issuance_mode == "FORMACAO"
    assert (await integrate_company(db, company_id))["posted"] == 0  # not asked: left out
    await set_include_training(db, company_id, True)
    assert (await integrate_company(db, company_id))["posted"] == 1
    entry_id = (await db.execute(select(JournalEntry.id).where(JournalEntry.source_id == ft_id))).scalar_one()

    (await db.get(Company, company_id)).training_mode = False  # the company starts for real
    await db.commit()
    assert (await integrate_company(db, company_id))["posted"] == 1  # the estorno
    estorno = (await db.execute(select(JournalEntry).where(JournalEntry.reversal_of_id == entry_id))).scalar_one()
    assert estorno.description.startswith("Estorno de VND")
    assert (await integrate_company(db, company_id))["posted"] == 0
