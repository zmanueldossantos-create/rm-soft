"""Transfer, loss and adjustment entered in one of the product's units: stock moves in base units, decimals refused
in a whole unit - the same conversion as sales and receptions."""
import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.product_sale_unit import ProductSaleUnit
from app.models.stock import Stock
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.stock_service import StockQuantityError, adjust_stock, record_stock_loss


async def _rice(db, ctx, code):
    """A product sold by the kilo (fractional) with a 25 kg bag, 100 kg in stock."""
    company_id = ctx["company"].id
    kilo = UnitOfMeasureCatalog(code="K" + code[-3:], name="Quilo " + code, is_fractional=True)
    bag = UnitOfMeasureCatalog(code="S" + code[-3:], name="Saco " + code)
    db.add_all([kilo, bag])
    await db.commit()
    await db.refresh(kilo)
    await db.refresh(bag)
    product = Product(company_id=company_id, code=code, name="Arroz " + code, vat_id=ctx["vat_nor"].id, price=900.0,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=kilo.id)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    sale_unit = ProductSaleUnit(company_id=company_id, product_id=product.id, unit_of_measure_id=bag.id, factor=25, price=21000)
    db.add_all([sale_unit, Stock(company_id=company_id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=100)])
    await db.commit()
    await db.refresh(sale_unit)
    return company_id, product.id, sale_unit.id, ctx["activity_warehouse"].id


async def _stock(db, product_id):
    return float((await db.execute(select(Stock.quantity).where(Stock.product_id == product_id))).scalar_one())


@pytest.mark.asyncio
async def test_a_loss_of_one_bag_removes_its_kilos(db, company_with_essentials):
    company_id, product_id, bag_id, warehouse_id = await _rice(db, company_with_essentials, "SU-001")
    await record_stock_loss(db, company_id, warehouse_id, product_id, 1, "QUEBRA", "Saco rasgado", sale_unit_id=bag_id)
    assert await _stock(db, product_id) == 75.0
    from app.models.stock_movement import StockMovement
    reason = (await db.execute(select(StockMovement.reason).where(StockMovement.product_id == product_id))).scalar_one()
    assert reason == "Saco rasgado (1 S001 = 25 K001)"  # what was typed, kept beside the base quantity


@pytest.mark.asyncio
async def test_a_transfer_of_two_bags_keeps_what_was_typed(db, company_with_essentials):
    from app.models.stock_movement import StockMovement
    from app.models.warehouse import Warehouse
    from app.services.stock_service import transfer_stock
    ctx = company_with_essentials
    company_id, product_id, bag_id, warehouse_id = await _rice(db, ctx, "SU-004")
    other = Warehouse(company_id=company_id, name="Armazém 2")
    db.add(other)
    await db.commit()
    await transfer_stock(db, company_id, product_id, warehouse_id, other.id, 2, sale_unit_id=bag_id)
    reasons = (await db.execute(select(StockMovement.reason).where(StockMovement.product_id == product_id))).scalars().all()
    assert reasons == ["2 S004 = 50 K004", "2 S004 = 50 K004"]  # both legs of the transfer


@pytest.mark.asyncio
async def test_an_adjustment_counted_in_bags(db, company_with_essentials):
    company_id, product_id, bag_id, warehouse_id = await _rice(db, company_with_essentials, "SU-002")
    await adjust_stock(db, company_id, warehouse_id, product_id, 2, "Contagem em sacos", sale_unit_id=bag_id)
    assert await _stock(db, product_id) == 50.0


@pytest.mark.asyncio
async def test_half_a_bag_is_refused(db, company_with_essentials):
    company_id, product_id, bag_id, warehouse_id = await _rice(db, company_with_essentials, "SU-003")
    with pytest.raises(StockQuantityError, match="deve ser inteira"):
        await record_stock_loss(db, company_id, warehouse_id, product_id, 1.5, "QUEBRA", None, sale_unit_id=bag_id)
    assert await _stock(db, product_id) == 100.0
