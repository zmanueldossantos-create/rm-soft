"""
Sale units of a product (see ProductSaleUnit): the other units it is sold in, each with a factor (base units
contained), a price and an optional barcode. The product itself stays the base unit.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_sale_unit import ProductSaleUnit
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog


class SaleUnitNotFoundError(Exception):
    """The product or the sale unit does not exist in this company."""


class SaleUnitInvalidError(Exception):
    """The sale unit breaks a rule (base unit, duplicate unit, barcode already used, factor)."""


async def _product(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = (await db.execute(
        select(Product).where(Product.id == product_id, Product.company_id == company_id)
    )).scalar_one_or_none()
    if product is None:
        raise SaleUnitNotFoundError("Produto nao encontrado")
    return product


async def _attach_unit_codes(db: AsyncSession, units: list[ProductSaleUnit]) -> list[ProductSaleUnit]:
    ids = {u.unit_of_measure_id for u in units}
    codes = dict((await db.execute(
        select(UnitOfMeasureCatalog.id, UnitOfMeasureCatalog.code).where(UnitOfMeasureCatalog.id.in_(ids))
    )).all()) if ids else {}
    for u in units:
        u.unit_of_measure_code = codes.get(u.unit_of_measure_id)
    return units


async def _check(
    db: AsyncSession, company_id: uuid.UUID, product: Product, unit_of_measure_id: uuid.UUID, factor: float,
    barcode: str | None, exclude_id: uuid.UUID | None = None,
) -> None:
    if factor <= 0:
        raise SaleUnitInvalidError("O fator deve ser maior que zero")
    if product.unit_of_measure_id and unit_of_measure_id == product.unit_of_measure_id:
        raise SaleUnitInvalidError("Esta ja e a unidade base do produto")
    if (await db.execute(select(UnitOfMeasureCatalog.id).where(UnitOfMeasureCatalog.id == unit_of_measure_id))).scalar_one_or_none() is None:
        raise SaleUnitInvalidError("Unidade de medida invalida")
    same_unit = select(ProductSaleUnit.id).where(
        ProductSaleUnit.product_id == product.id, ProductSaleUnit.unit_of_measure_id == unit_of_measure_id,
    )
    if exclude_id is not None:
        same_unit = same_unit.where(ProductSaleUnit.id != exclude_id)
    if (await db.execute(same_unit)).first() is not None:
        raise SaleUnitInvalidError("Este produto ja tem esta unidade de venda")
    if barcode:
        # One barcode, one thing to sell, company wide: a product or a sale unit.
        on_product = (await db.execute(
            select(Product.id).where(Product.company_id == company_id, Product.barcode == barcode)
        )).first()
        on_unit = select(ProductSaleUnit.id).where(ProductSaleUnit.company_id == company_id, ProductSaleUnit.barcode == barcode)
        if exclude_id is not None:
            on_unit = on_unit.where(ProductSaleUnit.id != exclude_id)
        if on_product is not None or (await db.execute(on_unit)).first() is not None:
            raise SaleUnitInvalidError("Este codigo de barras ja esta em uso")


async def list_sale_units(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> list[ProductSaleUnit]:
    await _product(db, company_id, product_id)
    units = list((await db.execute(
        select(ProductSaleUnit).where(ProductSaleUnit.company_id == company_id, ProductSaleUnit.product_id == product_id)
        .order_by(ProductSaleUnit.factor)
    )).scalars().all())
    return await _attach_unit_codes(db, units)


async def create_sale_unit(
    db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, unit_of_measure_id: uuid.UUID, factor: float,
    price: float, barcode: str | None = None,
) -> ProductSaleUnit:
    product = await _product(db, company_id, product_id)
    await _check(db, company_id, product, unit_of_measure_id, factor, barcode)
    unit = ProductSaleUnit(
        company_id=company_id, product_id=product.id, unit_of_measure_id=unit_of_measure_id,
        factor=factor, price=price, barcode=barcode,
    )
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return (await _attach_unit_codes(db, [unit]))[0]


async def _sale_unit(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, unit_id: uuid.UUID) -> ProductSaleUnit:
    unit = (await db.execute(
        select(ProductSaleUnit).where(
            ProductSaleUnit.id == unit_id, ProductSaleUnit.product_id == product_id, ProductSaleUnit.company_id == company_id,
        )
    )).scalar_one_or_none()
    if unit is None:
        raise SaleUnitNotFoundError("Unidade de venda nao encontrada")
    return unit


async def update_sale_unit(
    db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, unit_id: uuid.UUID, unit_of_measure_id: uuid.UUID,
    factor: float, price: float, barcode: str | None = None,
) -> ProductSaleUnit:
    product = await _product(db, company_id, product_id)
    unit = await _sale_unit(db, company_id, product_id, unit_id)
    await _check(db, company_id, product, unit_of_measure_id, factor, barcode, exclude_id=unit.id)
    unit.unit_of_measure_id = unit_of_measure_id
    unit.factor = factor
    unit.price = price
    unit.barcode = barcode
    await db.commit()
    await db.refresh(unit)
    return (await _attach_unit_codes(db, [unit]))[0]


async def toggle_sale_unit(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, unit_id: uuid.UUID) -> ProductSaleUnit:
    unit = await _sale_unit(db, company_id, product_id, unit_id)
    unit.is_active = not unit.is_active
    await db.commit()
    await db.refresh(unit)
    return (await _attach_unit_codes(db, [unit]))[0]
