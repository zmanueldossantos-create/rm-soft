"""
Business logic for PointOfSale (POS) - CRUD scoped to the caller's company,
nested under an Activity. See model docstring: several POS can share the
same Activity's stock/warehouse, only the cash register is per-POS.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.point_of_sale import PointOfSale
from app.services.activity_service import get_activity_or_raise


# Every activity gets one default cash point, always named like this (the activity is shown next to it where needed).
DEFAULT_POS_NAME = "Caixa Geral"


class PosAlreadyExistsError(Exception):
    """Raised when a POS name already exists within the same Activity."""
    pass


class PosNotFoundError(Exception):
    pass


class DefaultPosNotModifiableError(Exception):
    """Raised when trying to rename or deactivate an Activity's default POS -
    same protection principle as the central Warehouse (see create_activity)."""
    pass


async def _check_name_available(
    db: AsyncSession, activity_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None,
) -> None:
    query = select(PointOfSale).where(PointOfSale.activity_id == activity_id, PointOfSale.name == name)
    if exclude_id is not None:
        query = query.where(PointOfSale.id != exclude_id)
    if (await db.execute(query)).scalar_one_or_none() is not None:
        raise PosAlreadyExistsError("Ja existe um ponto de venda com este nome nesta atividade")


async def list_points_of_sale(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None = None) -> list[PointOfSale]:
    query = select(PointOfSale).where(PointOfSale.company_id == company_id)
    if activity_id is not None:
        query = query.where(PointOfSale.activity_id == activity_id)
    query = query.order_by(PointOfSale.name)
    result = await db.execute(query)
    return list(result.scalars().all())


class PosPrintError(Exception):
    """Printing after a sale switched on without any format."""


def _check_printing(print_after_sale: bool, print_ticket: bool, print_a4: bool) -> None:
    if print_after_sale and not (print_ticket or print_a4):
        raise PosPrintError("Escolha pelo menos um formato de impressao: Talao ou A4")


async def create_point_of_sale(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, name: str, is_default: bool = False,
    billetage_enabled: bool = False,
    print_after_sale: bool = False, print_ticket: bool = True, print_a4: bool = False,
) -> PointOfSale:
    """Creates a POS under an Activity - the Activity must belong to the caller's company.
    is_default=True is only ever set internally by activity_service.create_activity, never
    via the public create route - a GESTOR cannot mark an arbitrary POS as default afterward."""
    _check_printing(print_after_sale, print_ticket, print_a4)
    await get_activity_or_raise(db, company_id, activity_id)
    await _check_name_available(db, activity_id, name)

    pos = PointOfSale(company_id=company_id, activity_id=activity_id, name=name, is_default=is_default, billetage_enabled=billetage_enabled,
                      print_after_sale=print_after_sale, print_ticket=print_ticket, print_a4=print_a4)
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    return pos


async def get_pos_or_raise(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> PointOfSale:
    result = await db.execute(select(PointOfSale).where(PointOfSale.id == pos_id, PointOfSale.company_id == company_id))
    pos = result.scalar_one_or_none()
    if pos is None:
        raise PosNotFoundError("Ponto de venda nao encontrado")
    return pos


async def update_point_of_sale(
    db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID, name: str, billetage_enabled: bool = False,
    print_after_sale: bool = False, print_ticket: bool = True, print_a4: bool = False,
) -> PointOfSale:
    pos = await get_pos_or_raise(db, company_id, pos_id)
    # Renaming the Activity's default POS is blocked (see error below), but
    # billetage_enabled is a normal operational toggle - even the default POS
    # can turn it on/off, so it's NOT gated by the same is_default check.
    if pos.is_default and name != pos.name:
        raise DefaultPosNotModifiableError("A caixa por defeito da atividade nao pode ser renomeada")
    if name != pos.name:
        await _check_name_available(db, pos.activity_id, name, exclude_id=pos_id)
    pos.name = name
    pos.billetage_enabled = billetage_enabled
    _check_printing(print_after_sale, print_ticket, print_a4)
    pos.print_after_sale, pos.print_ticket, pos.print_a4 = print_after_sale, print_ticket, print_a4
    await db.commit()
    await db.refresh(pos)
    return pos


class PosStateError(Exception):
    """A point of sale used against its state: inactive for a new session, or deactivated with a session still open."""


async def toggle_pos_status(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> PointOfSale:
    pos = await get_pos_or_raise(db, company_id, pos_id)
    if pos.is_default:
        raise DefaultPosNotModifiableError("A caixa por defeito da atividade nao pode ser desativada")
    if pos.is_active:
        # An inactive point of sale cannot open a session: deactivating one with an open session would leave the drawer
        # uncounted - close it first.
        from app.models.cash_session import CashSession, CashSessionStatus
        open_session = (await db.execute(
            select(CashSession.id).where(CashSession.pos_id == pos.id, CashSession.status == CashSessionStatus.ABERTA)
        )).first()
        if open_session is not None:
            raise PosStateError("Feche a sessao de caixa antes de desativar o ponto de venda")
    pos.is_active = not pos.is_active
    await db.commit()
    await db.refresh(pos)
    return pos
