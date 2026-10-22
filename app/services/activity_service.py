"""
Business logic for Activity (business line / point of sale within a
Company) - GESTOR configures these, but only for Modules the company
has been granted by SUPER_ADMIN (see CompanyModule/company_module_service).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.warehouse import Warehouse
from app.services.company_module_service import is_module_granted


class ActivityNotFoundError(Exception):
    pass


class ModuleNotGrantedError(Exception):
    """Raised when GESTOR tries to configure an Activity for a Module the company was not granted."""
    pass


async def list_activities(db: AsyncSession, company_id: uuid.UUID) -> list[Activity]:
    """Each activity carries the capabilities of its module (capabilities): the screens follow the activity's own
    workflow - a hotel's bookings check in, a spa's marcações are charged."""
    from app.services.sector_service import module_capabilities_map  # lazy: sector_service is a heavier import
    result = await db.execute(select(Activity).where(Activity.company_id == company_id).order_by(Activity.name))
    activities = list(result.scalars().all())
    by_module = await module_capabilities_map(db, {a.module_id for a in activities})
    for activity in activities:
        activity.capabilities = sorted(by_module.get(activity.module_id, set()))
    return activities


async def create_activity(
    db: AsyncSession, company_id: uuid.UUID, module_id: uuid.UUID, name: str,
) -> Activity:
    """Creates an activity of a module the company was granted, with its own point-of-sale warehouse and default
    cash point. Invoice numbering never depends on the activity: it goes through document_series."""
    if not await is_module_granted(db, company_id, module_id):
        raise ModuleNotGrantedError("A empresa não tem acesso a este modulo - contacte o administrador da plataforma")
    from app.services.plan_service import check_limit
    await check_limit(db, company_id, "max_pos")  # every activity comes with its own till

    # Stock is received centrally (Armazem Principal) and internally
    # transferred to this activity's own point-of-sale warehouse before
    # being sold under it - see discussion on multi-activity stock.
    warehouse = Warehouse(company_id=company_id, name=f"{name} - Ponto de Venda")
    db.add(warehouse)
    await db.flush()  # get warehouse.id before creating the Activity

    activity = Activity(
        company_id=company_id,
        module_id=module_id,
        warehouse_id=warehouse.id,
        name=name,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    # Default cash point for this activity - full POS functionality (sales, transfers,
    # user association), never renamable/deactivatable - see point_of_sale_service.
    # Deferred import: point_of_sale_service imports get_activity_or_raise from this
    # module at top level, so importing create_point_of_sale up there would be circular.
    from app.services.point_of_sale_service import create_point_of_sale
    from app.services.point_of_sale_service import DEFAULT_POS_NAME
    await create_point_of_sale(db, company_id, activity.id, DEFAULT_POS_NAME, is_default=True)

    return activity


async def get_activity_or_raise(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID) -> Activity:
    result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.company_id == company_id)
    )
    activity = result.scalar_one_or_none()
    if activity is None:
        raise ActivityNotFoundError("Atividade não encontrada")
    return activity


async def update_activity(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, name: str,
) -> Activity:
    """Renames the activity."""
    activity = await get_activity_or_raise(db, company_id, activity_id)
    activity.name = name
    await db.commit()
    await db.refresh(activity)
    return activity


async def toggle_activity_status(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID) -> Activity:
    activity = await get_activity_or_raise(db, company_id, activity_id)
    activity.is_active = not activity.is_active
    await db.commit()
    await db.refresh(activity)
    return activity
