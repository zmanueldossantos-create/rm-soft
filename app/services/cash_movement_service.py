"""
Business logic for cash treasury movements (transfers between an Activity's
POS, including its default "Caixa Geral" POS, and external entradas/saidas)
and their reason catalog.

ARCHITECTURE NOTE: this used to also support a separate CashOffice entity.
That concept has been retired - see cash_movement.py model docstring.

Validation rules enforced here (not at the DB level):
- TRANSFERENCIA requires exactly a source_pos_id AND a destination_pos_id,
  reason_id must be None.
- ENTRADA_EXTERNA requires a destination_pos_id only (no source), reason_id
  required, and the reason's direction must be ENTRADA.
- SAIDA_EXTERNA requires a source_pos_id only (no destination), reason_id
  required, and the reason's direction must be SAIDA. The source POS must
  currently have an open CashSession - funds cannot leave a closed drawer
  that was never counted (see discussion on the "closed Bar POS with no
  funds" bug this rule fixes).
- amount must be > 0.
- Every POS referenced must belong to company_id - cross-tenant references
  are rejected the same way as everywhere else in the codebase.
"""
import uuid
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_movement import CashMovement, CashMovementType, CashMovementStatus
from app.models.cash_movement_reason import CashMovementReason
from app.models.movement_type import MovementDirection
from app.services.point_of_sale_service import get_pos_or_raise
from app.services.user_cash_point_access_service import require_cash_point_access
from app.services.cash_session_service import get_open_session, get_current_expected_cash_balance


class InvalidCashMovementError(Exception):
    """Raised when the combination of movement_type / source / destination / reason is invalid."""
    pass


class ReasonNotFoundError(Exception):
    pass


class ReasonDirectionMismatchError(Exception):
    """Raised when an ENTRADA_EXTERNA movement is given a SAIDA reason, or vice versa."""
    pass


class InsufficientFundsError(Exception):
    pass


class SourcePosNotOpenError(Exception):
    """Raised when funds are being taken out of a POS with no currently open CashSession."""
    pass


# ---------- Reasons catalog ----------

async def list_cash_movement_reasons(
    db: AsyncSession, company_id: uuid.UUID, direction: MovementDirection | None = None,
) -> list[CashMovementReason]:
    query = select(CashMovementReason).where(CashMovementReason.company_id == company_id)
    if direction is not None:
        query = query.where(CashMovementReason.direction == direction)
    query = query.order_by(CashMovementReason.name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_cash_movement_reason(
    db: AsyncSession, company_id: uuid.UUID, name: str, direction: MovementDirection,
) -> CashMovementReason:
    existing = await db.execute(
        select(CashMovementReason).where(
            CashMovementReason.company_id == company_id,
            CashMovementReason.name == name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise InvalidCashMovementError("Ja existe um motivo com este nome")
    reason = CashMovementReason(company_id=company_id, name=name, direction=direction)
    db.add(reason)
    await db.commit()
    await db.refresh(reason)
    return reason


async def get_reason_or_raise(db: AsyncSession, company_id: uuid.UUID, reason_id: uuid.UUID) -> CashMovementReason:
    result = await db.execute(
        select(CashMovementReason).where(CashMovementReason.id == reason_id, CashMovementReason.company_id == company_id)
    )
    reason = result.scalar_one_or_none()
    if reason is None:
        raise ReasonNotFoundError("Motivo de movimento de caixa nao encontrado")
    return reason


async def update_cash_movement_reason(
    db: AsyncSession, company_id: uuid.UUID, reason_id: uuid.UUID, name: str, direction: MovementDirection,
) -> CashMovementReason:
    reason = await get_reason_or_raise(db, company_id, reason_id)
    reason.name = name
    reason.direction = direction
    await db.commit()
    await db.refresh(reason)
    return reason


async def toggle_reason_status(db: AsyncSession, company_id: uuid.UUID, reason_id: uuid.UUID) -> CashMovementReason:
    reason = await get_reason_or_raise(db, company_id, reason_id)
    reason.is_active = not reason.is_active
    await db.commit()
    await db.refresh(reason)
    return reason


# ---------- Movements ----------

async def create_cash_movement(
    db: AsyncSession,
    company_id: uuid.UUID,
    movement_type: CashMovementType,
    creating_user: "User",
    amount: float,
    source_pos_id: uuid.UUID | None = None,
    destination_pos_id: uuid.UUID | None = None,
    reason_id: uuid.UUID | None = None,
    movement_date: date | None = None,
    description: str | None = None,
) -> CashMovement:
    if amount <= 0:
        raise InvalidCashMovementError("O valor do movimento deve ser maior que zero")

    if movement_type == CashMovementType.TRANSFERENCIA:
        if source_pos_id is None or destination_pos_id is None:
            raise InvalidCashMovementError("Uma transferencia exige uma origem e um destino")
        if reason_id is not None:
            raise InvalidCashMovementError("Uma transferencia entre caixas nao deve ter um motivo associado")
    elif movement_type == CashMovementType.ENTRADA_EXTERNA:
        if source_pos_id is not None or destination_pos_id is None:
            raise InvalidCashMovementError("Uma entrada externa exige apenas um destino, sem origem")
        if reason_id is None:
            raise InvalidCashMovementError("Uma entrada externa exige um motivo")
    elif movement_type == CashMovementType.SAIDA_EXTERNA:
        if destination_pos_id is not None or source_pos_id is None:
            raise InvalidCashMovementError("Uma saida externa exige apenas uma origem, sem destino")
        if reason_id is None:
            raise InvalidCashMovementError("Uma saida externa exige um motivo")

    if source_pos_id is not None:
        await get_pos_or_raise(db, company_id, source_pos_id)
        await require_cash_point_access(db, company_id, creating_user, source_pos_id)
        # Funds can only leave a POS whose drawer is currently open and counted -
        # see discussion on the closed-Bar-POS-with-no-funds bug.
        open_session = await get_open_session(db, company_id, source_pos_id)
        if open_session is None:
            raise SourcePosNotOpenError("Esta caixa nao tem nenhuma sessao aberta - abra a caixa antes de movimentar fundos")
        # Cannot send/take out more physical cash than the POS currently has -
        # see the "sent 50000 with only 5000 available" bug discussion.
        current_balance = await get_current_expected_cash_balance(db, company_id, source_pos_id, open_session)
        if amount > current_balance:
            raise InsufficientFundsError(f"Esta caixa so tem {current_balance:.2f} Kz disponiveis - o valor excede o saldo atual")
    if destination_pos_id is not None:
        await get_pos_or_raise(db, company_id, destination_pos_id)
        if movement_type == CashMovementType.TRANSFERENCIA:
            # A transfer must land on a POS whose drawer is currently open - otherwise the cash is
            # physically sent but never counted (see get_current_expected_cash_balance: 0.0 with no session).
            destination_open_session = await get_open_session(db, company_id, destination_pos_id)
            if destination_open_session is None:
                raise DestinationPosNotOpenError("A caixa de destino nao tem nenhuma sessao aberta - peca para a abrirem antes de transferir")

    if reason_id is not None:
        reason = await get_reason_or_raise(db, company_id, reason_id)
        expected_direction = (
            MovementDirection.ENTRADA if movement_type == CashMovementType.ENTRADA_EXTERNA
            else MovementDirection.SAIDA
        )
        if reason.direction != expected_direction:
            raise ReasonDirectionMismatchError(
                f"O motivo '{reason.name}' e de {reason.direction.value}, incompativel com este tipo de movimento"
            )

    initial_status = CashMovementStatus.PENDENTE if movement_type == CashMovementType.TRANSFERENCIA else CashMovementStatus.RECEBIDO
    movement = CashMovement(
        company_id=company_id,
        movement_type=movement_type,
        source_pos_id=source_pos_id,
        destination_pos_id=destination_pos_id,
        reason_id=reason_id,
        amount=amount,
        movement_date=movement_date or date.today(),
        description=description,
        created_by_user_id=creating_user.id,
        status=initial_status,
        received_at=None if initial_status == CashMovementStatus.PENDENTE else func.now(),
        received_by_user_id=None if initial_status == CashMovementStatus.PENDENTE else creating_user.id,
    )
    db.add(movement)
    await db.commit()
    await db.refresh(movement)
    return movement


class DestinationPosNotOpenError(Exception):
    pass


class MovementNotFoundError(Exception):
    pass


class MovementAlreadyReceivedError(Exception):
    pass


class MovementNotReceivableAtThisPosError(Exception):
    pass


async def receive_cash_movement(
    db: AsyncSession, company_id: uuid.UUID, movement_id: uuid.UUID, receiving_pos_id: uuid.UUID, received_by_user_id: uuid.UUID,
) -> CashMovement:
    """Confirms receipt of a pending TRANSFERENCIA - only the destination POS
    (receiving_pos_id must match movement.destination_pos_id) can confirm, and
    only once. See CashMovement.status docstring for why this two-step flow
    exists."""
    result = await db.execute(
        select(CashMovement).where(CashMovement.id == movement_id, CashMovement.company_id == company_id)
    )
    movement = result.scalar_one_or_none()
    if movement is None:
        raise MovementNotFoundError("Movimento nao encontrado")
    if movement.status == CashMovementStatus.RECEBIDO:
        raise MovementAlreadyReceivedError("Este movimento ja foi recebido")
    if movement.destination_pos_id != receiving_pos_id:
        raise MovementNotReceivableAtThisPosError("Este movimento nao se destina a esta caixa")

    movement.status = CashMovementStatus.RECEBIDO
    movement.received_at = func.now()
    movement.received_by_user_id = received_by_user_id
    await db.commit()
    await db.refresh(movement)
    return movement


async def list_pending_receptions(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> list[CashMovement]:
    """Pending TRANSFERENCIA movements awaiting confirmation at this specific POS."""
    result = await db.execute(
        select(CashMovement).where(
            CashMovement.company_id == company_id,
            CashMovement.destination_pos_id == pos_id,
            CashMovement.status == CashMovementStatus.PENDENTE,
        ).order_by(CashMovement.created_at)
    )
    return list(result.scalars().all())


async def list_pending_emissions(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> list[CashMovement]:
    """Pending TRANSFERENCIA movements sent FROM this POS, not yet received on the
    other side - shown to the source POS so it can cancel if needed (see cancel_cash_movement)."""
    result = await db.execute(
        select(CashMovement).where(
            CashMovement.company_id == company_id,
            CashMovement.source_pos_id == pos_id,
            CashMovement.status == CashMovementStatus.PENDENTE,
        ).order_by(CashMovement.created_at)
    )
    return list(result.scalars().all())


async def cancel_cash_movement(
    db: AsyncSession, company_id: uuid.UUID, movement_id: uuid.UUID, cancelling_pos_id: uuid.UUID,
) -> None:
    """Cancels (deletes) a pending TRANSFERENCIA before it has been received - only
    the SOURCE POS can cancel, and only while still PENDENTE (the funds never actually
    left the company, they were just held in transit - deleting the row restores the
    source POS's expected balance immediately since get_current_expected_cash_balance
    simply stops counting it)."""
    result = await db.execute(
        select(CashMovement).where(CashMovement.id == movement_id, CashMovement.company_id == company_id)
    )
    movement = result.scalar_one_or_none()
    if movement is None:
        raise MovementNotFoundError("Movimento nao encontrado")
    if movement.status == CashMovementStatus.RECEBIDO:
        raise MovementAlreadyReceivedError("Este movimento ja foi recebido e nao pode ser cancelado")
    if movement.source_pos_id != cancelling_pos_id:
        raise MovementNotReceivableAtThisPosError("Apenas a caixa de origem pode cancelar esta transferencia")

    await db.delete(movement)
    await db.commit()


async def list_cash_movements(
    db: AsyncSession, company_id: uuid.UUID,
    pos_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[CashMovement]:
    """Lists movements touching a given POS on EITHER side (source or
    destination), or all company movements if no pos_id filter is given."""
    query = select(CashMovement).where(CashMovement.company_id == company_id)
    if pos_id is not None:
        query = query.where(
            (CashMovement.source_pos_id == pos_id) | (CashMovement.destination_pos_id == pos_id)
        )
    query = query.order_by(CashMovement.movement_date.desc(), CashMovement.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
