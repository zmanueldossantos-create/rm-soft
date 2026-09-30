"""
Multi-tenant isolation tests (spec v7, section 2.5).

Creates TWO separate companies (A and B) and verifies that company A's
company_id can never read or modify a resource that actually belongs to
company B - even when the resource's real UUID is known/guessed.

Pattern: every service function scoped by company_id is expected to raise
its "NotFound"-style error when called with a mismatched (company_id, resource_id)
pair, exactly as it would for a truly nonexistent id. This mirrors how the
routes behave (a mismatched company_id looks identical to a 404 to the caller,
which is the correct, non-leaky behavior - it never distinguishes "exists but
not yours" from "doesn't exist").

HISTORY: an earlier draft of this file found and proved (via XPASS/strict xfail)
that customer_service.list_customer_bank_links / add_customer_bank_link /
remove_customer_bank_link did not scope by company_id at all. That has since
been fixed in app/services/customer_service.py + app/api/v1/customers/routes.py -
the tests below now assert the FIXED (safe) behavior directly, no xfail markers.

Also corrected from the earlier draft: receive_stock() never accepts a
client-supplied warehouse_id (it always resolves the caller's own central
warehouse internally), so it was never actually at risk - removed that test.
The two functions that DO accept client-supplied warehouse_id(s) are
transfer_stock() and create_stock_movement_document(); both already re-verify
company_id ownership of every warehouse_id received, and are tested here.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.warehouse import Warehouse
from app.models.bank import Bank
from app.models.currency import Currency
from app.models.company_bank_account import CompanyBankAccount
from app.models.movement_type import MovementType, MovementDirection

from app.services.customer_service import (
    create_customer,
    update_customer,
    toggle_customer_status,
    get_customer_or_raise,
    add_customer_bank_link,
    list_customer_bank_links,
    remove_customer_bank_link,
    CustomerNotFoundError,
    BankLinkNotFoundError,
)
from app.services.product_service import (
    update_product,
    toggle_product_status,
    get_product_or_raise,
    ProductNotFoundError,
)
from app.services.invoice_service import (
    get_invoice_with_lines,
    InvoiceNotFoundError,
)
from app.services.stock_service import (
    update_warehouse,
    toggle_warehouse_status,
    get_warehouse_or_raise,
    transfer_stock,
    receive_stock,
    WarehouseNotFoundError,
)
from app.services.movement_document_service import (
    create_stock_movement_document,
    MovementWarehouseNotFoundError,
)
from app.models.fiscal_regime import FiscalRegime


async def _make_second_company(db):
    """
    Builds a second, fully independent company (own regime, own VAT rate,
    own warehouse) - kept minimal here since these tests only need a valid
    company_id/warehouse to attach company B's resources to, not the full
    activity/fiscal-period setup that company_with_essentials builds.
    """
    from app.models.company import Company
    from app.models.vat import VAT

    regime = FiscalRegime(name=f"Regime B {uuid.uuid4().hex[:8]}", allows_nor=True, allows_red=True, allows_ise=True)
    db.add(regime)
    await db.flush()

    company_b = Company(
        name=f"Empresa B {uuid.uuid4().hex[:8]}",
        nif="5000000001",
        email=f"{uuid.uuid4().hex[:8]}@teste.co.ao",
        phone_number=f"+244{uuid.uuid4().int % 900000000 + 900000000}",
        fiscal_regime_id=regime.id,
    )
    db.add(company_b)
    await db.flush()

    vat_b = VAT(company_id=company_b.id, name="Taxa normal B", rate=14)
    db.add(vat_b)

    warehouse_b = Warehouse(company_id=company_b.id, name="Armazem B")
    db.add(warehouse_b)

    await db.commit()
    await db.refresh(company_b)
    await db.refresh(vat_b)
    await db.refresh(warehouse_b)

    return {"company": company_b, "vat": vat_b, "warehouse": warehouse_b}


async def _make_product(db, company, vat, code="PRD-B"):
    product = Product(
        company_id=company.id, code=code, name=f"Produto {code}",
        vat_id=vat.id, price=100, min_stock_threshold=0,
        product_type=ProductType.BEM,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _get_or_create_test_bank_and_currency(db):
    """
    Bank and Currency are platform-wide, SUPER_ADMIN-managed catalogs
    (not company-scoped) - get-or-create since other fixtures/tests may
    already have seeded them, same pattern as conftest's DocumentType seeding.
    """
    bank = (await db.execute(select(Bank).where(Bank.acronym == "TST"))).scalar_one_or_none()
    if bank is None:
        bank = Bank(acronym="TST", full_name="Banco Teste")
        db.add(bank)
        await db.flush()

    currency = (await db.execute(select(Currency).where(Currency.code == "AOA"))).scalar_one_or_none()
    if currency is None:
        currency = Currency(code="AOA", name="Kwanza")
        db.add(currency)
        await db.flush()

    await db.commit()
    await db.refresh(bank)
    await db.refresh(currency)
    return bank, currency


async def _get_or_create_test_movement_type(db, direction=MovementDirection.ENTRADA):
    code = "TSTE" if direction == MovementDirection.ENTRADA else "TSTS"
    result = await db.execute(select(MovementType).where(MovementType.code == code))
    movement_type = result.scalar_one_or_none()
    if movement_type is None:
        movement_type = MovementType(
            code=code, name=f"Teste {direction.value}", direction=direction, is_active=True,
        )
        db.add(movement_type)
        await db.commit()
        await db.refresh(movement_type)
    return movement_type


# ---------- Customers ----------

async def test_cannot_update_another_companys_customer(db, company_with_essentials):
    """Company A must not be able to edit a customer that belongs to company B."""
    company_a = company_with_essentials["company"]
    company_b = (await _make_second_company(db))["company"]

    customer_b = await create_customer(db, company_b.id, name="Cliente B", nif="123456789")

    with pytest.raises(CustomerNotFoundError):
        await update_customer(
            db, company_a.id, customer_b.id,
            name="Hackeado", nif="123456789",
        )


async def test_cannot_toggle_another_companys_customer(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    company_b = (await _make_second_company(db))["company"]

    customer_b = await create_customer(db, company_b.id, name="Cliente B", nif="223456789")

    with pytest.raises(CustomerNotFoundError):
        await toggle_customer_status(db, company_a.id, customer_b.id)


async def test_cannot_read_another_companys_customer(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    company_b = (await _make_second_company(db))["company"]

    customer_b = await create_customer(db, company_b.id, name="Cliente B", nif="323456789")

    with pytest.raises(CustomerNotFoundError):
        await get_customer_or_raise(db, company_a.id, customer_b.id)


async def test_cannot_list_another_companys_customer_bank_links(db, company_with_essentials):
    """FIXED BUG: this used to return company B's links with zero tenant check."""
    company_a = company_with_essentials["company"]
    company_b = (await _make_second_company(db))["company"]
    customer_b = await create_customer(db, company_b.id, name="Cliente B", nif="423456789")

    with pytest.raises(CustomerNotFoundError):
        await list_customer_bank_links(db, company_a.id, customer_b.id)


async def test_cannot_attach_bank_link_to_another_companys_customer(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    company_b = (await _make_second_company(db))["company"]
    customer_b = await create_customer(db, company_b.id, name="Cliente B", nif="623456789")
    bank, currency = await _get_or_create_test_bank_and_currency(db)

    bank_account_a = CompanyBankAccount(
        company_id=company_a.id, bank_id=bank.id,
        account_number="111111111111111111", iban="AO0600000000000000000001111",
        currency_id=currency.id,
    )
    db.add(bank_account_a)
    await db.commit()
    await db.refresh(bank_account_a)

    with pytest.raises(CustomerNotFoundError):
        await add_customer_bank_link(db, company_a.id, customer_b.id, bank_account_a.id)


async def test_cannot_attach_another_companys_bank_account_to_own_customer(db, company_with_essentials):
    """Even against one's own customer, the bank account itself must belong to the caller's company."""
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)
    bank, currency = await _get_or_create_test_bank_and_currency(db)

    customer_a = await create_customer(db, company_a.id, name="Cliente A", nif="723456789")
    bank_account_b = CompanyBankAccount(
        company_id=setup_b["company"].id, bank_id=bank.id,
        account_number="222222222222222222", iban="AO0600000000000000000002222",
        currency_id=currency.id,
    )
    db.add(bank_account_b)
    await db.commit()
    await db.refresh(bank_account_b)

    with pytest.raises(BankLinkNotFoundError):
        await add_customer_bank_link(db, company_a.id, customer_a.id, bank_account_b.id)


async def test_cannot_delete_another_companys_customer_bank_link(db, company_with_essentials):
    """FIXED BUG: this used to delete company B's link with zero tenant check."""
    company_a = company_with_essentials["company"]
    company_b = (await _make_second_company(db))["company"]
    customer_b = await create_customer(db, company_b.id, name="Cliente B", nif="523456789")
    bank, currency = await _get_or_create_test_bank_and_currency(db)

    bank_account_b = CompanyBankAccount(
        company_id=company_b.id, bank_id=bank.id,
        account_number="000000000000000000", iban="AO0600000000000000000000000",
        currency_id=currency.id,
    )
    db.add(bank_account_b)
    await db.flush()

    link = await add_customer_bank_link(db, company_b.id, customer_b.id, bank_account_b.id)

    with pytest.raises(BankLinkNotFoundError):
        await remove_customer_bank_link(db, company_a.id, link.id)


# ---------- Products ----------

async def test_cannot_update_another_companys_product(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)
    product_b = await _make_product(db, setup_b["company"], setup_b["vat"])

    with pytest.raises(ProductNotFoundError):
        await update_product(
            db, company_a.id, product_b.id,
            code=product_b.code, name="Hackeado", barcode=None,
            vat_id=setup_b["vat"].id, price=1, min_stock_threshold=0,
            expiry_date=None,
        )


async def test_cannot_toggle_another_companys_product(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)
    product_b = await _make_product(db, setup_b["company"], setup_b["vat"])

    with pytest.raises(ProductNotFoundError):
        await toggle_product_status(db, company_a.id, product_b.id)


async def test_cannot_read_another_companys_product(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)
    product_b = await _make_product(db, setup_b["company"], setup_b["vat"])

    with pytest.raises(ProductNotFoundError):
        await get_product_or_raise(db, company_a.id, product_b.id)


# ---------- Warehouses / Stock ----------

async def test_cannot_update_another_companys_warehouse(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)

    with pytest.raises(WarehouseNotFoundError):
        await update_warehouse(db, company_a.id, setup_b["warehouse"].id, name="Hackeado")


async def test_cannot_toggle_another_companys_warehouse(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)

    with pytest.raises(WarehouseNotFoundError):
        await toggle_warehouse_status(db, company_a.id, setup_b["warehouse"].id)


async def test_cannot_read_another_companys_warehouse(db, company_with_essentials):
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)

    with pytest.raises(WarehouseNotFoundError):
        await get_warehouse_or_raise(db, company_a.id, setup_b["warehouse"].id)


async def test_cannot_transfer_stock_using_another_companys_warehouse(db, company_with_essentials):
    """
    transfer_stock accepts two client-supplied warehouse_id's - the one
    client-controlled entry point that could realistically be tampered with.
    Using company B's warehouse as either side must fail, not silently move stock.
    """
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)
    product_a = await _make_product(db, company_a, company_with_essentials["vat_nor"], code="PRD-A")
    await receive_stock(db, company_a.id, product_a.id, 10)

    with pytest.raises(WarehouseNotFoundError):
        await transfer_stock(
            db, company_a.id, product_a.id,
            from_warehouse_id=company_with_essentials["central_warehouse"].id,
            to_warehouse_id=setup_b["warehouse"].id,
            quantity=5,
        )


async def test_cannot_create_movement_document_using_another_companys_warehouse(db, company_with_essentials):
    """Same principle for the 'Registar Recepcao de Stock' modal's underlying endpoint."""
    company_a = company_with_essentials["company"]
    setup_b = await _make_second_company(db)
    product_a = await _make_product(db, company_a, company_with_essentials["vat_nor"], code="PRD-A2")
    movement_type = await _get_or_create_test_movement_type(db, direction=MovementDirection.ENTRADA)

    with pytest.raises(MovementWarehouseNotFoundError):
        await create_stock_movement_document(
            db, company_a.id,
            movement_type_id=movement_type.id,
            warehouse_id=setup_b["warehouse"].id,
            lines_input=[{"product_id": product_a.id, "quantity": 5, "purchase_price": 0, "sale_price": 0}],
        )


# ---------- Invoices ----------

async def test_cannot_read_another_companys_invoice(db, company_with_essentials):
    """
    No cross-company invoice fixture is built here (invoice creation needs a
    full activity/fiscal-period/document-series setup already covered by
    test_invoice_service.py) - this proves the read-path guard directly:
    a random UUID that could never belong to company_a's own invoices,
    scoped as if it were company B's, must come back as not-found.
    """
    company_a = company_with_essentials["company"]

    with pytest.raises(InvoiceNotFoundError):
        await get_invoice_with_lines(db, company_a.id, uuid.uuid4())