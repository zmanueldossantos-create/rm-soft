"""
Service layer for InternalConsumption - the generic "Consumo Interno" module
(entry/exit/assignment of operational supplies - towels, soap, cleaning
products - across any sector). See the model docstring for the full
rationale. Deducts stock via stock_service.deduct_stock_for_sale (same
underlying mechanism a real sale uses, just without any invoice/customer
attached), so the same warehouse quantity is always the single source of
truth whether stock left via a sale or via internal use.
"""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.internal_consumption import InternalConsumption
from app.models.product import Product
from app.models.resource import Resource
from app.models.user import User
from app.services.activity_service import get_activity_or_raise
from app.services.consumption_reason_service import get_consumption_reason_or_raise
from app.services.stock_service import deduct_stock_for_sale, InsufficientStockError
from app.services.fiscal_period_service import resolve_posting_period


class NoWarehouseError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


async def record_consumption(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, product_id: uuid.UUID,
    quantity: float, reason_id: uuid.UUID, consumed_by_user_id: uuid.UUID,
    resource_id: uuid.UUID | None = None, notes: str | None = None, fiscal_period_id: uuid.UUID | None = None,
) -> InternalConsumption:
    activity = await get_activity_or_raise(db, company_id, activity_id)
    if activity.warehouse_id is None:
        raise NoWarehouseError("Esta atividade nao tem um armazem associado")

    reason = await get_consumption_reason_or_raise(db, company_id, reason_id)

    product_result = await db.execute(select(Product).where(Product.id == product_id, Product.company_id == company_id))
    product = product_result.scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError("Produto nao encontrado")

    # Internal entry: booked in the chosen period (active or soft-closed), never in a closed one.
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    # Raises InsufficientStockError if there isn't enough - no partial consumption.
    await deduct_stock_for_sale(
        db, company_id, activity.warehouse_id, product_id, quantity,
        reference=f"Consumo interno - {reason.name}", fiscal_period_id=posting_period.id,
    )

    record = InternalConsumption(
        company_id=company_id, fiscal_period_id=posting_period.id, activity_id=activity_id, warehouse_id=activity.warehouse_id,
        product_id=product_id, quantity=quantity, reason_id=reason_id,
        resource_id=resource_id, consumed_by_user_id=consumed_by_user_id, notes=notes,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def list_consumptions(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
) -> list[dict]:
    query = (
        select(InternalConsumption, Product.name.label("product_name"), Product.code.label("product_code"),
               Resource.name.label("resource_name"), User.full_name.label("consumed_by_name"))
        .join(Product, Product.id == InternalConsumption.product_id)
        .outerjoin(Resource, Resource.id == InternalConsumption.resource_id)
        .join(User, User.id == InternalConsumption.consumed_by_user_id)
        .where(InternalConsumption.company_id == company_id)
        .order_by(InternalConsumption.created_at.desc())
    )
    if activity_id is not None:
        query = query.where(InternalConsumption.activity_id == activity_id)
    if date_from is not None:
        query = query.where(InternalConsumption.created_at >= date_from)
    if date_to is not None:
        query = query.where(InternalConsumption.created_at <= date_to)

    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "id": record.id,
            "product_name": product_name,
            "product_code": product_code,
            "quantity": float(record.quantity),
            "resource_name": resource_name,
            "consumed_by_name": consumed_by_name,
            "notes": record.notes,
            "created_at": record.created_at,
        }
        for record, product_name, product_code, resource_name, consumed_by_name in rows
    ]
