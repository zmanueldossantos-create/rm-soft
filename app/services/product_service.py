"""
Business logic for product management.
Every query is scoped to the caller's company_id (multi-tenant isolation, section 2.5 v7) -
a GESTOR/ADMIN only ever sees and manages their own company's products.
Extended (Video 3) with category, brand, image, purchase price, the
managed-by-lote/stock/validade toggles, and richer status.
"""
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


async def _check_exemption_reason(db: AsyncSession, vat_id: uuid.UUID | None, exemption_reason_id: uuid.UUID | None) -> None:
    """AGT/SAF-T requires a justification code for every exempt (0%) line - see VatCode/Configuracoes."""
    if vat_id is None:
        return
    result = await db.execute(select(VAT).where(VAT.id == vat_id))
    vat = result.scalar_one_or_none()
    if vat is not None and float(vat.rate) == 0 and exemption_reason_id is None:
        raise ExemptionReasonRequiredError("Motivo de isencao obrigatorio quando o IVA e 0% (isento)")


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
    is_sold_by_weight: bool,
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
    subject_to_return: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
) -> Product:
    """Creates a product within the caller's company."""
    await _check_all_fields_available(db, company_id, code, name, barcode)
    _check_vat_rule(vat_id, is_raw_material)
    if is_raw_material:
        exemption_reason_id = None  # a raw material is never sold: no exemption to justify
    else:
        await _check_exemption_reason(db, vat_id, exemption_reason_id)

    product = Product(
        company_id=company_id,
        code=code,
        name=name,
        barcode=barcode,
        vat_id=vat_id,
        price=price,
        min_stock_threshold=min_stock_threshold,
        expiry_date=expiry_date,
        is_sold_by_weight=is_sold_by_weight,
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
        subject_to_return=subject_to_return,
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
    return list(result.scalars().all())


async def get_product_or_raise(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.company_id == company_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError("Produto nao encontrado")
    return product


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
    is_sold_by_weight: bool,
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
    subject_to_return: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
) -> Product:
    """Updates a product's editable fields, scoped to the caller's company."""
    product = await get_product_or_raise(db, company_id, product_id)
    await _check_all_fields_available(db, company_id, code, name, barcode, exclude_id=product_id)
    _check_vat_rule(vat_id, is_raw_material)
    if is_raw_material:
        exemption_reason_id = None  # a raw material is never sold: no exemption to justify
    else:
        await _check_exemption_reason(db, vat_id, exemption_reason_id)

    product.code = code
    product.name = name
    product.barcode = barcode
    product.vat_id = vat_id
    product.price = price
    product.min_stock_threshold = min_stock_threshold
    product.expiry_date = expiry_date
    product.is_sold_by_weight = is_sold_by_weight
    product.product_type = product_type
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
    product.subject_to_return = subject_to_return
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