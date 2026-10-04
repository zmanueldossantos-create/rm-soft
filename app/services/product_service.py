"""
Business logic for product management.
Every query is scoped to the caller's company_id (multi-tenant isolation, section 2.5 v7) -
a GESTOR/ADMIN only ever sees and manages their own company's products.
Extended (Video 3) with category, brand, image, purchase price, the
managed-by-lote/stock/validade toggles, and richer status.
"""
from app.services.vat_rule_service import resolve_article_vat
import uuid
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.vat import VAT


class ProductAlreadyExistsError(Exception):
    """Raised when a product field (code, name or barcode) conflicts within the same company."""
    pass


class ProductNotFoundError(Exception):
    """Raised when a product id does not match any product in the caller's company."""
    pass


class ArticleUnitRequiredError(Exception):
    """A product or service saved without a base unit."""


class ExemptionReasonRequiredError(Exception):
    """Raised when the chosen VAT rate is 0% (isento) but no AGT exemption reason code was given."""
    pass


class VatRequiredError(ExemptionReasonRequiredError):
    """A product that can be sold needs a VAT rate. Subclass of ExemptionReasonRequiredError so the
    422 answer given for that error applies to it as well."""


def _check_vat_rule(vat_id: uuid.UUID | None, is_raw_material: bool) -> None:
    """A raw material is never sold (invoice, POS and open accounts refuse it), so it carries no VAT
    rate. Every other product must have one."""
    if vat_id is None and not is_raw_material:
        raise VatRequiredError("Taxa de IVA obrigatoria para este produto")


async def _check_all_fields_available(
    db: AsyncSession,
    company_id: uuid.UUID,
    code: str,
    name: str,
    barcode: str | None,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """
    Checks uniqueness within the company, in the same top-to-bottom order as
    the form fields (code, name, barcode) - all scoped to company_id, since
    the same code/name can exist across different companies (tenants).
    """
    code_query = select(Product).where(Product.company_id == company_id, Product.code == code)
    if exclude_id is not None:
        code_query = code_query.where(Product.id != exclude_id)
    if (await db.execute(code_query)).scalar_one_or_none() is not None:
        raise ProductAlreadyExistsError("Ja existe um produto registado com este codigo")

    name_query = select(Product).where(Product.company_id == company_id, func.lower(Product.name) == name.lower())
    if exclude_id is not None:
        name_query = name_query.where(Product.id != exclude_id)
    if (await db.execute(name_query)).scalar_one_or_none() is not None:
        raise ProductAlreadyExistsError("Ja existe um produto registado com este nome")

    if barcode:
        barcode_query = select(Product).where(Product.company_id == company_id, Product.barcode == barcode)
        if exclude_id is not None:
            barcode_query = barcode_query.where(Product.id != exclude_id)
        if (await db.execute(barcode_query)).scalar_one_or_none() is not None:
            raise ProductAlreadyExistsError("Ja existe um produto registado com este codigo de barras")


async def create_product(
    db: AsyncSession,
    company_id: uuid.UUID,
    code: str,
    name: str,
    barcode: str | None,
    vat_id: uuid.UUID | None,
    price: float,
    min_stock_threshold: float,
    expiry_date: date | None,
    product_type: str = "BEM",
    unit_of_measure_id: uuid.UUID | None = None,
    batch_yield: float = 1,
    is_raw_material: bool = False,
    category_id: uuid.UUID | None = None,
    brand: str | None = None,
    image_path: str | None = None,
    purchase_price: float | None = None,
    managed_by_batch: bool = False,
    managed_by_stock: bool = True,
    managed_by_expiry: bool = False,
    not_available_pos: bool = False,
    internal_use_only: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
) -> Product:
    """Creates a product within the caller's company."""
    await _check_all_fields_available(db, company_id, code, name, barcode)
    if unit_of_measure_id is None:  # every article has a base unit: the SAF-T and the documents show it
        raise ArticleUnitRequiredError("A unidade base e obrigatoria")
    _check_vat_rule(vat_id, is_raw_material)
    if is_raw_material:
        exemption_reason_id = None  # a raw material is never sold: no exemption to justify
    else:
        exemption_reason_id = await resolve_article_vat(db, company_id, vat_id, exemption_reason_id)

    product = Product(
        company_id=company_id,
        code=code,
        name=name,
        barcode=barcode,
        vat_id=vat_id,
        price=price,
        min_stock_threshold=min_stock_threshold,
        expiry_date=expiry_date,
        product_type=product_type,
        unit_of_measure_id=unit_of_measure_id,
        batch_yield=batch_yield,
        is_raw_material=is_raw_material,
        category_id=category_id,
        brand=brand,
        image_path=image_path,
        purchase_price=purchase_price,
        managed_by_batch=managed_by_batch,
        managed_by_stock=managed_by_stock,
        managed_by_expiry=managed_by_expiry,
        not_available_pos=not_available_pos,
        internal_use_only=internal_use_only,
        status=status,
        exemption_reason_id=exemption_reason_id,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def list_products(db: AsyncSession, company_id: uuid.UUID) -> list[Product]:
    """Lists all products belonging to the caller's company."""
    result = await db.execute(
        select(Product).where(Product.company_id == company_id).order_by(Product.created_at.desc())
    )
    products = list(result.scalars().all())
    # The unit code travels with each article: any screen that can list it (the Caixa included) shows its unit
    # without needing access to the units catalog.
    from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
    unit_ids = {a.unit_of_measure_id for a in products if a.unit_of_measure_id}
    codes = dict((await db.execute(
        select(UnitOfMeasureCatalog.id, UnitOfMeasureCatalog.code).where(UnitOfMeasureCatalog.id.in_(unit_ids))
    )).all()) if unit_ids else {}
    for a in products:
        a.unit_of_measure_code = codes.get(a.unit_of_measure_id)
    # Fractional units (KG, L): the screens then accept decimal quantities for the base unit or a sale unit.
    fractional_ids = set((await db.execute(
        select(UnitOfMeasureCatalog.id).where(UnitOfMeasureCatalog.is_fractional.is_(True))
    )).scalars().all())
    for a in products:
        a.unit_is_fractional = a.unit_of_measure_id in fractional_ids
    # Their active sale units travel with them too (one query for the whole list): the Caixa and the invoice form offer
    # them at once, and a scanned barcode can be one of them.
    from app.models.product_sale_unit import ProductSaleUnit
    by_product: dict = {}
    if products:
        rows = (await db.execute(
            select(ProductSaleUnit, UnitOfMeasureCatalog.code)
            .join(UnitOfMeasureCatalog, UnitOfMeasureCatalog.id == ProductSaleUnit.unit_of_measure_id)
            .where(ProductSaleUnit.product_id.in_([a.id for a in products]), ProductSaleUnit.is_active.is_(True))
            .order_by(ProductSaleUnit.factor)
        )).all()
        for sale_unit, code in rows:
            by_product.setdefault(sale_unit.product_id, []).append({
                "id": sale_unit.id, "unit_of_measure_code": code, "factor": float(sale_unit.factor),
                "price": float(sale_unit.price), "barcode": sale_unit.barcode,
                "is_fractional": sale_unit.unit_of_measure_id in fractional_ids,
            })
    for a in products:
        a.sale_units = by_product.get(a.id, [])
    return products


async def get_product_or_raise(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.company_id == company_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError("Produto nao encontrado")
    return product


class BaseUnitLockedError(Exception):
    """The base unit of a product that already has a history cannot change."""


async def ensure_base_unit_can_change(db: AsyncSession, product: Product, new_unit_id) -> None:
    """
    The base unit is what every quantity of the product is counted in (stock, ledger, sale-unit factors, average cost).
    Changing it would not convert anything - 75 KG would silently become 75 SC - so it is refused as soon as the
    product has stock movements, invoice lines or sale units. A product without history may still be corrected.
    """
    if new_unit_id == product.unit_of_measure_id:
        return
    from app.models.invoice_line import InvoiceLine
    from app.models.product_sale_unit import ProductSaleUnit
    from app.models.stock_movement import StockMovement
    checks = (
        (StockMovement, StockMovement.product_id, 'movimentos de stock'),
        (InvoiceLine, InvoiceLine.product_id, 'documentos de venda'),
        (ProductSaleUnit, ProductSaleUnit.product_id, 'unidades e embalagens'),
    )
    for model, column, label in checks:
        if (await db.execute(select(model.id).where(column == product.id).limit(1))).first() is not None:
            raise BaseUnitLockedError(
                f"A unidade base de {product.name} nao pode ser alterada: o produto ja tem {label}. "
                "Todas as quantidades estao contadas nesta unidade."
            )


async def update_product(
    db: AsyncSession,
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    code: str,
    name: str,
    barcode: str | None,
    vat_id: uuid.UUID | None,
    price: float,
    min_stock_threshold: float,
    expiry_date: date | None,
    product_type: str = "BEM",
    unit_of_measure_id: uuid.UUID | None = None,
    batch_yield: float = 1,
    is_raw_material: bool = False,
    category_id: uuid.UUID | None = None,
    brand: str | None = None,
    image_path: str | None = None,
    purchase_price: float | None = None,
    managed_by_batch: bool = False,
    managed_by_stock: bool = True,
    managed_by_expiry: bool = False,
    not_available_pos: bool = False,
    internal_use_only: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
) -> Product:
    """Updates a product's editable fields, scoped to the caller's company."""
    product = await get_product_or_raise(db, company_id, product_id)
    await _check_all_fields_available(db, company_id, code, name, barcode, exclude_id=product_id)
    if unit_of_measure_id is None:  # every article has a base unit: the SAF-T and the documents show it
        raise ArticleUnitRequiredError("A unidade base e obrigatoria")
    _check_vat_rule(vat_id, is_raw_material)
    if is_raw_material:
        exemption_reason_id = None  # a raw material is never sold: no exemption to justify
    else:
        exemption_reason_id = await resolve_article_vat(db, company_id, vat_id, exemption_reason_id)

    product.code = code
    product.name = name
    product.barcode = barcode
    product.vat_id = vat_id
    product.price = price
    product.min_stock_threshold = min_stock_threshold
    product.expiry_date = expiry_date
    product.product_type = product_type
    await ensure_base_unit_can_change(db, product, unit_of_measure_id)
    product.unit_of_measure_id = unit_of_measure_id
    product.batch_yield = batch_yield
    product.is_raw_material = is_raw_material
    product.category_id = category_id
    product.brand = brand
    product.image_path = image_path
    product.purchase_price = purchase_price
    product.managed_by_batch = managed_by_batch
    product.managed_by_stock = managed_by_stock
    product.managed_by_expiry = managed_by_expiry
    product.not_available_pos = not_available_pos
    product.internal_use_only = internal_use_only
    product.status = status
    product.exemption_reason_id = exemption_reason_id

    await db.commit()
    await db.refresh(product)
    return product


async def toggle_product_status(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    """Activates or deactivates a product (soft delete equivalent for the catalog)."""
    product = await get_product_or_raise(db, company_id, product_id)
    product.is_active = not product.is_active
    await db.commit()
    await db.refresh(product)
    return product