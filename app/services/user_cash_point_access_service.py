"""
Business logic for UserCashPointAccess - assigns/unassigns a User to exactly
one PointOfSale at a time. See model docstring: a user with no assignment
here cannot perform ANY cash operation, GESTOR bypasses this check entirely
(see require_cash_point_access).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_cash_point_access import UserCashPointAccess
from app.models.user import User
from app.services.point_of_sale_service import get_pos_or_raise


class UserNotFoundError(Exception):
    pass


class AccessNotFoundError(Exception):
    pass


class PosAlreadyAssignedError(Exception):
    """Raised when trying to assign a POS that already belongs to a different user -
    the caller must unassign that user first (see model note on pos_id uniqueness)."""
    pass


async def get_access_for_user(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> UserCashPointAccess | None:
    result = await db.execute(
        select(UserCashPointAccess).where(UserCashPointAccess.company_id == company_id, UserCashPointAccess.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_cash_point_access(db: AsyncSession, company_id: uuid.UUID) -> list[UserCashPointAccess]:
    result = await db.execute(select(UserCashPointAccess).where(UserCashPointAccess.company_id == company_id))
    return list(result.scalars().all())


async def get_access_for_pos(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> UserCashPointAccess | None:
    result = await db.execute(
        select(UserCashPointAccess).where(UserCashPointAccess.company_id == company_id, UserCashPointAccess.pos_id == pos_id)
    )
    return result.scalar_one_or_none()


async def assign_user_to_cash_point(
    db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, pos_id: uuid.UUID,
) -> UserCashPointAccess:
    """Assigns a user to exactly one POS - reassigns (updates in place) if
    the user already had a different one, since only one is allowed at a time.
    The POS itself must also be free (or already assigned to this same user) -
    a POS already held by a different user must be unassigned first."""
    user_result = await db.execute(select(User).where(User.id == user_id, User.company_id == company_id))
    if user_result.scalar_one_or_none() is None:
        raise UserNotFoundError("Utilizador nao encontrado")

    await get_pos_or_raise(db, company_id, pos_id)

    pos_holder = await get_access_for_pos(db, company_id, pos_id)
    if pos_holder is not None and pos_holder.user_id != user_id:
        raise PosAlreadyAssignedError(
            "Esta caixa ja esta associada a outro utilizador - desassocie-o primeiro"
        )

    existing = await get_access_for_user(db, company_id, user_id)
    if existing is not None:
        existing.pos_id = pos_id
        await db.commit()
        await db.refresh(existing)
        return existing

    access = UserCashPointAccess(company_id=company_id, user_id=user_id, pos_id=pos_id)
    db.add(access)
    await db.commit()
    await db.refresh(access)
    return access


async def unassign_user(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> None:
    access = await get_access_for_user(db, company_id, user_id)
    if access is None:
        raise AccessNotFoundError("Este utilizador nao tem nenhuma caixa associada")
    await db.delete(access)
    await db.commit()


class CashPointAccessDeniedError(Exception):
    """Raised when a non-GESTOR user tries a cash operation on a POS they are not assigned to."""
    pass


async def require_cash_point_access(
    db: AsyncSession, company_id: uuid.UUID, user: User, pos_id: uuid.UUID,
) -> None:
    """
    Enforces the association rule for cash operations (open session, sell,
    transfer, external entrada/saida): GESTOR always passes. Any other role
    must have an UserCashPointAccess row matching this exact POS.
    """
    if user.role.value == "GESTOR":
        return

    access = await get_access_for_user(db, company_id, user.id)
    if access is None:
        raise CashPointAccessDeniedError("Nao tem nenhuma caixa associada - contacte o gestor")

    if access.pos_id != pos_id:
        raise CashPointAccessDeniedError("Nao tem acesso a este ponto de venda")


async def require_cash_point_read_access(
    db: AsyncSession, company_id: uuid.UUID, user: User, pos_id: uuid.UUID,
) -> None:
    """
    Enforces the association rule for READING a till (its sessions, journal and reports): a CAIXA reads only the
    till he is assigned to - same check and message as the cash operations (require_cash_point_access). Every other
    role reads every till, as in Faturas: a manager or an accountant checks them all.
    """
    if getattr(user.role, "value", user.role) != "CAIXA":
        return
    await require_cash_point_access(db, company_id, user, pos_id)
