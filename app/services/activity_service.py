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


class ActivityAlreadyExistsError(Exception):
    """Raised when the series_code already exists for this company."""
    pass


class ActivityNotFoundError(Exception):
    pass


class ModuleNotGrantedError(Exception):
    """Raised when GESTOR tries to configure an Activity for a Module the company was not granted."""
    pass


async def _generate_unique_legacy_series_code(db: AsyncSession, company_id: uuid.UUID, name: str) -> str:
    base = "".join(ch for ch in name.upper() if ch.isalnum())[:3] or "ACT"
    candidate = base
    suffix = 1
    while True:
        try:
            await _check_series_code_available(db, company_id, candidate)
            return candidate
        except SeriesCodeTakenError:
            suffix += 1
            candidate = f"{base}{suffix}"


async def _check_series_code_available(
    db: AsyncSession, company_id: uuid.UUID, series_code: str, exclude_id: uuid.UUID | None = None
) -> None:
    query = select(Activity).where(Activity.company_id == company_id, Activity.series_code == series_code)
    if exclude_id is not None:
        query = query.where(Activity.id != exclude_id)
    result = await db.execute(query)
    if result.scalar_one_or_none() is not None:
        raise ActivityAlreadyExistsError("Ja existe uma atividade com este codigo de serie")


async def list_activities(db: AsyncSession, company_id: uuid.UUID) -> list[Activity]:
    result = await db.execute(select(Activity).where(Activity.company_id == company_id).order_by(Activity.name))
    return list(result.scalars().all())


async def create_activity(
    db: AsyncSession, company_id: uuid.UUID, module_id: uuid.UUID, name: str,
) -> Activity:
    """series_code/number_digits are legacy columns kept only for backward DB
    compatibility - they have NO effect on real invoice numbering (see
    document_series_service.get_or_create_current_series, which is company+doctype+
    year(+establishment) scoped, never per-activity). Auto-derived here so the caller
    (and the Atividades screen) no longer needs to think about them at all."""
    if not await is_module_granted(db, company_id, module_id):
        raise ModuleNotGrantedError("A empresa nao tem acesso a este modulo - contacte o administrador da plataforma")

    series_code = await _generate_unique_legacy_series_code(db, company_id, name)
    number_digits = 3

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
        series_code=series_code,
        number_digits=number_digits,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    # Default cash point for this activity - full POS functionality (sales, transfers,
    # user association), never renamable/deactivatable - see point_of_sale_service.
    # Deferred import: point_of_sale_service imports get_activity_or_raise from this
    # module at top level, so importing create_point_of_sale up there would be circular.
    from app.services.point_of_sale_service import create_point_of_sale
    await create_point_of_sale(db, company_id, activity.id, f"{name} - Caixa Geral", is_default=True)

    return activity


async def get_activity_or_raise(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID) -> Activity:
    result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.company_id == company_id)
    )
    activity = result.scalar_one_or_none()
    if activity is None:
        raise ActivityNotFoundError("Atividade nao encontrada")
    return activity


async def update_activity(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, name: str,
) -> Activity:
    """series_code/number_digits are legacy, unused for real invoice numbering - see
    create_activity docstring. Only the name is actually editable here now."""
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
