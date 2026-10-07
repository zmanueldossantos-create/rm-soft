"""
Sale units of a product (see ProductSaleUnit): the other units it is sold in, each with a factor (base units
contained), a price and an optional barcode. The product itself stays the base unit.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.product import Product
from app.models.product_sale_unit import ProductSaleUnit
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog


class SaleUnitNotFoundError(Exception):
    """The product or the sale unit does not exist in this company."""


class SaleUnitInvalidError(Exception):
    """The sale unit breaks a rule (base unit, duplicate unit, barcode already used, factor)."""


class SaleUnitNeedsConfirmationError(Exception):
    """The sale unit looks inconsistent (price, factor): nothing is saved until the user confirms explicitly."""

    def __init__(self, warnings: list[str]):
        super().__init__("; ".join(warnings))
        self.warnings = warnings


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
    barcode: str | None, exclude_id: uuid.UUID | None = None, price: float | None = None, confirm: bool = False,
) -> None:
    if factor <= 0:
        raise SaleUnitInvalidError("O fator deve ser maior que zero")
    if abs(factor - 1) < 1e-9:
        raise SaleUnitInvalidError("Um fator de 1 e a propria unidade base do produto")
    if product.unit_of_measure_id and unit_of_measure_id == product.unit_of_measure_id:
        raise SaleUnitInvalidError("Esta ja e a unidade base do produto")
    unit = (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.id == unit_of_measure_id))).scalar_one_or_none()
    if unit is None:
        raise SaleUnitInvalidError("Unidade de medida invalida")
    base_code = (await db.execute(
        select(UnitOfMeasureCatalog.code).where(UnitOfMeasureCatalog.id == product.unit_of_measure_id)
    )).scalar_one_or_none() or "unidade base"
    # A universal unit (a dozen) always holds the same count: no product may redefine it.
    if unit.fixed_factor and abs(factor - float(unit.fixed_factor)) > 1e-9:
        raise SaleUnitInvalidError(f"A unidade {unit.code} contem sempre {float(unit.fixed_factor):g} {base_code}")
    same_unit = select(ProductSaleUnit.id).where(
        ProductSaleUnit.product_id == product.id, ProductSaleUnit.unit_of_measure_id == unit_of_measure_id,
    )
    if exclude_id is not None:
        same_unit = same_unit.where(ProductSaleUnit.id != exclude_id)
    if (await db.execute(same_unit)).first() is not None:
        raise SaleUnitInvalidError("Este produto ja tem esta unidade ou embalagem")
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
    if price is not None:
        await _consistency(db, company_id, product, unit.code, base_code, factor, price, exclude_id, confirm)


async def _consistency(
    db: AsyncSession, company_id: uuid.UUID, product: Product, unit_code: str, base_code: str, factor: float,
    price: float, exclude_id: uuid.UUID | None, confirm: bool,
) -> None:
    """Price and factor consistency, each check set per company: 'off', 'warn' (saved only once confirmed) or 'block'."""
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
    per_base = round(price / factor, 2)
    base_price = float(product.price or 0)
    purchase = float(product.purchase_price) if product.purchase_price is not None else None
    others = select(ProductSaleUnit.id).where(
        ProductSaleUnit.product_id == product.id, ProductSaleUnit.is_active.is_(True), ProductSaleUnit.factor == factor,
    )
    if exclude_id is not None:
        others = others.where(ProductSaleUnit.id != exclude_id)
    same_factor = (await db.execute(others)).first() is not None

    issues = []
    # A raw material is never sold: its packages carry no price, so price checks do not apply to it.
    if not product.is_raw_material and per_base > base_price + 0.005:
        issues.append((company.sale_unit_check_above_base,
                       f"Cada {base_code} sai a {per_base:.2f} na unidade {unit_code}, mais caro que a unidade base ({base_price:.2f})"))
    if not product.is_raw_material and purchase is not None and per_base < purchase - 0.005:
        issues.append((company.sale_unit_check_below_cost,
                       f"Venda abaixo do custo: cada {base_code} sai a {per_base:.2f}, preco de compra {purchase:.2f}"))
    if same_factor:
        issues.append((company.sale_unit_check_same_factor,
                       f"Outra unidade ou embalagem deste produto ja contem {factor:g} {base_code}"))
    for mode, message in issues:
        if mode == "block":
            raise SaleUnitInvalidError(message)
    warnings = [message for mode, message in issues if mode == "warn"]
    if warnings and not confirm:
        raise SaleUnitNeedsConfirmationError(warnings)


async def list_sale_units(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> list[ProductSaleUnit]:
    await _product(db, company_id, product_id)
    units = list((await db.execute(
        select(ProductSaleUnit).where(ProductSaleUnit.company_id == company_id, ProductSaleUnit.product_id == product_id)
        .order_by(ProductSaleUnit.factor)
    )).scalars().all())
    return await _attach_unit_codes(db, units)


async def create_sale_unit(
    db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, unit_of_measure_id: uuid.UUID, factor: float,
    price: float, barcode: str | None = None, confirm: bool = False,
) -> ProductSaleUnit:
    product = await _product(db, company_id, product_id)
    if product.is_raw_material:
        price = 0.0  # a raw material is never sold: its packages carry no price
    await _check(db, company_id, product, unit_of_measure_id, factor, barcode, price=price, confirm=confirm)
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
        raise SaleUnitNotFoundError("Unidade ou embalagem nao encontrada")
    return unit


async def update_sale_unit(
    db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, unit_id: uuid.UUID, unit_of_measure_id: uuid.UUID,
    factor: float, price: float, barcode: str | None = None, confirm: bool = False,
) -> ProductSaleUnit:
    product = await _product(db, company_id, product_id)
    unit = await _sale_unit(db, company_id, product_id, unit_id)
    if product.is_raw_material:
        price = 0.0  # a raw material is never sold: its packages carry no price
    await _check(db, company_id, product, unit_of_measure_id, factor, barcode, exclude_id=unit.id, price=price, confirm=confirm)
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


async def resolve_line_unit(
    db: AsyncSession, company_id: uuid.UUID, product: Product, sale_unit_id, quantity: float | None = None,
) -> tuple[float, float, uuid.UUID | None, str | None]:
    """
    THE unit conversion of a line, for selling and receiving alike: price, factor (base units in one unit), sale unit id
    and unit code. The product's base unit (factor 1) unless one of ITS active sale units is given. A decimal quantity is
    only allowed in a fractional unit (KG, L). Stock always moves quantity x factor.
    """
    if sale_unit_id:
        sale_unit = (await db.execute(
            select(ProductSaleUnit).where(
                ProductSaleUnit.id == sale_unit_id, ProductSaleUnit.product_id == product.id,
                ProductSaleUnit.company_id == company_id, ProductSaleUnit.is_active.is_(True),
            )
        )).scalar_one_or_none()
        if sale_unit is None:
            raise SaleUnitInvalidError(f"Unidade ou embalagem invalida ou inativa para {product.name}")
        unit_id, price, factor, line_sale_unit_id = sale_unit.unit_of_measure_id, float(sale_unit.price), float(sale_unit.factor), sale_unit.id
    else:
        unit_id, price, factor, line_sale_unit_id = product.unit_of_measure_id, float(product.price), 1.0, None
    unit = (await db.execute(
        select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.id == unit_id)
    )).scalar_one_or_none() if unit_id else None
    code = unit.code if unit else None
    if quantity is not None and abs(quantity - round(quantity)) > 1e-9 and not (unit and unit.is_fractional):
        raise SaleUnitInvalidError(f"{product.name}: a quantidade deve ser inteira ({code or 'unidade'})")
    return price, factor, line_sale_unit_id, code
