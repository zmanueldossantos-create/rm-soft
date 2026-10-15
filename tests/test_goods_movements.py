"""Point 1 (Guias): GR to a customer, GT between two warehouses, GD back to a supplier - issued like an invoice (the
type's series, hash, ATCUD) and moving the stock with them, in the unit entered; cancelled with a reason, the goods
come back. A GR is priced at the sale price with the product's VAT, a GT or a GD at the cost without VAT."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.document_type import DocumentType
from app.models.product import Product, ProductType
from app.models.product_sale_unit import ProductSaleUnit
from app.models.stock import Stock
from app.models.supplier import Supplier
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.warehouse import Warehouse
from app.services.goods_movement_service import (
    GoodsMovementError, cancel_goods_movement, create_goods_movement, get_goods_movement,
)


async def _setup(db, ctx):
    company_id = ctx["company"].id
    for code, name in (("GR", "Guia de Remessa"), ("GT", "Guia de Transporte"), ("GD", "Guia de Devolução")):
        if (await db.execute(select(DocumentType).where(DocumentType.code == code))).scalar_one_or_none() is None:
            db.add(DocumentType(code=code, name=name, area="FACTURACAO", is_fiscal=True, saft_section="MOVEMENTS"))
    kilo = UnitOfMeasureCatalog(code="KGG", name="Quilo guia", is_fractional=True)
    sack = UnitOfMeasureCatalog(code="SCG", name="Saco guia")
    db.add_all([kilo, sack])
    await db.flush()
    flour = Product(company_id=company_id, code="FAR-G", name="Farinha", vat_id=ctx["vat_nor"].id, price=1500,
                    min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=kilo.id, average_cost=1000)
    db.add(flour)
    await db.flush()
    sack_unit = ProductSaleUnit(company_id=company_id, product_id=flour.id, unit_of_measure_id=sack.id, factor=20, price=28000)
    customer = Customer(company_id=company_id, name="Hotel Kilamba", nif="5000222333", legal_person_type=LegalPersonType.JURIDICA,
                        address="Rua 1, Kilamba")
    supplier = Supplier(company_id=company_id, name="Moagem", nif="5000444555", address="Viana")
    other = Warehouse(company_id=company_id, name="Loja Talatona", address="Talatona")
    db.add_all([sack_unit, customer, supplier, other])
    await db.flush()
    origin = ctx["central_warehouse"].id
    db.add(Stock(company_id=company_id, product_id=flour.id, warehouse_id=origin, quantity=100))
    await db.commit()
    return company_id, ctx["gestor"].id, flour.id, sack_unit.id, customer.id, supplier.id, origin, other.id


async def _qty(db, product_id, warehouse_id):
    row = (await db.execute(select(Stock.quantity).where(Stock.product_id == product_id, Stock.warehouse_id == warehouse_id))).scalar_one_or_none()
    return float(row or 0)


@pytest.mark.asyncio
async def test_a_remittance_guide_takes_the_goods_out_at_the_sale_price(db, company_with_essentials):
    company_id, user_id, flour, sack, customer, _, origin, _ = await _setup(db, company_with_essentials)
    with pytest.raises(GoodsMovementError, match="cliente"):
        await create_goods_movement(db, company_id, user_id, "GR", origin, [{"product_id": flour, "quantity": 1}])
    with pytest.raises(GoodsMovementError, match="anterior"):
        await create_goods_movement(db, company_id, user_id, "GR", origin, [{"product_id": flour, "quantity": 1}],
                                    start_time=datetime.now(timezone.utc) - timedelta(hours=1), customer_id=customer)
    with pytest.raises(GoodsMovementError, match="Stock insuficiente"):
        await create_goods_movement(db, company_id, user_id, "GR", origin,
                                    [{"product_id": flour, "sale_unit_id": sack, "quantity": 6}], customer_id=customer)
    assert await _qty(db, flour, origin) == 100.0  # nothing moved

    guide = await create_goods_movement(db, company_id, user_id, "GR", origin,
                                        [{"product_id": flour, "sale_unit_id": sack, "quantity": 2}],
                                        customer_id=customer, vehicle_plate="ld-12-34-ab")
    guide_id = guide.id
    detail = await get_goods_movement(db, company_id, guide_id)
    assert detail["reference"].startswith("GR ") and detail["reference"].endswith("/1")
    assert (detail["party"], detail["unload_address"], detail["vehicle_plate"]) == ("Hotel Kilamba", "Rua 1, Kilamba", "LD-12-34-AB")
    line = detail["lines"][0]
    assert (line["unit"], line["quantity"], line["unit_price"], line["tax_code"], line["line_vat"]) == ("SCG", 2.0, 28000.0, "NOR", 7840.0)
    assert detail["gross_total"] == 63840.0
    assert await _qty(db, flour, origin) == 60.0

    await cancel_goods_movement(db, company_id, guide_id, user_id, "Cliente recusou")
    assert (await get_goods_movement(db, company_id, guide_id))["status"] == "ANULADA"
    assert await _qty(db, flour, origin) == 100.0
    with pytest.raises(GoodsMovementError, match="já está anulada"):
        await cancel_goods_movement(db, company_id, guide_id, user_id, "outra vez")


@pytest.mark.asyncio
async def test_a_transport_guide_transfers_and_a_return_guide_goes_back_to_the_supplier(db, company_with_essentials):
    company_id, user_id, flour, _, _, supplier, origin, shop = await _setup(db, company_with_essentials)
    with pytest.raises(GoodsMovementError, match="diferente"):
        await create_goods_movement(db, company_id, user_id, "GT", origin, [{"product_id": flour, "quantity": 1}],
                                    destination_warehouse_id=origin)
    transport = await create_goods_movement(db, company_id, user_id, "GT", origin, [{"product_id": flour, "quantity": 30}],
                                            destination_warehouse_id=shop)
    transport_id = transport.id
    assert (await _qty(db, flour, origin), await _qty(db, flour, shop)) == (70.0, 30.0)
    detail = await get_goods_movement(db, company_id, transport_id)
    assert (detail["lines"][0]["unit_price"], detail["vat_total"], detail["unload_address"]) == (1000.0, 0.0, "Talatona")

    devolution = await create_goods_movement(db, company_id, user_id, "GD", origin, [{"product_id": flour, "quantity": 10}],
                                             supplier_id=supplier)
    assert (await get_goods_movement(db, company_id, devolution.id))["party"] == "Moagem"
    assert await _qty(db, flour, origin) == 60.0

    # the goods moved on: the transport cannot be undone any more
    stock = (await db.execute(select(Stock).where(Stock.product_id == flour, Stock.warehouse_id == shop))).scalar_one()
    stock.quantity = 5
    await db.commit()
    with pytest.raises(GoodsMovementError, match="Não é possível anular"):
        await cancel_goods_movement(db, company_id, transport_id, user_id, "Erro")
    stock = (await db.execute(select(Stock).where(Stock.product_id == flour, Stock.warehouse_id == shop))).scalar_one()
    stock.quantity = 30
    await db.commit()
    await cancel_goods_movement(db, company_id, transport_id, user_id, "Erro")
    assert (await _qty(db, flour, origin), await _qty(db, flour, shop)) == (90.0, 0.0)


@pytest.mark.asyncio
async def test_a_guide_prints(db, company_with_essentials):
    from app.services.cash_report_service import _company_dict
    from app.utils.guia_pdf import generate_guia_pdf
    company_id, user_id, flour, sack, customer, _, origin, _ = await _setup(db, company_with_essentials)
    guide = await create_goods_movement(db, company_id, user_id, "GR", origin,
                                        [{"product_id": flour, "sale_unit_id": sack, "quantity": 2}], customer_id=customer)
    data = await get_goods_movement(db, company_id, guide.id)
    assert generate_guia_pdf(data, _company_dict(company_with_essentials["company"])).startswith(b"%PDF")
