"""
Service layer for OpenAccount - the generic running-tab engine. See
app.models.open_account for the full design rationale.

close_account is the key operation: it converts the account's accumulated
lines into a real Invoice via the existing pos_service.checkout pipeline
(the same one Caixa's normal sale flow uses), so every downstream concern
(stock deduction, VAT calculation, AGT series/numbering, payment recording)
is handled exactly once, in exactly one place - this module never
duplicates that logic.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.product import Product
from app.models.service import Service
from app.services.point_of_sale_service import get_pos_or_raise
from app.services.pos_service import checkout


class OpenAccountNotFoundError(Exception):
    pass


class AccountAlreadyClosedError(Exception):
    pass


class EmptyAccountError(Exception):
    pass


class ItemNotFoundError(Exception):
    pass


async def open_account(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, pos_id: uuid.UUID, opened_by_user_id: uuid.UUID,
    label: str, resource_id: uuid.UUID | None = None, customer_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> OpenAccount:
    await get_pos_or_raise(db, company_id, pos_id)
    account = OpenAccount(
        company_id=company_id, activity_id=activity_id, pos_id=pos_id, resource_id=resource_id,
        customer_id=customer_id, label=label, notes=notes, opened_by_user_id=opened_by_user_id,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def get_account_or_raise(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID) -> OpenAccount:
    result = await db.execute(select(OpenAccount).where(OpenAccount.id == account_id, OpenAccount.company_id == company_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise OpenAccountNotFoundError("Conta nao encontrada")
    return account


async def list_open_accounts(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None = None) -> list[OpenAccount]:
    query = select(OpenAccount).where(OpenAccount.company_id == company_id, OpenAccount.status == OpenAccountStatus.ABERTA)
    if activity_id is not None:
        query = query.where(OpenAccount.activity_id == activity_id)
    result = await db.execute(query.order_by(OpenAccount.opened_at))
    return list(result.scalars().all())


async def list_account_lines(db: AsyncSession, account_id: uuid.UUID) -> list[OpenAccountLine]:
    result = await db.execute(select(OpenAccountLine).where(OpenAccountLine.account_id == account_id).order_by(OpenAccountLine.added_at))
    return list(result.scalars().all())


async def add_line(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, added_by_user_id: uuid.UUID,
    quantity: float, product_id: uuid.UUID | None = None, service_id: uuid.UUID | None = None,
) -> OpenAccountLine:
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")

    if product_id is not None:
        result = await db.execute(select(Product).where(Product.id == product_id, Product.company_id == company_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise ItemNotFoundError("Produto nao encontrado")
        name_snapshot, unit_price = item.name, float(item.price)
    elif service_id is not None:
        result = await db.execute(select(Service).where(Service.id == service_id, Service.company_id == company_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise ItemNotFoundError("Servico nao encontrado")
        name_snapshot, unit_price = item.name, float(item.price or 0)
    else:
        raise ItemNotFoundError("Indique um produto ou servico")

    # If this product/service is already on the account, bump its quantity instead
    # of adding a duplicate line - matches Caixa's cart behaviour (see the "multiple
    # lines for Pao de Forma" discussion), so the bill reads as one line per item.
    existing_result = await db.execute(
        select(OpenAccountLine).where(
            OpenAccountLine.account_id == account_id,
            OpenAccountLine.product_id == product_id,
            OpenAccountLine.service_id == service_id,
        )
    )
    existing_line = existing_result.scalar_one_or_none()
    if existing_line is not None:
        existing_line.quantity = float(existing_line.quantity) + quantity
        await db.commit()
        await db.refresh(existing_line)
        return existing_line

    line = OpenAccountLine(
        account_id=account_id, product_id=product_id, service_id=service_id,
        name_snapshot=name_snapshot, quantity=quantity, unit_price=unit_price, added_by_user_id=added_by_user_id,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return line


async def update_line_quantity(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, line_id: uuid.UUID, quantity: float,
) -> OpenAccountLine | None:
    """Sets a line's quantity directly (e.g. +/- buttons on the line). A quantity
    of 0 or less removes the line entirely (matches Caixa's cart UX) and returns
    None in that case."""
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")

    result = await db.execute(select(OpenAccountLine).where(OpenAccountLine.id == line_id, OpenAccountLine.account_id == account_id))
    line = result.scalar_one_or_none()
    if line is None:
        return None

    if quantity <= 0:
        await db.delete(line)
        await db.commit()
        return None

    line.quantity = quantity
    await db.commit()
    await db.refresh(line)
    return line


async def remove_line(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, line_id: uuid.UUID) -> None:
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")
    result = await db.execute(select(OpenAccountLine).where(OpenAccountLine.id == line_id, OpenAccountLine.account_id == account_id))
    line = result.scalar_one_or_none()
    if line is not None:
        await db.delete(line)
        await db.commit()


async def close_account(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, closing_user: "User",
    payments: list[dict], invoice_type: str = "FACTURA_RECIBO",
) -> OpenAccount:
    """Converts the account's lines into a real Invoice via pos_service.checkout,
    then marks the account FECHADA and links the resulting invoice."""
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")

    lines = await list_account_lines(db, account_id)
    if not lines:
        raise EmptyAccountError("Nao e possivel fechar uma conta sem artigos")

    lines_input = [
        {"product_id": str(l.product_id) if l.product_id else None, "service_id": str(l.service_id) if l.service_id else None, "quantity": float(l.quantity)}
        for l in lines
    ]

    invoice = await checkout(
        db, company_id, account.pos_id, closing_user, account.customer_id, lines_input, payments,
        invoice_type=invoice_type,
    )

    account.status = OpenAccountStatus.FECHADA
    account.invoice_id = invoice.id
    from sqlalchemy import func as sa_func
    account.closed_at = sa_func.now()
    await db.commit()
    await db.refresh(account)
    return account
