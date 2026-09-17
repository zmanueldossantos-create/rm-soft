"""
Business logic for CashSession (Caixa open/close) - see model docstring.
The session's business_date becomes the invoice date for every sale made
under it (see invoice_service.create_invoice), replacing the interim
date.today() used before the POS module existed.
"""
import uuid
from datetime import date

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_session import CashSession, CashSessionStatus
from app.models.payment import Payment
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.invoice import Invoice
from app.models.cash_movement import CashMovement, CashMovementStatus
from app.services.point_of_sale_service import get_pos_or_raise
from app.services.user_cash_point_access_service import require_cash_point_access, CashPointAccessDeniedError
from app.models.cash_denomination_count import DenominationCountType


class SessionAlreadyOpenError(Exception):
    """Raised when trying to open a session for an activity that already has one open."""
    pass


class SessionNotFoundError(Exception):
    pass


class SessionAlreadyClosedError(Exception):
    pass


async def get_open_session(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> CashSession | None:
    """Looks up the currently open session for a specific POS - "one open session at
    a time" is enforced per POS, not per Activity, so sibling POS under the same
    Activity can each run their own cash register independently."""
    result = await db.execute(
        select(CashSession).where(
            CashSession.company_id == company_id,
            CashSession.pos_id == pos_id,
            CashSession.status == CashSessionStatus.ABERTA,
        )
    )
    return result.scalar_one_or_none()


async def get_carry_forward_amount(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> float:
    """
    The amount that will automatically become the opening float for this POS's next
    session - this POS's last closed session's closing_amount_counted, or 0 if it has
    never had one. Exposed separately so the "Abrir caixa" confirmation screen can show
    the carried-over amount before the cashier commits (see open_session docstring).
    """
    last_closed_result = await db.execute(
        select(CashSession)
        .where(CashSession.company_id == company_id, CashSession.pos_id == pos_id, CashSession.status == CashSessionStatus.FECHADA)
        .order_by(CashSession.closed_at.desc())
        .limit(1)
    )
    last_closed = last_closed_result.scalar_one_or_none()
    return float(last_closed.closing_amount_counted) if last_closed is not None else 0.0


async def open_session(
    db: AsyncSession,
    company_id: uuid.UUID,
    pos_id: uuid.UUID,
    opened_by_user: "User",
    opening_amount: float | None = None,
) -> CashSession:
    """activity_id is derived from the POS (and denormalized onto the session -
    see CashSession model docstring), never supplied directly by the caller.
    Requires the caller to be associated with this exact POS (GESTOR bypasses
    this check) - see user_cash_point_access_service.require_cash_point_access.

    opening_amount is now optional - if not given, the float automatically carries
    over from this POS's last closed session (closing_amount_counted), so the
    cashier no longer has to manually re-enter the drawer's cash each morning. If
    this POS has never had a session before, it starts at 0. Passing an explicit
    value still overrides the carry-over, for the rare case of a manual correction."""
    await require_cash_point_access(db, company_id, opened_by_user, pos_id)
    pos = await get_pos_or_raise(db, company_id, pos_id)
    opened_by_user_id = opened_by_user.id

    existing = await get_open_session(db, company_id, pos_id)
    if existing is not None:
        raise SessionAlreadyOpenError("Ja existe uma sessao de caixa aberta para este ponto de venda")

    if opening_amount is None:
        opening_amount = await get_carry_forward_amount(db, company_id, pos_id)

    session = CashSession(
        company_id=company_id,
        activity_id=pos.activity_id,
        pos_id=pos_id,
        business_date=date.today(),
        opened_by_user_id=opened_by_user_id,
        opening_amount=opening_amount,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session_or_raise(db: AsyncSession, company_id: uuid.UUID, session_id: uuid.UUID) -> CashSession:
    result = await db.execute(select(CashSession).where(CashSession.id == session_id, CashSession.company_id == company_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionNotFoundError("Sessao de caixa nao encontrada")
    return session


async def get_current_expected_cash_balance(
    db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID, session: CashSession | None = None,
) -> float:
    """
    The physical cash a POS should currently have, live (not just at close time) -
    used both by close_session and by cash_movement_service to reject a transfer
    that would overdraw the source POS. Same formula as close_session's comment
    below described: opening float + cash (is_cash) sales since open + received
    transfers in - all transfers/exits out (regardless of reception status, since
    the cash physically leaves the drawer immediately - see CashMovement.status
    docstring).
    """
    if session is None:
        session = await get_open_session(db, company_id, pos_id)
        if session is None:
            return 0.0

    cash_total_result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .where(Invoice.cash_session_id == session.id, PaymentMethodCatalog.is_cash == True)
    )
    cash_sales_total = float(cash_total_result.scalar_one())

    movements_result = await db.execute(
        select(CashMovement).where(
            CashMovement.company_id == company_id,
            or_(CashMovement.source_pos_id == pos_id, CashMovement.destination_pos_id == pos_id),
            CashMovement.created_at >= session.opened_at,
        )
    )
    movements_total = 0.0
    for movement in movements_result.scalars().all():
        if movement.destination_pos_id == pos_id and movement.status == CashMovementStatus.RECEBIDO:
            movements_total += float(movement.amount)
        if movement.source_pos_id == pos_id:
            movements_total -= float(movement.amount)

    return float(session.opening_amount) + cash_sales_total + movements_total


class BilletageRequiredError(Exception):
    """Raised when the POS requires billetage counting but no FECHO count has been recorded yet."""
    pass


async def close_session(
    db: AsyncSession,
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    closed_by_user_id: uuid.UUID,
    closing_amount_counted: float | None = None,
    closing_notes: str | None = None,
) -> CashSession:
    session = await get_session_or_raise(db, company_id, session_id)
    if session.status == CashSessionStatus.FECHADA:
        raise SessionAlreadyClosedError("Esta sessao de caixa ja esta fechada")

    pos = await get_pos_or_raise(db, company_id, session.pos_id)
    if pos.billetage_enabled:
        # Deferred imports: cash_denomination_count_service is a higher-level module
        # that doesn't need to be imported at module load time for every session close.
        from app.services.cash_denomination_count_service import get_latest_count, get_count_total
        fecho_count = await get_latest_count(db, company_id, session_id, DenominationCountType.FECHO)
        if fecho_count is None:
            raise BilletageRequiredError(
                "Esta caixa exige billetagem - registe a contagem por denominacao antes de fechar"
            )
        closing_amount_counted = await get_count_total(db, fecho_count.id)
    elif closing_amount_counted is None:
        raise ValueError("closing_amount_counted e obrigatorio quando a billetagem nao esta ativa")

    expected = await get_current_expected_cash_balance(db, company_id, session.pos_id, session)

    session.closed_by_user_id = closed_by_user_id
    session.closing_amount_expected = expected
    session.closing_amount_counted = closing_amount_counted
    session.closing_difference = round(closing_amount_counted - expected, 2)
    session.closing_notes = closing_notes
    session.status = CashSessionStatus.FECHADA
    from sqlalchemy import func as sa_func
    session.closed_at = sa_func.now()

    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession, company_id: uuid.UUID,
    activity_id: uuid.UUID | None = None, pos_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[CashSession]:
    query = select(CashSession).where(CashSession.company_id == company_id)
    if activity_id is not None:
        query = query.where(CashSession.activity_id == activity_id)
    if pos_id is not None:
        query = query.where(CashSession.pos_id == pos_id)
    query = query.order_by(CashSession.opened_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
