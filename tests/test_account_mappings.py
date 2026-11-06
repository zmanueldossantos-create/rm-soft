"""
Contabilidade - «Contas por operação» (suggested from the PGC, changed by the company) and the sub-accounts the system
makes: one per bank account, till, customer and supplier, numbered under their parent, made once; an account in use
cannot be deleted.
"""
from datetime import date

import pytest

from app.models.account import AccountLink
from app.models.bank import Bank
from app.models.company_bank_account import CompanyBankAccount
from app.models.currency import Currency
from app.models.customer import Customer
from app.models.supplier import Supplier
from app.services.account_mapping_service import list_mappings, set_mapping, set_options, sync_subaccounts
from app.services.chart_of_accounts_service import ChartError, delete_account, get_chart, start_chart
from sqlalchemy import select


@pytest.mark.asyncio
async def test_the_pgc_suggests_the_accounts_of_the_operations(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await start_chart(db, company_id, "PGC")
    rows = {r["key"]: r for r in (await list_mappings(db, company_id))["operations"]}
    assert rows["VAT_OUTPUT"]["account_code"] == "34.5.3" and rows["SALES_SERVICES"]["account_code"] == "62.1.1"
    assert rows["CASH_SHORTAGE"]["account_id"] is None  # the accountant decides
    chart = {a["code"]: a for a in (await get_chart(db, company_id))["accounts"]}
    await set_mapping(db, company_id, "VAT_OUTPUT", chart["34.5"]["id"])  # the company's own choice
    assert {r["key"]: r for r in (await list_mappings(db, company_id))["operations"]}["VAT_OUTPUT"]["account_code"] == "34.5"
    with pytest.raises(ChartError, match="Contas por operação"):
        await delete_account(db, company_id, chart["62.1.1"]["id"])


@pytest.mark.asyncio
async def test_one_subaccount_per_bank_till_customer_and_supplier(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    bank, kz = Bank(acronym="BAI", full_name="BAI"), Currency(code="AOA", name="Kwanza")
    db.add_all([bank, kz])
    await db.flush()
    db.add_all([
        CompanyBankAccount(company_id=company_id, bank_id=bank.id, account_number="0001", iban="AO060001", currency_id=kz.id),
        Customer(company_id=company_id, name="Hotel Atlântico", nif="5000111999", registration_date=date.today()),
        Customer(company_id=company_id, name="Consumidor final", nif="999999999", is_final_consumer=True,
                 registration_date=date.today()),
        Supplier(company_id=company_id, name="Moagem do Sul", nif="5000222888"),
    ])
    await db.commit()
    result = await sync_subaccounts(db, company_id)  # no chart yet: nothing, every parent missing
    assert result["created"] == 0 and "Fornecedores" in result["missing_parent"]

    await start_chart(db, company_id, "PGC")
    result = await sync_subaccounts(db, company_id)
    codes = {a["code"]: a["name"] for a in (await get_chart(db, company_id))["accounts"]}
    assert codes["43.1.1"] == "BAI · 0001" and codes["31.1.2.1.1"] == "Hotel Atlântico (5000111999)"
    assert codes["32.1.2.1"].startswith("Moagem do Sul") and codes["45.1.1"].startswith(ctx["pos"].name)
    assert not any(name.startswith("Consumidor final") for name in codes.values())
    assert (await sync_subaccounts(db, company_id))["created"] == 0  # made once

    await set_options(db, company_id, per_customer=False, per_supplier=True)
    db.add(Customer(company_id=company_id, name="Outro", nif="5000777666", registration_date=date.today()))
    await db.commit()
    assert (await sync_subaccounts(db, company_id))["created"] == 0  # customers on the parent account itself
    links = (await db.execute(select(AccountLink).where(AccountLink.company_id == company_id))).scalars().all()
    bank_link = next(l for l in links if l.entity_kind == "BANK")
    with pytest.raises(ChartError, match="subconta de uma conta bancária"):
        await delete_account(db, company_id, bank_link.account_id)


@pytest.mark.asyncio
async def test_a_new_customer_supplier_or_till_gets_its_subaccount_at_once(db, company_with_essentials):
    """Once the chart is started, each new customer, supplier and caixa gets its sub-account when it is saved."""
    from app.services.customer_service import create_customer
    from app.services.point_of_sale_service import create_point_of_sale
    from app.services.supplier_service import create_supplier
    ctx = company_with_essentials
    company_id = ctx["company"].id
    chart = await start_chart(db, company_id, "PGC")
    assert any(a["code"] == "45.1.1" for a in chart["accounts"])  # the caixa that existed: at the PGC's loading
    customer = await create_customer(db, company_id, "Restaurante Ilha", "5000999111")
    supplier = await create_supplier(db, company_id, "Padaria Grossista", nif="5000999222")
    till = await create_point_of_sale(db, company_id, ctx["pos"].activity_id, "Balcão 2")
    assert customer.name == "Restaurante Ilha" and supplier.name == "Padaria Grossista" and till.name == "Balcão 2"
    names = {a["code"]: a["name"] for a in (await get_chart(db, company_id))["accounts"]}
    assert names["31.1.2.1.1"].startswith("Restaurante Ilha") and names["32.1.2.1"].startswith("Padaria Grossista")
    assert names["45.1.2"].startswith("Balcão 2")
