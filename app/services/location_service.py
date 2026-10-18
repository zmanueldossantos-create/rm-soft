"""
Emplacements (point 5) - the places of a warehouse and where each product is kept there (see
app/models/warehouse_location.py). Optional: nothing asks for a location; a warehouse without any shows none.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.warehouse import Warehouse
from app.models.warehouse_location import ProductLocation, WarehouseLocation


class LocationError(Exception):
    """A location that cannot be created or changed as asked (the message says why)."""


async def _warehouse(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (await db.execute(select(Warehouse).where(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id))).scalar_one_or_none()
    if warehouse is None:
        raise LocationError("Armazém não encontrado")
    return warehouse


def _clean_code(code: str | None) -> str:
    code = " ".join((code or "").split()).upper()
    if not code:
        raise LocationError("Indique o código da localização")
    if len(code) > 30:
        raise LocationError("O código da localização tem no máximo 30 caracteres")
    return code


async def _ensure_code_free(db: AsyncSession, warehouse_id: uuid.UUID, code: str, exclude_id: uuid.UUID | None = None):
    query = select(WarehouseLocation.id).where(WarehouseLocation.warehouse_id == warehouse_id, WarehouseLocation.code == code)
    if exclude_id is not None:
        query = query.where(WarehouseLocation.id != exclude_id)
    if (await db.execute(query)).first() is not None:
        raise LocationError(f"Já existe a localização {code} neste armazém")


async def list_locations(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> list[dict]:
    """The places of a warehouse, by code, with how many products are kept in each."""
    await _warehouse(db, company_id, warehouse_id)
    used = dict((await db.execute(
        select(ProductLocation.location_id, func.count()).where(ProductLocation.warehouse_id == warehouse_id)
        .group_by(ProductLocation.location_id))).all())
    rows = (await db.execute(select(WarehouseLocation).where(WarehouseLocation.warehouse_id == warehouse_id)
                             .order_by(WarehouseLocation.code))).scalars().all()
    return [{"id": l.id, "warehouse_id": l.warehouse_id, "code": l.code, "description": l.description,
             "is_active": l.is_active, "products": int(used.get(l.id, 0))} for l in rows]


async def create_location(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID, code: str,
                          description: str | None = None) -> WarehouseLocation:
    await _warehouse(db, company_id, warehouse_id)
    code = _clean_code(code)
    await _ensure_code_free(db, warehouse_id, code)
    location = WarehouseLocation(company_id=company_id, warehouse_id=warehouse_id, code=code,
                                 description=(" ".join((description or "").split())[:200] or None))
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


async def _get(db: AsyncSession, company_id: uuid.UUID, location_id: uuid.UUID) -> WarehouseLocation:
    location = (await db.execute(select(WarehouseLocation).where(
        WarehouseLocation.id == location_id, WarehouseLocation.company_id == company_id))).scalar_one_or_none()
    if location is None:
        raise LocationError("Localização não encontrada")
    return location


async def update_location(db: AsyncSession, company_id: uuid.UUID, location_id: uuid.UUID, code: str,
                          description: str | None = None) -> WarehouseLocation:
    location = await _get(db, company_id, location_id)
    code = _clean_code(code)
    await _ensure_code_free(db, location.warehouse_id, code, exclude_id=location.id)
    location.code = code
    location.description = " ".join((description or "").split())[:200] or None
    await db.commit()
    await db.refresh(location)
    return location


async def toggle_location(db: AsyncSession, company_id: uuid.UUID, location_id: uuid.UUID) -> WarehouseLocation:
    """Activates or deactivates a place - never while products are still kept there (move them first)."""
    location = await _get(db, company_id, location_id)
    if location.is_active:
        used = (await db.execute(select(func.count()).select_from(ProductLocation)
                                 .where(ProductLocation.location_id == location.id))).scalar_one()
        if used:
            raise LocationError(f"Localização usada por {used} produto(s) - mude-os de localização primeiro")
    location.is_active = not location.is_active
    await db.commit()
    await db.refresh(location)
    return location


async def set_product_location(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID,
                               location_id: uuid.UUID | None) -> None:
    """Where a product is kept in a warehouse: one of its active places, or none (location_id empty)."""
    await _warehouse(db, company_id, warehouse_id)
    if (await db.execute(select(Product.id).where(Product.id == product_id, Product.company_id == company_id))).first() is None:
        raise LocationError("Produto não encontrado")
    current = (await db.execute(select(ProductLocation).where(
        ProductLocation.product_id == product_id, ProductLocation.warehouse_id == warehouse_id))).scalar_one_or_none()
    if location_id is None:
        if current is not None:
            await db.delete(current)
        await db.commit()
        return
    location = await _get(db, company_id, location_id)
    if location.warehouse_id != warehouse_id:
        raise LocationError("Esta localização é de outro armazém")
    if not location.is_active:
        raise LocationError(f"A localização {location.code} está desativada")
    if current is None:
        db.add(ProductLocation(company_id=company_id, product_id=product_id, warehouse_id=warehouse_id,
                               location_id=location.id))
    else:
        current.location_id = location.id
    await db.commit()


def location_label(code: str, description: str | None) -> str:
    """How a place is shown next to the stock: its code and description (A-01 · Prateleira 1), or the code alone."""
    return f"{code} · {description}" if description else code


async def location_codes(db: AsyncSession, warehouse_ids, product_ids=None) -> dict:
    """{(product_id, warehouse_id): "A-01 · Prateleira 1"} - where each product is kept, to show it next to the stock
    (the code first: sorting on it sorts by code)."""
    warehouse_ids = [w for w in set(warehouse_ids) if w is not None]
    if not warehouse_ids:
        return {}
    query = (select(ProductLocation.product_id, ProductLocation.warehouse_id, WarehouseLocation.code,
                    WarehouseLocation.description)
             .join(WarehouseLocation, WarehouseLocation.id == ProductLocation.location_id)
             .where(ProductLocation.warehouse_id.in_(warehouse_ids)))
    if product_ids is not None:
        query = query.where(ProductLocation.product_id.in_(list(product_ids)))
    return {(p, w): location_label(code, desc) for p, w, code, desc in (await db.execute(query)).all()}
