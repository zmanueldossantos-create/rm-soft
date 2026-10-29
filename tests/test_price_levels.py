"""Preço 1 / 2 / 3: a product and each of its sale units may carry two more prices; the line sold keeps the level
chosen, the server reads the price itself; choosing Preço 2 / 3 needs the permission invoices:price_levels."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.issuable import ensure_price_levels
from app.models.invoice_line import InvoiceLine
from app.models.product import Product, ProductType
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.user import UserRole
from app.schemas.invoice import InvoiceLineCreateRequest
from app.services.invoice_service import ProductNotFoundError, create_invoice
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
async def test_choosing_preco_2_or_3_needs_the_permission(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    level_2 = [InvoiceLineCreateRequest(product_id=company_id, quantity=1, price_level=2)]
    level_1 = [InvoiceLineCreateRequest(product_id=company_id, quantity=1)]
    caixa = SimpleNamespace(company_id=company_id, role=UserRole.CAIXA)
    await ensure_price_levels(db, caixa, level_1)  # Preço 1: nothing more needed
    with pytest.raises(HTTPException) as refused:
        await ensure_price_levels(db, caixa, level_2)
    assert refused.value.status_code == 403
    await ensure_price_levels(db, SimpleNamespace(company_id=company_id, role=UserRole.GESTOR), level_2)
    with pytest.raises(ValueError):
        InvoiceLineCreateRequest(product_id=company_id, quantity=1, price_level=4)
