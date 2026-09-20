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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.open_account_transfer import OpenAccountTransfer
from app.models.product import Product
from app.models.service import Service
from app.services.point_of_sale_service import get_pos_or_raise
from app.services.resource_service import get_resource_or_raise
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
        if item.is_raw_material:
            raise ItemNotFoundError("Materia-prima nao pode ser adicionada a uma conta")
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
    # first() + ORDER BY, not scalar_one_or_none(): a transfer (see transfer_lines) can leave
    # two lines for the same item on one account - transferred lines are never merged into
    # existing ones, so their snapshot prices stay untouched.
    existing_result = await db.execute(
        select(OpenAccountLine).where(
            OpenAccountLine.account_id == account_id,
            OpenAccountLine.product_id == product_id,
            OpenAccountLine.service_id == service_id,
        ).order_by(OpenAccountLine.added_at).limit(1)
    )
    existing_line = existing_result.scalars().first()
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


class InvalidTransferError(Exception):
    pass


_QTY_EPS = 1e-9


async def transfer_lines(
    db: AsyncSession, company_id: uuid.UUID, source_account_id: uuid.UUID, moved_by_user_id: uuid.UUID,
    items: list[dict], target_account_id: uuid.UUID | None = None,
    target_resource_id: uuid.UUID | None = None, new_label: str | None = None,
) -> tuple[OpenAccount, OpenAccount, bool]:
    """Moves lines (or parts of lines) from one open account to another - the single
    operation behind "transfer the order to another table" and "split the bill".

    items: [{"line_id": UUID, "quantity": float}, ...].
    Destination: an existing open account (target_account_id), or a NEW one created in
    the same transaction - on target_resource_id (another table; the label defaults to
    its name) or, without it, on the SAME resource as the source under new_label (a split).

    Nothing is ever deleted: a full line keeps its row and simply changes account; a
    partial move lowers the source line and adds a copy (same name/price snapshot) to
    the target. Transferred lines are never merged into existing ones, so snapshot
    prices stay untouched. Every move is recorded in OpenAccountTransfer (insert-only
    audit). If the source ends up without lines it is closed (FECHADA, no invoice) so
    the table is freed. Hotel stay accounts (booking_id set) and accounts of different
    points of sale are refused. Returns (source, target, source_closed).
    """
    source = await get_account_or_raise(db, company_id, source_account_id)
    if source.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")
    if source.booking_id is not None:
        raise InvalidTransferError("Contas de estadia de hotel nao permitem transferencia de linhas")
    if not items:
        raise InvalidTransferError("Selecione pelo menos um artigo para transferir")

    wanted: dict[uuid.UUID, float] = {}
    for item in items:
        line_id, quantity = item["line_id"], float(item["quantity"])
        if quantity <= 0:
            raise InvalidTransferError("A quantidade a transferir deve ser superior a zero")
        if line_id in wanted:
            raise InvalidTransferError("O mesmo artigo foi indicado mais de uma vez")
        wanted[line_id] = quantity

    lines_result = await db.execute(
        select(OpenAccountLine).where(OpenAccountLine.id.in_(list(wanted)), OpenAccountLine.account_id == source.id).with_for_update()
    )
    lines = {l.id: l for l in lines_result.scalars().all()}
    if len(lines) != len(wanted):
        raise ItemNotFoundError("Linha nao encontrada nesta conta")
    for line_id, quantity in wanted.items():
        if quantity - float(lines[line_id].quantity) > _QTY_EPS:
            raise InvalidTransferError("Quantidade a transferir superior a quantidade existente na conta")

    if target_account_id is not None:
        if target_account_id == source.id:
            raise InvalidTransferError("A conta de destino deve ser diferente da conta de origem")
        target = await get_account_or_raise(db, company_id, target_account_id)
        if target.status == OpenAccountStatus.FECHADA:
            raise AccountAlreadyClosedError("A conta de destino ja esta fechada")
        if target.booking_id is not None:
            raise InvalidTransferError("Contas de estadia de hotel nao permitem transferencia de linhas")
        if target.pos_id != source.pos_id:
            raise InvalidTransferError("As contas devem pertencer ao mesmo ponto de venda")
    else:
        label = (new_label or "").strip()
        resource_id = source.resource_id
        if target_resource_id is not None:
            resource = await get_resource_or_raise(db, company_id, target_resource_id)
            if not resource.is_active:
                raise InvalidTransferError("Este recurso esta inativo")
            if resource.activity_id != source.activity_id:
                raise InvalidTransferError("O recurso de destino pertence a outra atividade")
            resource_id = resource.id
            label = label or resource.name
        if not label:
            raise InvalidTransferError("Indique a conta de destino ou um nome para a nova conta")
        target = OpenAccount(
            company_id=company_id, activity_id=source.activity_id, pos_id=source.pos_id, resource_id=resource_id,
            customer_id=source.customer_id, label=label[:100], notes=source.notes, opened_by_user_id=moved_by_user_id,
        )
        db.add(target)
        await db.flush()

    for line_id, quantity in wanted.items():
        line = lines[line_id]
        if float(line.quantity) - quantity <= _QTY_EPS:
            moved_quantity = float(line.quantity)
            line.account_id = target.id
            target_line = line
        else:
            moved_quantity = quantity
            line.quantity = float(line.quantity) - quantity
            target_line = OpenAccountLine(
                account_id=target.id, product_id=line.product_id, service_id=line.service_id,
                name_snapshot=line.name_snapshot, quantity=quantity, unit_price=line.unit_price,
                added_by_user_id=line.added_by_user_id, added_at=line.added_at,
            )
            db.add(target_line)
            await db.flush()
        db.add(OpenAccountTransfer(
            company_id=company_id, source_account_id=source.id, target_account_id=target.id,
            source_line_id=line.id, target_line_id=target_line.id, name_snapshot=line.name_snapshot,
            quantity=moved_quantity, unit_price=line.unit_price, moved_by_user_id=moved_by_user_id,
        ))
    await db.flush()

    remaining = (await db.execute(
        select(func.count()).select_from(OpenAccountLine).where(OpenAccountLine.account_id == source.id)
    )).scalar_one()
    source_closed = remaining == 0
    if source_closed:
        source.status = OpenAccountStatus.FECHADA
        source.closed_at = func.now()

    await db.commit()
    await db.refresh(source)
    await db.refresh(target)
    return source, target, source_closed
