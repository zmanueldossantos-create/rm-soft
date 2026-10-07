import pytest

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.movement_type import MovementType, MovementDirection
from app.services.movement_document_service import (
    create_stock_movement_document,
    InsufficientStockForMovementError,
)
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def _make_product(db, company, vat, code="PROD-MV"):
    product = Product(
        company_id=company.id, code=code, name="Produto Movimento",
        vat_id=vat.id, price=100.0, min_stock_threshold=0,
        product_type=ProductType.BEM,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _make_movement_type(db, code, direction):
    mt = MovementType(code=code, name=f"Teste {code}", direction=direction, is_auto=False)
    db.add(mt)
    await db.commit()
    await db.refresh(mt)
    return mt


async def test_create_stock_movement_document_entrada_increases_stock(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"])
    entrada_type = await _make_movement_type(db, "ENT", MovementDirection.ENTRADA)

    doc = await create_stock_movement_document(
        db, company.id, entrada_type.id, setup["activity_warehouse"].id,
        lines_input=[{"product_id": product.id, "quantity": 15, "purchase_price": 200.0, "sale_price": 250.0}],
    )

    assert doc.series == f"ENT{doc.movement_date.year}"
    assert doc.number == 1
    assert float(doc.total_value) == 3000.0  # 15 x 200 (purchase price, since ENTRADA)

    stock_result = await db.execute(select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id))
    stock = stock_result.scalar_one()
    assert float(stock.quantity) == 15.0


async def test_create_stock_movement_document_saida_decreases_stock_and_rejects_insufficient(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], code="PROD-MV2")
    entrada_type = await _make_movement_type(db, "ENT2", MovementDirection.ENTRADA)
    saida_type = await _make_movement_type(db, "SAI2", MovementDirection.SAIDA)

    await create_stock_movement_document(
        db, company.id, entrada_type.id, setup["activity_warehouse"].id,
        lines_input=[{"product_id": product.id, "quantity": 10, "purchase_price": 50.0, "sale_price": 80.0}],
    )

    doc = await create_stock_movement_document(
        db, company.id, saida_type.id, setup["activity_warehouse"].id,
        lines_input=[{"product_id": product.id, "quantity": 4, "purchase_price": 50.0, "sale_price": 80.0}],
    )
    assert float(doc.total_value) == 320.0  # 4 x 80 (sale price, since SAIDA)

    stock_result = await db.execute(select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id))
    stock = stock_result.scalar_one()
    assert float(stock.quantity) == 6.0  # 10 - 4

    with pytest.raises(InsufficientStockForMovementError):
        await create_stock_movement_document(
            db, company.id, saida_type.id, setup["activity_warehouse"].id,
            lines_input=[{"product_id": product.id, "quantity": 100, "purchase_price": 50.0, "sale_price": 80.0}],
        )


from app.models.product_sale_unit import ProductSaleUnit  # noqa: E402
from app.models.stock import Stock  # noqa: E402
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog  # noqa: E402
from app.services.movement_document_service import MovementDirection, MovementProductNotFoundError  # noqa: E402


async def _product_in_bags(db, setup, code):
    product = await _make_product(db, setup["company"], setup["vat_nor"], code=code)
    kilo = UnitOfMeasureCatalog(code="K" + code[-3:], name="Quilo " + code, is_fractional=True)
    bag = UnitOfMeasureCatalog(code="S" + code[-3:], name="Saco " + code)
    db.add_all([kilo, bag])
    await db.commit()
    await db.refresh(kilo)
    await db.refresh(bag)
    product.unit_of_measure_id = kilo.id
    sale_unit = ProductSaleUnit(company_id=setup["company"].id, product_id=product.id, unit_of_measure_id=bag.id, factor=25, price=21000)
    db.add(sale_unit)
    await db.commit()
    await db.refresh(sale_unit)
    return product, sale_unit, bag.code


@pytest.mark.asyncio
async def test_a_reception_in_bags_moves_base_units(db, company_with_essentials):
    setup = company_with_essentials
    product, bag_unit, bag_code = await _product_in_bags(db, setup, "MV-SC1")
    entrada = await _make_movement_type(db, "ENS", MovementDirection.ENTRADA)
    doc = await create_stock_movement_document(
        db, setup["company"].id, entrada.id, setup["activity_warehouse"].id,
        lines_input=[{"product_id": product.id, "quantity": 2, "sale_unit_id": bag_unit.id, "purchase_price": 17500.0, "sale_price": 21000.0}],
    )
    stock = (await db.execute(select(Stock).where(Stock.product_id == product.id))).scalar_one()
    assert float(stock.quantity) == 50.0
    from app.models.stock_movement_document import StockMovementDocumentLine
    line = (await db.execute(select(StockMovementDocumentLine).where(StockMovementDocumentLine.document_id == doc.id))).scalar_one()
    assert (float(line.quantity), float(line.unit_factor), line.unit_snapshot, line.sale_unit_id) == (2.0, 25.0, bag_code, bag_unit.id)


@pytest.mark.asyncio
async def test_half_a_bag_is_refused_at_reception(db, company_with_essentials):
    setup = company_with_essentials
    product, bag_unit, _ = await _product_in_bags(db, setup, "MV-SC2")
    entrada = await _make_movement_type(db, "ENT2", MovementDirection.ENTRADA)
    with pytest.raises(MovementProductNotFoundError, match="deve ser inteira"):
        await create_stock_movement_document(
            db, setup["company"].id, entrada.id, setup["activity_warehouse"].id,
            lines_input=[{"product_id": product.id, "quantity": 1.5, "sale_unit_id": bag_unit.id, "purchase_price": 0, "sale_price": 0}],
        )


@pytest.mark.asyncio
async def test_a_movement_date_lies_between_its_period_start_and_today(db, company_with_essentials):
    from datetime import date, timedelta
    from app.services.fiscal_period_service import PeriodClosedError
    setup = company_with_essentials
    product = await _make_product(db, setup["company"], setup["vat_nor"], code="MV-DT1")
    entrada = await _make_movement_type(db, "END", MovementDirection.ENTRADA)
    line = [{"product_id": product.id, "quantity": 1, "purchase_price": 0, "sale_price": 0}]
    with pytest.raises(PeriodClosedError, match="nao pode ser futura"):
        await create_stock_movement_document(db, setup["company"].id, entrada.id, setup["activity_warehouse"].id,
                                             lines_input=line, movement_date=date.today() + timedelta(days=1))
    with pytest.raises(PeriodClosedError, match="anterior ao periodo escolhido"):
        await create_stock_movement_document(db, setup["company"].id, entrada.id, setup["activity_warehouse"].id,
                                             lines_input=line, movement_date=date.today().replace(day=1) - timedelta(days=1))


@pytest.mark.asyncio
async def test_priced_receptions_move_the_average_cost(db, company_with_essentials):
    setup = company_with_essentials
    product, bag_unit, _ = await _product_in_bags(db, setup, "MV-SC3")
    entrada = await _make_movement_type(db, "ENC", MovementDirection.ENTRADA)
    async def receive(lines):
        await create_stock_movement_document(db, setup["company"].id, entrada.id, setup["activity_warehouse"].id, lines_input=lines)
        await db.refresh(product)
        return float(product.average_cost)
    # 2 bags at 17 500 into an empty stock: 700 per kilo
    assert await receive([{"product_id": product.id, "quantity": 2, "sale_unit_id": bag_unit.id, "purchase_price": 17500, "sale_price": 0}]) == 700.0
    # 50 kg at 800 on top of 50 kg at 700: (50 x 700 + 50 x 800) / 100
    assert await receive([{"product_id": product.id, "quantity": 50, "purchase_price": 800, "sale_price": 0}]) == 750.0
    # 10 kg without a price: the quantity enters, the cost stays
    assert await receive([{"product_id": product.id, "quantity": 10, "purchase_price": 0, "sale_price": 0}]) == 750.0


@pytest.mark.asyncio
async def test_the_stock_summary_values_at_the_average_cost(db, company_with_essentials):
    from app.services.stock_service import get_stock_dashboard
    setup = company_with_essentials
    product, bag_unit, _ = await _product_in_bags(db, setup, "MV-SC4")
    entrada = await _make_movement_type(db, "END4", MovementDirection.ENTRADA)
    await create_stock_movement_document(db, setup["company"].id, entrada.id, setup["activity_warehouse"].id,
                                         lines_input=[{"product_id": product.id, "quantity": 1, "sale_unit_id": bag_unit.id, "purchase_price": 17500, "sale_price": 0}])
    summary = await get_stock_dashboard(db, setup["company"].id)
    item = next(i for i in summary["items"] if i["product_id"] == product.id)
    sale_price = float(product.price)
    assert (item["average_cost"], item["cost_value"], item["cost_unknown"]) == (700.0, 17500.0, False)
    assert item["margin_value"] == round(25 * sale_price - 17500, 2)
