"""
Business logic for the POS/Caixa checkout flow - combines invoice
creation (via invoice_service.create_invoice) with split payments and the
active CashSession's business_date, as ONE atomic sale.
"""
from datetime import date
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.services.cash_session_service import get_open_session, SessionNotFoundError
from app.services.user_cash_point_access_service import require_cash_point_access
from app.services.invoice_service import create_invoice, convert_pro_forma_to_invoice, create_pro_forma


class NoOpenSessionError(Exception):
    """Raised when trying to sell without an open cash session for the activity."""
    pass


async def _ensure_sellable_at_pos(db: AsyncSession, company_id: uuid.UUID, lines_input: list[dict]) -> None:
    """THE Caixa guard - sale, pro-forma and open accounts (closed through checkout): an article marked 'nao disponivel
    POS' is never sold from a cash point. The screen hides it; the server refuses it."""
    from sqlalchemy import select
    from app.models.product import Product
    from app.models.service import Service
    from app.services.invoice_service import ProductNotFoundError
    for model, key in ((Product, "product_id"), (Service, "service_id")):
        ids = {uuid.UUID(str(l[key])) for l in lines_input if l.get(key)}
        if not ids:
            continue
        name = (await db.execute(
            select(model.name).where(model.id.in_(ids), model.company_id == company_id, model.not_available_pos.is_(True))
        )).scalars().first()
        if name:
            raise ProductNotFoundError(f"{name} nao esta disponivel para venda na caixa")


async def checkout(
    db: AsyncSession,
    company_id: uuid.UUID,
    pos_id: uuid.UUID,
    selling_user: "User",
    customer_id: uuid.UUID | None,
    lines_input: list[dict],
    payments: list[dict],
    invoice_type: str = "FACTURA",
    discount_global_percent: float = 0,
    payment_term_id: uuid.UUID | None = None,
    payment_method_id: uuid.UUID | None = None,
    bank_account_id: uuid.UUID | None = None,
    due_date=None,
) -> Invoice:
    """
    Completes a POS sale: requires an open CashSession for this specific POS
    (see cash_session_service.open_session) - activity_id for the invoice is
    taken from the session (denormalized from the POS at open time, see
    CashSession model docstring), the session's business_date becomes the
    invoice's date, and every payment line is recorded against the invoice,
    split across methods if the customer paid with more than one (e.g. part
    cash, part Multicaixa Express). Requires the caller to be associated with
    this exact POS (GESTOR bypasses this check). invoice_type defaults to
    FACTURA but can be FACTURA_RECIBO (chosen from the Caixa screen's document
    type selector) - discount_global_percent applies on top of any per-line
    discount, same as the admin NovaFatura flow.
    """
    await require_cash_point_access(db, company_id, selling_user, pos_id)
    session = await get_open_session(db, company_id, pos_id)
    if session is None:
        raise NoOpenSessionError("Nao ha nenhuma sessao de caixa aberta para este ponto de venda - abra a caixa antes de vender")
    await _ensure_sellable_at_pos(db, company_id, lines_input)

    invoice = await create_invoice(
        db, company_id, session.activity_id, customer_id, invoice_type=invoice_type,
        lines_input=lines_input,
        business_date=date.today(),  # the real day of the sale, never the session's (it may be days old)
        cash_session_id=session.id,
        payments=payments if payments else None,
        discount_global_percent=discount_global_percent,
        payment_term_id=payment_term_id,
        payment_method_id=payment_method_id,
        bank_account_id=bank_account_id,
        due_date=due_date,
    )
    return invoice


async def create_pro_forma_from_pos(
    db: AsyncSession,
    company_id: uuid.UUID,
    pos_id: uuid.UUID,
    selling_user: "User",
    customer_id: uuid.UUID | None,
    lines_input: list[dict],
    discount_global_percent: float = 0,
) -> Invoice:
    """
    Generates a Pro-forma (FP) from the Caixa screen - no payment involved (see
    create_pro_forma docstring: non-fiscal, no stock deduction, no AGT submission).
    Still requires an open CashSession for this POS and the caller's association,
    same access rules as checkout(), even though the pro-forma itself is not
    linked to the session (cash_session_id is only meaningful for real sales).
    """
    await require_cash_point_access(db, company_id, selling_user, pos_id)
    session = await get_open_session(db, company_id, pos_id)
    if session is None:
        raise NoOpenSessionError("Nao ha nenhuma sessao de caixa aberta para este ponto de venda - abra a caixa antes de gerar documentos")
    await _ensure_sellable_at_pos(db, company_id, lines_input)

    pro_forma = await create_pro_forma(
        db, company_id, session.activity_id, customer_id,
        lines_input=lines_input,
        business_date=date.today(),  # the real day of the sale, never the session's (it may be days old)
        discount_global_percent=discount_global_percent,
    )
    return pro_forma


async def liquidate_pending_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    pos_id: uuid.UUID,
    pro_forma_id: uuid.UUID,
    target_invoice_type: str,
    payments: list[dict],
) -> Invoice:
    """
    Liquidates a pending Pro-forma from the Caixa screen: requires an open
    CashSession for this POS (same rule as checkout), converts the pro-forma
    into a real fiscal invoice via convert_pro_forma_to_invoice, and links
    the resulting invoice + its payments to the open session exactly like a
    fresh sale - so close_session's expected-amount calculation accounts
    for the cash collected here.
    """
    session = await get_open_session(db, company_id, pos_id)
    if session is None:
        raise NoOpenSessionError("Nao ha nenhuma sessao de caixa aberta para este ponto de venda - abra a caixa antes de liquidar")

    invoice = await convert_pro_forma_to_invoice(
        db, company_id, pro_forma_id, target_invoice_type,
        business_date=date.today(),  # the real day of the sale, never the session's (it may be days old)
        cash_session_id=session.id,
        payments=payments,
    )
    return invoice



async def get_pos_stock(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> dict:
    """
    The stock a point of sale sells from - its activity's warehouse: the quantity of every product managed by stock
    (0 when it has no stock row yet), whether the warehouse allows a negative stock, and whether its exits are blocked.
    Products not managed by stock are absent: the till never checks them. The till warns with it before checkout;
    the server's own stock rule still decides at checkout.
    """
    from sqlalchemy import select
    from app.models.activity import Activity
    from app.models.point_of_sale import PointOfSale
    from app.models.product import Product
    from app.models.stock import Stock
    from app.models.warehouse import Warehouse

    empty = {"warehouse_id": None, "allow_negative_stock": True, "exits_blocked": False, "stock": {}}
    pos = (await db.execute(
        select(PointOfSale).where(PointOfSale.id == pos_id, PointOfSale.company_id == company_id)
    )).scalar_one_or_none()
    if pos is None:
        return empty
    activity = (await db.execute(select(Activity).where(Activity.id == pos.activity_id))).scalar_one_or_none()
    if activity is None or activity.warehouse_id is None:
        return empty
    warehouse = (await db.execute(select(Warehouse).where(Warehouse.id == activity.warehouse_id))).scalar_one()
    managed = (await db.execute(
        select(Product.id).where(
            Product.company_id == company_id, Product.is_active.is_(True), Product.managed_by_stock.is_(True),
        )
    )).scalars().all()
    quantities = dict((await db.execute(
        select(Stock.product_id, Stock.quantity).where(Stock.warehouse_id == warehouse.id)
    )).all())
    # What sits on open accounts is already served (a beer on table 2): it is no longer on the shelf, even though
    # the stock only moves when the account is closed. The till and the open accounts both sell what is left.
    from app.services.open_account_service import engaged_on_open_accounts
    engaged = await engaged_on_open_accounts(db, warehouse.id)
    return {
        "warehouse_id": str(warehouse.id),
        "allow_negative_stock": bool(warehouse.allow_negative_stock),
        "exits_blocked": bool(getattr(warehouse, "saidas_bloqueadas", False)),
        "stock": {str(pid): float(quantities.get(pid, 0) or 0) - engaged.get(pid, 0.0) for pid in managed},
    }
