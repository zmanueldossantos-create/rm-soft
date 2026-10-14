"""Point 12 (Faturas de compra): a supplier invoice is registered with the VAT the supplier charged; the company
deducts the share its regime allows (data of the regime), the rest is a cost. A supplier of Angola needs its NIF, the
same supplier document is never registered twice, and a registration is cancelled - never deleted."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.fiscal_regime import FiscalRegime
from app.models.legal_vat_rate import LegalVatRate
from app.models.supplier import Supplier
from app.models.vat_code import VatCode
from app.services.purchase_invoice_service import (
    PurchaseInvoiceError, cancel_purchase_invoice, get_purchase_invoice, list_purchase_invoices, register_purchase_invoice,
)
from app.services.supplier_service import SupplierNifRequiredError, create_supplier


async def _rates(db):
    async def rate(category, value):
        found = (await db.execute(select(LegalVatRate).where(LegalVatRate.tax_category == category))).scalar_one_or_none()
        if found is None:
            found = LegalVatRate(tax_category=category, name=category, rate=value)
            db.add(found)
            await db.flush()
        return found
    return await rate("NOR", 14), await rate("ISE", 0)


async def _setup(db, ctx, pct):
    company = ctx["company"]
    regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id))).scalar_one()
    regime.input_vat_deductible_pct = pct
    supplier = Supplier(company_id=company.id, name="Grossista Lda", nif="5000111222")
    db.add(supplier)
    nor, ise = await _rates(db)
    await db.commit()
    return supplier, nor, ise


def _line(rate, quantity=10, price=100, **extra):
    return {"description": "Farinha", "quantity": quantity, "unit_price": price, "legal_vat_rate_id": rate.id, **extra}


@pytest.mark.asyncio
@pytest.mark.parametrize("pct,deductible,cost", [(100, 140.0, 1000.0), (7, 9.8, 1130.2), (0, 0.0, 1140.0)])
async def test_the_regime_decides_the_deductible_vat(db, company_with_essentials, pct, deductible, cost):
    ctx = company_with_essentials
    supplier, nor, _ = await _setup(db, ctx, pct)
    invoice = await register_purchase_invoice(db, ctx["company"].id, ctx["gestor"].id, supplier.id, "FT A/1",
                                              date.today(), [_line(nor)])
    detail = await get_purchase_invoice(db, ctx["company"].id, invoice.id)
    assert detail["description"] is None  # the line's text never becomes the invoice's description
    assert (detail["subtotal"], detail["vat_total"], detail["total"]) == (1000.0, 140.0, 1140.0)
    assert (detail["vat_deductible"], detail["lines"][0]["cost"]) == (deductible, cost)
    assert detail["reference"] == f"COMP{date.today().year}/1"


@pytest.mark.asyncio
async def test_an_exempt_line_needs_its_motive_and_a_document_is_registered_once(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    supplier, nor, ise = await _setup(db, ctx, 100)
    with pytest.raises(PurchaseInvoiceError, match="motivo de isenção"):
        await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/2", date.today(), [_line(ise)])
    motive = (await db.execute(select(VatCode))).scalars().first()
    invoice = await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/2", date.today(),
                                              [_line(ise, exemption_id=motive.id)])
    with pytest.raises(PurchaseInvoiceError, match="já está registado"):
        await register_purchase_invoice(db, company_id, user_id, supplier.id, "ft a/2", date.today(), [_line(nor)])

    await cancel_purchase_invoice(db, company_id, invoice.id, user_id, "Registada em duplicado")
    listed = await list_purchase_invoices(db, company_id)
    assert [(i["supplier_document"], i["status"]) for i in listed] == [("FT A/2", "ANULADA")]
    await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/2", date.today(), [_line(nor)])  # again


@pytest.mark.asyncio
async def test_a_supplier_of_angola_needs_its_nif(db, company_with_essentials):
    with pytest.raises(SupplierNifRequiredError):
        await create_supplier(db, company_with_essentials["company"].id, "Sem NIF")


async def _flour_in_sacks(db, ctx):
    """Flour counted in kilos, bought in 20 kg sacks; the system's automatic entry and exit types."""
    from app.models.movement_type import MovementDirection, MovementType
    from app.models.product import Product, ProductType
    from app.models.product_sale_unit import ProductSaleUnit
    from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
    company_id = ctx["company"].id
    kilo = UnitOfMeasureCatalog(code="KPI", name="Quilo compra", is_fractional=True)
    sack = UnitOfMeasureCatalog(code="SPI", name="Saco compra")
    db.add_all([kilo, sack,
                MovementType(code="EAP", name="Entrada automática", direction=MovementDirection.ENTRADA, is_auto=True),
                MovementType(code="SAP", name="Saída automática", direction=MovementDirection.SAIDA, is_auto=True)])
    await db.flush()
    flour = Product(company_id=company_id, code="MP-FPI", name="Farinha", vat_id=None, price=0, min_stock_threshold=0,
                    product_type=ProductType.BEM, is_raw_material=True, unit_of_measure_id=kilo.id)
    db.add(flour)
    await db.flush()
    sack_unit = ProductSaleUnit(company_id=company_id, product_id=flour.id, unit_of_measure_id=sack.id, factor=20, price=0)
    db.add(sack_unit)
    await db.commit()
    return flour.id, sack_unit.id


async def _quantity(db, product_id):
    from app.models.stock import Stock
    return float((await db.execute(select(Stock.quantity).where(Stock.product_id == product_id))).scalar_one())


@pytest.mark.asyncio
async def test_the_invoice_brings_its_products_into_stock_at_their_cost_and_its_cancellation_takes_them_out(
        db, company_with_essentials):
    from app.models.product import Product
    from app.models.stock import Stock
    ctx = company_with_essentials
    company_id, user_id, warehouse_id = ctx["company"].id, ctx["gestor"].id, ctx["activity_warehouse"].id
    supplier, nor, _ = await _setup(db, ctx, 7)
    supplier_id, nor_id = supplier.id, nor.id
    flour_id, sack_id = await _flour_in_sacks(db, ctx)
    line = {"product_id": flour_id, "sale_unit_id": sack_id, "quantity": 10, "unit_price": 10000, "legal_vat_rate_id": nor_id}

    with pytest.raises(PurchaseInvoiceError, match="armazém"):
        await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT S/1", date.today(), [line], stock_entry=True)
    with pytest.raises(PurchaseInvoiceError, match="linha de produto"):
        await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT S/1", date.today(),
                                        [{**line, "product_id": None, "sale_unit_id": None, "description": "Renda"}],
                                        stock_entry=True, warehouse_id=warehouse_id)

    # 10 sacks at 10 000: HT 100 000, VAT 14 000 of which 7 % deductible (980) - the cost is 113 020 for 200 kg
    invoice = await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT S/1", date.today(), [line],
                                              stock_entry=True, warehouse_id=warehouse_id)
    invoice_id = invoice.id
    detail = await get_purchase_invoice(db, company_id, invoice_id)
    year = date.today().year
    assert (detail["lines"][0]["unit"], detail["lines"][0]["cost"]) == ("SPI", 113020.0)
    assert (detail["stock_entry_reference"], detail["warehouse_name"]) == (f"EAP{year}/1", ctx["activity_warehouse"].name)
    assert await _quantity(db, flour_id) == 200.0
    cost = (await db.execute(select(Product.average_cost).where(Product.id == flour_id))).scalar_one()
    assert float(cost) == 565.1

    # the flour was used: the cancellation cannot take it out again - nothing changes
    stock = (await db.execute(select(Stock).where(Stock.product_id == flour_id))).scalar_one()
    stock.quantity = 50
    await db.commit()
    with pytest.raises(PurchaseInvoiceError, match="Não é possível anular"):
        await cancel_purchase_invoice(db, company_id, invoice_id, user_id, "Erro")
    assert (await get_purchase_invoice(db, company_id, invoice_id))["status"] == "REGISTADA"

    stock = (await db.execute(select(Stock).where(Stock.product_id == flour_id))).scalar_one()
    stock.quantity = 200
    await db.commit()
    await cancel_purchase_invoice(db, company_id, invoice_id, user_id, "Erro")
    detail = await get_purchase_invoice(db, company_id, invoice_id)
    assert (detail["status"], detail["stock_exit_reference"]) == ("ANULADA", f"SAP{year}/1")
    assert await _quantity(db, flour_id) == 0.0


@pytest.mark.asyncio
async def test_a_user_document_never_uses_an_automatic_type(db, company_with_essentials):
    from app.services.movement_document_service import MovementTypeNotConfiguredError, create_stock_movement_document
    ctx = company_with_essentials
    flour_id, _ = await _flour_in_sacks(db, ctx)
    from app.models.movement_type import MovementType
    automatic = (await db.execute(select(MovementType).where(MovementType.code == "EAP"))).scalar_one()
    with pytest.raises(MovementTypeNotConfiguredError, match="reservado"):
        await create_stock_movement_document(db, ctx["company"].id, automatic.id, ctx["activity_warehouse"].id,
                                             [{"product_id": flour_id, "quantity": 1, "purchase_price": 0}])
