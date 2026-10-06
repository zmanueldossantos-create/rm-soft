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

from app.services.document_rules import default_paid_on_issue_type
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
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, pos_id: uuid.UUID | None, opened_by_user_id: uuid.UUID,
    label: str, resource_id: uuid.UUID | None = None, customer_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> OpenAccount:
    # No till is chosen to open an account: it belongs to the activity. pos_id only records where it was opened
    # (the activity's default till when none is given); the till that closes it is the one that cashes it.
    if pos_id is None:
        pos_id = await _default_pos_of(db, company_id, activity_id)
    else:
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


async def _list_open_account_rows(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None = None) -> list[OpenAccount]:
    query = select(OpenAccount).where(OpenAccount.company_id == company_id, OpenAccount.status == OpenAccountStatus.ABERTA)
    if activity_id is not None:
        query = query.where(OpenAccount.activity_id == activity_id)
    result = await db.execute(query.order_by(OpenAccount.opened_at))
    return list(result.scalars().all())


async def _list_account_line_rows(db: AsyncSession, account_id: uuid.UUID) -> list[OpenAccountLine]:
    result = await db.execute(select(OpenAccountLine).where(OpenAccountLine.account_id == account_id).order_by(OpenAccountLine.added_at))
    return list(result.scalars().all())


async def add_line(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, added_by_user_id: uuid.UUID,
    quantity: float, product_id: uuid.UUID | None = None, service_id: uuid.UUID | None = None,
    sale_unit_id: uuid.UUID | None = None,
) -> OpenAccountLine:
    if float(quantity) <= 0:
        raise InvalidLineError("A quantidade deve ser superior a zero")
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
        # Sold in its base unit or one of its sale units (a CX of 24 at its own price), exactly as in the till.
        unit_price, unit_factor, line_sale_unit_id, unit_code = await _resolve_unit(db, company_id, item, sale_unit_id, quantity)
        name_snapshot = item.name
        kitchen_status = KITCHEN_NOT_SENT if item.prepared_in_kitchen else None
    elif service_id is not None:
        result = await db.execute(select(Service).where(Service.id == service_id, Service.company_id == company_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise ItemNotFoundError("Servico nao encontrado")
        name_snapshot, unit_price = item.name, float(item.price or 0)
        unit_factor, line_sale_unit_id, unit_code = 1.0, None, None
        kitchen_status = None
    else:
        raise ItemNotFoundError("Indique um produto ou servico")

    if product_id is not None:
        await _ensure_stock(db, company_id, account, item, float(quantity) * unit_factor)

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
            OpenAccountLine.sale_unit_id == line_sale_unit_id,
            # a dish already sent is never added to: the new one leaves with the next sending
            func.coalesce(OpenAccountLine.kitchen_status, KITCHEN_NOT_SENT) == KITCHEN_NOT_SENT,
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
        sale_unit_id=line_sale_unit_id, unit_factor=unit_factor, unit_code_snapshot=unit_code,
        kitchen_status=kitchen_status,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return line


async def update_line_quantity(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, line_id: uuid.UUID, quantity: float,
    user_id: uuid.UUID | None = None,
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

    if line.kitchen_status in KITCHEN_LOCKED:
        raise InvalidLineError(_LOCKED_MESSAGE[line.kitchen_status])
    if line.kitchen_status == KITCHEN_WAITING:
        # sent, not started yet: the room may lower it (the kitchen sees 'Modificado') or cancel it - never raise it
        if float(quantity) - float(line.quantity) > _QTY_EPS:
            raise InvalidLineError("Este prato ja foi enviado para a cozinha - adicione-o de novo, segue no proximo envio")
        if quantity <= 0:
            _cancel_line(line, "Anulado pela sala", user_id)
        else:
            line.quantity = quantity
            line.kitchen_modified = True
        await db.commit()
        await db.refresh(line)
        return line

    if quantity <= 0:
        await db.delete(line)
        await db.commit()
        return None

    if line.product_id is not None:
        product = await _product_or_raise(db, company_id, line.product_id)
        await _resolve_unit(db, company_id, product, line.sale_unit_id, quantity)  # a decimal quantity only in KG, L...
        delta = (float(quantity) - float(line.quantity)) * float(line.unit_factor or 1)
        if delta > _QTY_EPS:  # a lower quantity always passes, as in the till
            await _ensure_stock(db, company_id, account, product, delta)

    line.quantity = quantity
    await db.commit()
    await db.refresh(line)
    return line


async def remove_line(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, line_id: uuid.UUID, user_id: uuid.UUID | None = None) -> None:
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")
    result = await db.execute(select(OpenAccountLine).where(OpenAccountLine.id == line_id, OpenAccountLine.account_id == account_id))
    line = result.scalar_one_or_none()
    if line is None:
        return
    if line.kitchen_status in KITCHEN_LOCKED:
        raise InvalidLineError(_LOCKED_MESSAGE[line.kitchen_status])
    if line.kitchen_status == KITCHEN_WAITING:
        _cancel_line(line, "Anulado pela sala", user_id)  # the kitchen sees it struck through
    else:
        await db.delete(line)
    await db.commit()


async def close_account(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, closing_user: "User",
    payments: list[dict], invoice_type: str | None = None, pos_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None, discount_global_percent: float = 0, payment_term_id: uuid.UUID | None = None,
) -> OpenAccount:
    """Converts the account's lines into a real Invoice via pos_service.checkout,
    then marks the account FECHADA and links the resulting invoice."""
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")

    lines = await list_account_lines(db, account_id)
    lines = [l for l in lines if l.kitchen_status != KITCHEN_CANCELLED]  # a cancelled dish is never invoiced
    if not lines:
        raise EmptyAccountError("Nao e possivel fechar uma conta sem artigos")

    lines_input = [
        {"product_id": str(l.product_id) if l.product_id else None, "service_id": str(l.service_id) if l.service_id else None, "quantity": float(l.quantity),
         "sale_unit_id": str(l.sale_unit_id) if l.sale_unit_id else None}
        for l in lines
    ]

    if invoice_type is None:  # by default the catalog decides: a type paid on issue
        invoice_type = await default_paid_on_issue_type(db)
    # Cashed by the till that closes it (its session, its balance, its series) - any till of the activity.
    closing_pos_id = account.pos_id
    if pos_id is not None and pos_id != account.pos_id:
        await _ensure_pos_of_activity(db, company_id, pos_id, account.activity_id)
        closing_pos_id = pos_id
    invoice = await checkout(
        db, company_id, closing_pos_id, closing_user, customer_id or account.customer_id, lines_input, payments,
        invoice_type=invoice_type, discount_global_percent=discount_global_percent, payment_term_id=payment_term_id,
    )
    if customer_id is not None:
        account.customer_id = customer_id  # the customer the account was invoiced to

    account.status = OpenAccountStatus.FECHADA
    account.invoice_id = invoice.id
    account.pos_id = closing_pos_id  # the till that cashed it
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
        if lines[line_id].kitchen_status == KITCHEN_CANCELLED:
            raise InvalidTransferError("Uma linha anulada nao se transfere")

    if target_account_id is not None:
        if target_account_id == source.id:
            raise InvalidTransferError("A conta de destino deve ser diferente da conta de origem")
        target = await get_account_or_raise(db, company_id, target_account_id)
        if target.status == OpenAccountStatus.FECHADA:
            raise AccountAlreadyClosedError("A conta de destino ja esta fechada")
        if target.booking_id is not None:
            raise InvalidTransferError("Contas de estadia de hotel nao permitem transferencia de linhas")
        if target.activity_id != source.activity_id:
            raise InvalidTransferError("As contas devem pertencer a mesma atividade")
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
                sale_unit_id=line.sale_unit_id, unit_factor=line.unit_factor, unit_code_snapshot=line.unit_code_snapshot,
                kitchen_status=line.kitchen_status, kitchen_order_id=line.kitchen_order_id, kitchen_modified=line.kitchen_modified,
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


# ---------------------------------------------------------------------------------------------------------------
# An open account is a till cart kept open: same units, same stock rule. One difference: it is shared (several
# waiters, several tables, for hours), so the check runs on the server, against what the other accounts hold.

class InsufficientStockError(Exception):
    pass


class InvalidLineError(Exception):
    pass


def _fmt_qty(value: float) -> str:
    """1.5 -> '1,5' ; 24.0 -> '24' (PT notation, up to 3 decimals)."""
    return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",")


async def _product_or_raise(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = (await db.execute(
        select(Product).where(Product.id == product_id, Product.company_id == company_id)
    )).scalar_one_or_none()
    if product is None:
        raise ItemNotFoundError("Produto nao encontrado")
    return product


async def _resolve_unit(
    db: AsyncSession, company_id: uuid.UUID, product: Product, sale_unit_id, quantity: float | None,
) -> tuple[float, float, uuid.UUID | None, str | None]:
    """Price, factor, sale unit and unit code of a product line - the till's own rule (resolve_line_unit):
    an internal-use article is never sold, a decimal quantity only in a fractional unit (KG, L)."""
    if getattr(product, "internal_use_only", False):
        raise InvalidLineError(f"{product.name} e de uso interno e nao pode ser vendido")
    from app.services.product_sale_unit_service import SaleUnitInvalidError, resolve_line_unit
    try:
        price, factor, su_id, code = await resolve_line_unit(db, company_id, product, sale_unit_id, quantity)
    except SaleUnitInvalidError as e:
        raise InvalidLineError(str(e))
    return float(price), float(factor or 1), su_id, code


async def engaged_on_open_accounts(db: AsyncSession, warehouse_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """Base-unit quantity of every product sitting on the open accounts selling from this warehouse.
    What is on an open account is already served: it is no longer on the shelf, even though the stock
    only moves when the account is closed (pos_service.get_pos_stock subtracts it)."""
    from app.models.activity import Activity
    rows = (await db.execute(
        select(OpenAccountLine.product_id, func.sum(OpenAccountLine.quantity * OpenAccountLine.unit_factor))
        .join(OpenAccount, OpenAccount.id == OpenAccountLine.account_id)
        .join(Activity, Activity.id == OpenAccount.activity_id)
        .where(
            OpenAccount.status == OpenAccountStatus.ABERTA,
            Activity.warehouse_id == warehouse_id,
            OpenAccountLine.product_id.is_not(None),
            OpenAccountLine.kitchen_status.is_distinct_from(KITCHEN_CANCELLED),
        )
        .group_by(OpenAccountLine.product_id)
    )).all()
    return {pid: float(q or 0) for pid, q in rows}


async def _ensure_stock(
    db: AsyncSession, company_id: uuid.UUID, account: OpenAccount, product: Product, extra_base: float,
) -> None:
    """The till cart's stock rule, applied on the server: extra_base more base units of the product must fit in
    what is left in the warehouse of the account's point of sale (stock minus every open account) - unless the
    warehouse allows a negative stock. Exits blocked refuse everything."""
    if not product.managed_by_stock or extra_base <= _QTY_EPS:
        return
    # One writer at a time per product: two waiters can never both take the last unit.
    await db.execute(select(Product.id).where(Product.id == product.id).with_for_update())
    from app.services.pos_service import get_pos_stock
    pos_stock = await get_pos_stock(db, company_id, account.pos_id)
    if pos_stock["warehouse_id"] is None:
        return
    if pos_stock["exits_blocked"]:
        raise InsufficientStockError("Saidas bloqueadas no armazem deste ponto de venda")
    if pos_stock["allow_negative_stock"]:
        return
    available = float(pos_stock["stock"].get(str(product.id), 0.0))
    if extra_base - available > _QTY_EPS:
        _, _, _, base_code = await _resolve_unit(db, company_id, product, None, None)
        raise InsufficientStockError(f"Stock insuficiente: {_fmt_qty(max(available, 0.0))} {base_code or 'UN'} disponivel")


async def change_line_unit(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, line_id: uuid.UUID, sale_unit_id: uuid.UUID | None,
) -> OpenAccountLine:
    """Sells a product line in another unit (UN <-> CX), as the till cart's unit selector: the price follows the
    unit, a bigger unit must fit in the stock."""
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")
    line = (await db.execute(
        select(OpenAccountLine).where(OpenAccountLine.id == line_id, OpenAccountLine.account_id == account_id)
    )).scalar_one_or_none()
    if line is None:
        raise ItemNotFoundError("Linha nao encontrada nesta conta")
    if line.product_id is None:
        raise InvalidLineError("Um servico nao tem outras unidades")
    if line.kitchen_status not in (None, KITCHEN_NOT_SENT):
        raise InvalidLineError("Este prato ja foi enviado para a cozinha")
    product = await _product_or_raise(db, company_id, line.product_id)
    price, factor, su_id, code = await _resolve_unit(db, company_id, product, sale_unit_id, float(line.quantity))
    delta = float(line.quantity) * (factor - float(line.unit_factor or 1))
    if delta > _QTY_EPS:
        await _ensure_stock(db, company_id, account, product, delta)
    line.sale_unit_id, line.unit_factor, line.unit_code_snapshot, line.unit_price = su_id, factor, code, price
    await db.commit()
    await db.refresh(line)
    return line


async def list_open_accounts(db: AsyncSession, company_id: uuid.UUID, *args: object, **kwargs: object) -> list[OpenAccount]:
    """The open accounts, each with its number of lines and its total (what the account cards show) - one query
    for all of them, whatever filters the listing itself takes."""
    accounts = await _list_open_account_rows(db, company_id, *args, **kwargs)
    totals = await _account_totals(db, [a.id for a in accounts])
    ready = await _ready_dishes(db, [a.id for a in accounts])
    for account in accounts:
        account.ready_dishes = ready.get(account.id, 0)
        account.line_count, account.subtotal, account.vat_total, account.total = totals.get(account.id, (0, 0.0, 0.0, 0.0))
    return accounts


# ---------------------------------------------------------------------------------------------------------------
# What an account will cost. A price is before VAT (the invoice adds the rate of each article), so the account
# computes exactly as invoice_service.create_invoice does: per line, subtotal rounded, VAT rounded, then the sums.
# The screen only adds up these amounts - the total it asks for at closing is the one the invoice will charge.

_LINES_WITH_VAT = """
    SELECT l.id, l.account_id, l.quantity, l.unit_price, COALESCE(pv.rate, sv.rate, 0) AS vat_rate
    FROM open_account_lines l
    LEFT JOIN products p ON p.id = l.product_id
    LEFT JOIN vat_rates pv ON pv.id = p.vat_id
    LEFT JOIN services s ON s.id = l.service_id
    LEFT JOIN vat_rates sv ON sv.id = s.vat_id
    WHERE l.{column} = ANY(:ids)
      AND (l.kitchen_status IS NULL OR l.kitchen_status <> 'ANULADO')
"""


def _line_amounts(quantity: float, unit_price: float, vat_rate: float) -> tuple[float, float, float]:
    """Subtotal, VAT and total of one line - the invoice's own rounding (create_invoice)."""
    subtotal = round(float(quantity) * float(unit_price), 2)
    vat = round(subtotal * (float(vat_rate) / 100), 2)
    return subtotal, vat, round(subtotal + vat, 2)


async def _lines_with_vat(db: AsyncSession, column: str, ids: list[uuid.UUID]) -> list:
    """(line id, account id, quantity, unit price, VAT rate) of the lines whose `column` (id / account_id) is in ids."""
    if not ids:
        return []
    from sqlalchemy import text
    return (await db.execute(text(_LINES_WITH_VAT.format(column=column)), {"ids": list(ids)})).all()


async def _account_totals(db: AsyncSession, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, float, float, float]]:
    """account id -> (number of lines, subtotal, VAT, total) - accounts without lines are absent."""
    sums: dict[uuid.UUID, tuple[int, float, float]] = {}
    for _, account_id, quantity, unit_price, vat_rate in await _lines_with_vat(db, "account_id", account_ids):
        subtotal, vat, _ = _line_amounts(quantity, unit_price, vat_rate)
        count, s, v = sums.get(account_id, (0, 0.0, 0.0))
        sums[account_id] = (count + 1, s + subtotal, v + vat)
    return {
        account_id: (count, round(s, 2), round(v, 2), round(round(s, 2) + round(v, 2), 2))
        for account_id, (count, s, v) in sums.items()
    }


async def list_account_lines(db: AsyncSession, account_id: uuid.UUID) -> list[OpenAccountLine]:
    """The lines of an account, each with its VAT rate and its subtotal, VAT and total (as the invoice will)."""
    lines = await _list_account_line_rows(db, account_id)
    rates = {row[0]: float(row[4]) for row in await _lines_with_vat(db, "id", [l.id for l in lines])}
    for line in lines:
        line.vat_rate = rates.get(line.id, 0.0)
        if line.kitchen_status == KITCHEN_CANCELLED:  # struck through, never invoiced
            line.line_subtotal, line.line_vat, line.line_total = 0.0, 0.0, 0.0
        else:
            line.line_subtotal, line.line_vat, line.line_total = _line_amounts(line.quantity, line.unit_price, line.vat_rate)
    await _attach_kitchen_orders(db, lines)
    return lines


async def open_total_of_resource(db: AsyncSession, resource_id: uuid.UUID) -> float:
    """What the open accounts of a table / room will cost, VAT included (the floor plan's cards)."""
    ids = (await db.execute(
        select(OpenAccount.id).where(OpenAccount.resource_id == resource_id, OpenAccount.status == OpenAccountStatus.ABERTA)
    )).scalars().all()
    return round(sum(total for _, _, _, total in (await _account_totals(db, list(ids))).values()), 2)


async def cancel_empty_account(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID) -> OpenAccount:
    """Cancels an account opened by mistake: only while it holds no article. It is closed without any fiscal
    document - as a transfer closes the account it empties - and its table is freed. A hotel stay account is never
    cancelled here: it closes at check-out."""
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")
    if account.booking_id is not None:
        raise InvalidLineError("Uma conta de estadia fecha-se no check-out")
    lines = (await db.execute(
        select(func.count()).select_from(OpenAccountLine).where(
            OpenAccountLine.account_id == account.id, OpenAccountLine.kitchen_status.is_distinct_from(KITCHEN_CANCELLED),
        )
    )).scalar_one()
    if lines:
        raise InvalidLineError("So uma conta sem artigos pode ser anulada - retire ou transfira os artigos primeiro")
    account.status = OpenAccountStatus.FECHADA
    account.closed_at = func.now()
    await db.commit()
    await db.refresh(account)
    return account


# ---------------------------------------------------------------------------------------------------------------
# Kitchen (point 34b). A dish (product.prepared_in_kitchen) is added NAO_ENVIADO; "Enviar para cozinha" sends every
# unsent dish of the account in one KitchenOrder (who, when, number of the day). Once sent, the room may still lower
# or cancel it while EM_ESPERA; from EM_PREPARACAO on, only the kitchen changes it. A cancelled line stays, struck
# through, and is never invoiced.

KITCHEN_NOT_SENT = "NAO_ENVIADO"
KITCHEN_WAITING = "EM_ESPERA"
KITCHEN_PREPARING = "EM_PREPARACAO"
KITCHEN_READY = "PRONTO"
KITCHEN_CANCELLED = "ANULADO"
KITCHEN_LOCKED = (KITCHEN_PREPARING, KITCHEN_READY, KITCHEN_CANCELLED)
_LOCKED_MESSAGE = {
    KITCHEN_PREPARING: "A cozinha ja esta a preparar este prato",
    KITCHEN_READY: "Este prato ja esta pronto",
    KITCHEN_CANCELLED: "Esta linha esta anulada",
}


def _cancel_line(line: OpenAccountLine, reason: str, user_id: uuid.UUID | None = None) -> None:
    line.kitchen_status = KITCHEN_CANCELLED
    line.cancel_reason = reason
    line.cancelled_at = func.now()
    line.cancelled_by_user_id = user_id


async def _attach_kitchen_orders(db: AsyncSession, lines: list[OpenAccountLine]) -> None:
    """Who sent each dish, when, and in which order of the day - shown under the dish in the room and the kitchen."""
    from app.models.kitchen_order import KitchenOrder
    from app.models.user import User
    order_ids = {l.kitchen_order_id for l in lines if l.kitchen_order_id}
    orders = {}
    if order_ids:
        rows = (await db.execute(
            select(KitchenOrder.id, KitchenOrder.number, KitchenOrder.sent_at, User.full_name)
            .join(User, User.id == KitchenOrder.sent_by_user_id)
            .where(KitchenOrder.id.in_(order_ids))
        )).all()
        orders = {order_id: (number, sent_at, name) for order_id, number, sent_at, name in rows}
    for line in lines:
        line.kitchen_order_number, line.sent_at, line.sent_by_name = orders.get(line.kitchen_order_id, (None, None, None))


async def send_to_kitchen(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, sent_by_user_id: uuid.UUID,
) -> "KitchenOrder":
    """Sends every unsent dish of the account to the kitchen, in one order numbered for the day (#1, #2...)."""
    from datetime import date
    from sqlalchemy import text
    from app.models.kitchen_order import KitchenOrder
    account = await get_account_or_raise(db, company_id, account_id)
    if account.status == OpenAccountStatus.FECHADA:
        raise AccountAlreadyClosedError("Esta conta ja esta fechada")
    lines = (await db.execute(
        select(OpenAccountLine).where(
            OpenAccountLine.account_id == account.id, OpenAccountLine.kitchen_status == KITCHEN_NOT_SENT,
        ).with_for_update()
    )).scalars().all()
    if not lines:
        raise InvalidLineError("Nao ha pratos por enviar para a cozinha")
    today = date.today()
    # one numbering at a time per company and day: two tables sent at once never get the same number
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"kitchen:{company_id}:{today}"})
    last = (await db.execute(
        select(func.max(KitchenOrder.number)).where(KitchenOrder.company_id == company_id, KitchenOrder.day == today)
    )).scalar_one()
    order = KitchenOrder(company_id=company_id, account_id=account.id, day=today, number=(last or 0) + 1,
                         sent_by_user_id=sent_by_user_id)
    db.add(order)
    await db.flush()
    for line in lines:
        line.kitchen_status = KITCHEN_WAITING
        line.kitchen_order_id = order.id
    await db.commit()
    await db.refresh(order)
    return order


# ---------------------------------------------------------------------------------------------------------------
# Tills. An open account belongs to its activity, like its tables and its stock: no till is chosen to open it,
# every till of the activity sees it, and the one that closes it cashes it.

async def _default_pos_of(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID) -> uuid.UUID:
    """The activity's default till (else its oldest active one) - recorded where an account is opened."""
    from app.models.point_of_sale import PointOfSale
    pos_id = (await db.execute(
        select(PointOfSale.id).where(
            PointOfSale.company_id == company_id, PointOfSale.activity_id == activity_id, PointOfSale.is_active.is_(True),
        ).order_by(PointOfSale.is_default.desc(), PointOfSale.created_at)
    )).scalars().first()
    if pos_id is None:
        raise InvalidLineError("Esta atividade nao tem nenhum ponto de venda ativo")
    return pos_id


async def _ensure_pos_of_activity(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID, activity_id: uuid.UUID) -> None:
    """A till cashes only the accounts of its own activity."""
    pos = await get_pos_or_raise(db, company_id, pos_id)
    if pos.activity_id != activity_id:
        raise InvalidLineError("Este ponto de venda pertence a outra atividade")


async def _ready_dishes(db: AsyncSession, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """account id -> number of its dishes the kitchen has made ready (shown on the account card)."""
    if not account_ids:
        return {}
    rows = (await db.execute(
        select(OpenAccountLine.account_id, func.count(OpenAccountLine.id))
        .where(OpenAccountLine.account_id.in_(account_ids), OpenAccountLine.kitchen_status == KITCHEN_READY)
        .group_by(OpenAccountLine.account_id)
    )).all()
    return {account_id: int(count) for account_id, count in rows}
