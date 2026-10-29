"""Preço 1 / 2 / 3: a product and each of its sale units may carry two more prices; the line sold keeps the level
chosen, the server reads the price itself; Preço 2 / 3 and a free price are allowed per till (the gestor always)."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.issuable import ensure_line_prices
from app.models.invoice_line import InvoiceLine
from app.models.product import Product, ProductType
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.user import UserRole
from app.schemas.invoice import InvoiceLineCreateRequest
from app.services.invoice_service import LinePriceError, ProductNotFoundError, create_invoice
from app.services.product_sale_unit_service import SaleUnitInvalidError, create_sale_unit, resolve_line_unit


async def _product(db, ctx):
    product = Product(company_id=ctx["company"].id, code="PAO", name="Pão", vat_id=ctx["vat_nor"].id, price=1000.0,
                      price_2=900.0, min_stock_threshold=0, product_type=ProductType.BEM,
                      unit_of_measure_id=ctx["unit_un"].id)
    box = UnitOfMeasureCatalog(code="CX10", name="Caixa de 10")
    db.add_all([product, box])
    await db.commit()
    await db.refresh(product)
    await db.refresh(box)
    unit = await create_sale_unit(db, ctx["company"].id, product.id, box.id, 10, 9500, price_2=9000.0, confirm=True)
    return product, unit


@pytest.mark.asyncio
async def test_the_price_of_each_level(db, company_with_essentials):
    ctx = company_with_essentials
    product, unit = await _product(db, ctx)
    company_id = ctx["company"].id
    assert (await resolve_line_unit(db, company_id, product, None))[0] == 1000.0
    assert (await resolve_line_unit(db, company_id, product, None, price_level=2))[0] == 900.0
    assert (await resolve_line_unit(db, company_id, product, unit.id, price_level=2))[0] == 9000.0
    with pytest.raises(SaleUnitInvalidError, match="não tem Preço 3"):
        await resolve_line_unit(db, company_id, product, None, price_level=3)


@pytest.mark.asyncio
async def test_the_line_keeps_the_level_sold(db, company_with_essentials):
    ctx = company_with_essentials
    product, unit = await _product(db, ctx)
    invoice = await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                                   lines_input=[{"product_id": product.id, "quantity": 2, "price_level": 2},
                                                {"product_id": product.id, "sale_unit_id": unit.id, "quantity": 1}],
                                   deduct_stock=False)
    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
                              .order_by(InvoiceLine.line_number))).scalars().all()
    assert [(float(l.unit_price), l.price_level) for l in lines] == [(900.0, 2), (9500.0, 1)]
    with pytest.raises(ProductNotFoundError, match="não tem Preço 3"):
        await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                             lines_input=[{"product_id": product.id, "quantity": 1, "price_level": 3}], deduct_stock=False)


@pytest.mark.asyncio
async def test_preco_2_3_and_the_free_price_are_allowed_per_till(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, pos = ctx["company"].id, ctx["pos"]
    level_2 = [InvoiceLineCreateRequest(product_id=company_id, quantity=1, price_level=2)]
    free = [InvoiceLineCreateRequest(product_id=company_id, quantity=1, free_price=3200)]
    level_1 = [InvoiceLineCreateRequest(product_id=company_id, quantity=1)]
    caixa = SimpleNamespace(company_id=company_id, role=UserRole.CAIXA)
    gestor = SimpleNamespace(company_id=company_id, role=UserRole.GESTOR)
    await ensure_line_prices(db, caixa, level_1, pos.id)  # Preço 1: nothing more needed
    for lines in (level_2, free):
        with pytest.raises(HTTPException) as refused:
            await ensure_line_prices(db, caixa, lines, pos.id)
        assert refused.value.status_code == 403
        await ensure_line_prices(db, gestor, lines, pos.id)  # the gestor always may
        await ensure_line_prices(db, gestor, lines)  # in the Faturas too
        with pytest.raises(HTTPException):  # the Faturas (no till): only the gestor
            await ensure_line_prices(db, caixa, lines)
    pos.allow_price_levels = True  # set by the gestor on the till, like the billetage
    await db.commit()
    await ensure_line_prices(db, caixa, level_2, pos.id)
    with pytest.raises(HTTPException, match="alterar o preço"):
        await ensure_line_prices(db, caixa, free, pos.id)
    pos.allow_free_price = True
    await db.commit()
    await ensure_line_prices(db, caixa, free, pos.id)
    with pytest.raises(ValueError):
        InvoiceLineCreateRequest(product_id=company_id, quantity=1, price_level=4)
    with pytest.raises(ValueError):  # never 0
        InvoiceLineCreateRequest(product_id=company_id, quantity=1, free_price=0)


@pytest.mark.asyncio
async def test_a_free_price_is_traced_and_never_under_the_cost_unconfirmed(db, company_with_essentials):
    ctx = company_with_essentials
    product, unit = await _product(db, ctx)
    product.purchase_price = 700.0
    await db.commit()

    async def sell(**line):
        return await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                                    lines_input=[{"product_id": product.id, "quantity": 1, **line}], deduct_stock=False)

    invoice = await sell(free_price=850.0)
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))).scalar_one()
    assert (float(line.unit_price), line.price_level, float(line.catalog_unit_price)) == (850.0, 0, 1000.0)
    with pytest.raises(LinePriceError, match="abaixo do custo"):
        await sell(free_price=600.0)
    invoice = await sell(free_price=600.0, below_cost_ok=True)  # confirmed by the seller
    with pytest.raises(LinePriceError, match="abaixo do custo"):  # the box of 10 costs 7 000
        await sell(free_price=6500.0, sale_unit_id=unit.id)
