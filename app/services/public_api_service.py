"""
The public API's reads and writes (app.api.public_v1): what another program of the company sees of the catalogue
and of the customers. Always scoped to the key's company; only what can be sold is shown (an internal-use article,
one waiting for its price, an inactive or blocked one, a category closed to sales: never).

Prices: «price» is the price before VAT (as stored), «price_with_vat» the price the customer pays; the VAT comes
from the article's rate (0 / 5 / 14 %).
"""
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import FINAL_CONSUMER_NIF, Customer
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.product_sale_unit import ProductSaleUnit
from app.models.service import ProductServiceStatus, Service
from app.models.service_type import ServiceType
from app.models.stock import Stock
from app.models.warehouse import Warehouse
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.vat import VAT

MAX_PAGE_SIZE = 200
# shown to the other programs: ESGOTADO stays visible (with its status), the rest is not on sale
SELLABLE = (ProductServiceStatus.ACTIVO, ProductServiceStatus.ESGOTADO)


class PublicApiError(Exception):
    """Refused - the message is shown as it is (422)."""


class AlreadyExistsError(Exception):
    """A customer with this NIF already exists - its id comes with the message (409)."""

    def __init__(self, message: str, existing_id: uuid.UUID):
        super().__init__(message)
        self.existing_id = existing_id


def _money(value) -> float | None:
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _with_vat(price, rate) -> float | None:
    if price is None:
        return None
    return _money(Decimal(str(price)) * (1 + Decimal(str(rate or 0)) / 100))


def _page(page: int, page_size: int) -> tuple[int, int]:
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 50), 1), MAX_PAGE_SIZE)
    return page, page_size


def _search(column_list, text: str | None):
    if not text or not text.strip():
        return None
    like = f"%{text.strip()}%"
    return or_(*[c.ilike(like) for c in column_list])


# --------------------------------------------------------------------------------------------------------- products

def _sellable_products(company_id: uuid.UUID):
    return (select(Product, VAT.rate, VAT.tax_category, ProductCategory.name, UnitOfMeasureCatalog.code)
            .outerjoin(VAT, VAT.id == Product.vat_id)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(UnitOfMeasureCatalog, UnitOfMeasureCatalog.id == Product.unit_of_measure_id)
            .where(Product.company_id == company_id, Product.is_active.is_(True), Product.status.in_(SELLABLE),
                   Product.internal_use_only.is_(False), Product.awaiting_price.is_(False),
                   or_(ProductCategory.id.is_(None), ProductCategory.not_available_sales.is_(False))))


async def _stock_by_product(db: AsyncSession, company_id: uuid.UUID, product_ids: list[uuid.UUID]) -> dict:
    """{product_id: [(warehouse_id, warehouse name, quantity)]} - the active warehouses only."""
    if not product_ids:
        return {}
    rows = (await db.execute(
        select(Stock.product_id, Warehouse.id, Warehouse.name, Stock.quantity)
        .join(Warehouse, Warehouse.id == Stock.warehouse_id)
        .where(Stock.company_id == company_id, Stock.product_id.in_(product_ids), Warehouse.is_active.is_(True))
        .order_by(Warehouse.is_default.desc(), Warehouse.name))).all()
    out: dict = {}
    for product_id, warehouse_id, name, quantity in rows:
        out.setdefault(product_id, []).append((warehouse_id, name, float(quantity or 0)))
    return out


async def _sale_units(db: AsyncSession, company_id: uuid.UUID, product_ids: list[uuid.UUID]) -> dict:
    if not product_ids:
        return {}
    rows = (await db.execute(
        select(ProductSaleUnit, UnitOfMeasureCatalog.code)
        .join(UnitOfMeasureCatalog, UnitOfMeasureCatalog.id == ProductSaleUnit.unit_of_measure_id)
        .where(ProductSaleUnit.company_id == company_id, ProductSaleUnit.product_id.in_(product_ids),
               ProductSaleUnit.is_active.is_(True))
        .order_by(ProductSaleUnit.factor))).all()
    out: dict = {}
    for unit, code in rows:
        out.setdefault(unit.product_id, []).append(unit_view(unit, code))
    return out


def unit_view(unit: ProductSaleUnit, code: str) -> dict:
    return {"id": str(unit.id), "unit": code, "factor": float(unit.factor), "price": _money(unit.price),
            "barcode": unit.barcode}


def _product_view(row, stock: list, units: list, detail: bool) -> dict:
    product, rate, tax_category, category, unit = row
    rate = float(rate or 0)
    view = {
        "id": str(product.id), "code": product.code, "name": product.name, "brand": product.brand,
        "barcode": product.barcode, "category": category, "unit": unit,
        "price": _money(product.price), "vat_rate": rate, "vat_category": tax_category,
        "price_with_vat": _with_vat(product.price, rate),
        "status": product.status.value,
        # null: an article without stock control (always available)
        "stock": round(sum(q for _, _, q in stock), 3) if product.managed_by_stock else None,
        "sale_units": units, "image": product.image_path, "updated_at": product.updated_at,
    }
    if detail and product.managed_by_stock:
        view["stock_by_warehouse"] = [{"warehouse_id": str(w), "warehouse": n, "quantity": q} for w, n, q in stock]
    return view


async def list_products(db: AsyncSession, company_id: uuid.UUID, search: str | None = None,
                        category: str | None = None, barcode: str | None = None,
                        updated_since: datetime | None = None, page: int = 1, page_size: int = 50) -> dict:
    page, page_size = _page(page, page_size)
    query = _sellable_products(company_id)
    condition = _search([Product.name, Product.code, Product.brand], search)
    if condition is not None:
        query = query.where(condition)
    if category:
        query = query.where(ProductCategory.name.ilike(category.strip()))
    if barcode:
        units = select(ProductSaleUnit.product_id).where(ProductSaleUnit.company_id == company_id,
                                                         ProductSaleUnit.barcode == barcode.strip())
        query = query.where(or_(Product.barcode == barcode.strip(), Product.id.in_(units)))
    if updated_since:
        query = query.where(Product.updated_at >= updated_since)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Product.name, Product.id)
                             .offset((page - 1) * page_size).limit(page_size))).all()
    ids = [r[0].id for r in rows]
    stock, units = await _stock_by_product(db, company_id, ids), await _sale_units(db, company_id, ids)
    return {"items": [_product_view(r, stock.get(r[0].id, []), units.get(r[0].id, []), False) for r in rows],
            "page": page, "page_size": page_size, "total": total}


async def get_product(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> dict:
    row = (await db.execute(_sellable_products(company_id).where(Product.id == product_id))).first()
    if row is None:
        raise LookupError("Produto não encontrado")
    stock, units = await _stock_by_product(db, company_id, [product_id]), await _sale_units(db, company_id, [product_id])
    return _product_view(row, stock.get(product_id, []), units.get(product_id, []), True)


async def list_categories(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(select(ProductCategory).where(
        ProductCategory.company_id == company_id, ProductCategory.is_active.is_(True),
        ProductCategory.not_available_sales.is_(False)).order_by(ProductCategory.name))).scalars().all()
    return [{"id": str(c.id), "name": c.name} for c in rows]


# --------------------------------------------------------------------------------------------------------- services

def _sellable_services(company_id: uuid.UUID):
    return (select(Service, VAT.rate, VAT.tax_category, ServiceType.name, UnitOfMeasureCatalog.code)
            .outerjoin(VAT, VAT.id == Service.vat_id)
            .outerjoin(ServiceType, ServiceType.id == Service.service_type_id)
            .outerjoin(UnitOfMeasureCatalog, UnitOfMeasureCatalog.id == Service.unit_of_measure_id)
            .where(Service.company_id == company_id, Service.is_active.is_(True), Service.status.in_(SELLABLE),
                   Service.price.is_not(None),
                   or_(ServiceType.id.is_(None), ServiceType.not_available_sales.is_(False))))


def _service_view(row) -> dict:
    service, rate, tax_category, service_type, unit = row
    rate = float(rate or 0)
    return {"id": str(service.id), "code": service.code, "name": service.name, "description": service.description,
            "type": service_type, "unit": unit, "duration_minutes": service.duration_minutes,
            "price": _money(service.price), "vat_rate": rate, "vat_category": tax_category,
            "price_with_vat": _with_vat(service.price, rate), "status": service.status.value,
            "updated_at": service.updated_at}


async def list_services(db: AsyncSession, company_id: uuid.UUID, search: str | None = None,
                        updated_since: datetime | None = None, page: int = 1, page_size: int = 50) -> dict:
    page, page_size = _page(page, page_size)
    query = _sellable_services(company_id)
    condition = _search([Service.name, Service.code], search)
    if condition is not None:
        query = query.where(condition)
    if updated_since:
        query = query.where(Service.updated_at >= updated_since)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Service.name, Service.id)
                             .offset((page - 1) * page_size).limit(page_size))).all()
    return {"items": [_service_view(r) for r in rows], "page": page, "page_size": page_size, "total": total}


async def get_service(db: AsyncSession, company_id: uuid.UUID, service_id: uuid.UUID) -> dict:
    row = (await db.execute(_sellable_services(company_id).where(Service.id == service_id))).first()
    if row is None:
        raise LookupError("Serviço não encontrado")
    return _service_view(row)


# -------------------------------------------------------------------------------------------------------- customers

def customer_view(c: Customer) -> dict:
    return {"id": str(c.id), "code": c.customer_code, "name": c.name, "nif": c.nif,
            "person_type": c.legal_person_type.value if hasattr(c.legal_person_type, "value") else c.legal_person_type,
            "email": c.email, "phone": c.phone_number, "address": c.address, "city": c.city,
            "status": c.status.value, "created_at": c.created_at, "updated_at": c.updated_at}


async def list_customers(db: AsyncSession, company_id: uuid.UUID, search: str | None = None, nif: str | None = None,
                         email: str | None = None, phone: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    """The «Consumidor final» generic customer is never listed: it is not a real customer."""
    page, page_size = _page(page, page_size)
    query = select(Customer).where(Customer.company_id == company_id, Customer.is_active.is_(True),
                                   Customer.nif != FINAL_CONSUMER_NIF)
    condition = _search([Customer.name, Customer.customer_code, Customer.email], search)
    if condition is not None:
        query = query.where(condition)
    if nif:
        query = query.where(Customer.nif == nif.strip().upper())
    if email:
        query = query.where(func.lower(Customer.email) == email.strip().lower())
    if phone:
        query = query.where(Customer.phone_number == phone.strip())
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Customer.name, Customer.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [customer_view(c) for c in rows], "page": page, "page_size": page_size, "total": total}


async def get_customer(db: AsyncSession, company_id: uuid.UUID, customer_id: uuid.UUID) -> dict:
    customer = (await db.execute(select(Customer).where(
        Customer.id == customer_id, Customer.company_id == company_id, Customer.nif != FINAL_CONSUMER_NIF))).scalar_one_or_none()
    if customer is None:
        raise LookupError("Cliente não encontrado")
    return customer_view(customer)


async def create_customer(db: AsyncSession, company_id: uuid.UUID, data: dict, key_name: str) -> dict:
    """data: validated by the route (name, nif, phone, email...). A NIF already known: AlreadyExistsError with the
    existing customer's id - the program then uses that one (no duplicate)."""
    from app.services import customer_service

    if data["nif"] == FINAL_CONSUMER_NIF:
        raise PublicApiError("O NIF genérico do consumidor final não cria um cliente - use o NIF do cliente")
    existing = (await db.execute(select(Customer).where(Customer.company_id == company_id,
                                                        Customer.nif == data["nif"]))).scalar_one_or_none()
    if existing is not None:
        raise AlreadyExistsError("Já existe um cliente com este NIF", existing.id)
    customer = await customer_service.create_customer(
        db, company_id, name=data["name"], nif=data["nif"], email=data.get("email"),
        phone_number=data.get("phone"), address=data.get("address"),
        customer_code=await customer_service.suggest_next_customer_code(db, company_id),
        legal_person_type=data.get("person_type") or "FISICA", city=data.get("city"),
        description=f"Criado pela API (chave «{key_name}»)")
    return customer_view(customer)
