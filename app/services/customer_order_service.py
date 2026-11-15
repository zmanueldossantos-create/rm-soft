"""
Encomendas (capability ORDERS): a customer's order to be made and handed over later - who, when, how it is delivered,
what (with a production note per line) and where it stands.

The money goes through the usual documents, at a till of the order's activity (pay_order, deliver_order):
- a deposit (sinal): the order's Fatura (FT, the whole order) is issued with it, and a Recibo (RC) for the amount -
  the goods are not handed over yet (often not even made): they leave the stock at the delivery;
- the delivery: a Recibo for what is still due (or nothing: «fica a dever», the FT stays to be received); an order
  never invoiced is sold at once - a Fatura/Recibo (FR), or a FT on credit;
- cancelled after its FT (gestor only): a credit note, and the deposit given back (DEVOLVIDO: the whole FT credited,
  the money refunded from a till or a bank account) or kept (RETIDO: only the part not paid is credited - the FT then
  stands for the deposit). Never delivered, nothing left the stock: nothing goes back.
Once invoiced, an order's lines no longer change (its delivery, contact and notes still do).

Rules:
- numbered ENC<year>/n per company (an internal, non-fiscal document), under a lock - two cashiers never get the same;
- a customer is required (the Consumidor final cannot be called back), the delivery date is never in the past when
  ordered, a delivery (ENTREGA) needs its address;
- changed while ENCOMENDADA or EM_PRODUCAO; production moves ENCOMENDADA <-> EM_PRODUCAO <-> PRONTA (a step back is
  allowed: a cake to redo); cancelled with a reason while not delivered;
- the activity is one whose sector has the Encomendas (capability ORDERS).
"""
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.customer import Customer
from app.models.customer_order import (
    DELIVERY_DELIVERY, DELIVERY_PICKUP, CustomerOrder, CustomerOrderLine, CustomerOrderStatus,
)
from app.models.product import Product
from app.models.service import Service
from app.models.vat import VAT

LUANDA = ZoneInfo("Africa/Luanda")
EDITABLE = (CustomerOrderStatus.ENCOMENDADA, CustomerOrderStatus.EM_PRODUCAO)
OPEN = (CustomerOrderStatus.ENCOMENDADA, CustomerOrderStatus.EM_PRODUCAO, CustomerOrderStatus.PRONTA)
# production moves one step at a time, back or forth
PRODUCTION_STEPS = {
    CustomerOrderStatus.ENCOMENDADA: {CustomerOrderStatus.EM_PRODUCAO},
    CustomerOrderStatus.EM_PRODUCAO: {CustomerOrderStatus.ENCOMENDADA, CustomerOrderStatus.PRONTA},
    CustomerOrderStatus.PRONTA: {CustomerOrderStatus.EM_PRODUCAO},
}
STATUS_LABELS = {
    CustomerOrderStatus.ENCOMENDADA: "Encomendada", CustomerOrderStatus.EM_PRODUCAO: "Em produção",
    CustomerOrderStatus.PRONTA: "Pronta", CustomerOrderStatus.ENTREGUE: "Entregue", CustomerOrderStatus.CANCELADA: "Cancelada",
}


class CustomerOrderError(Exception):
    """A refused order or change - the message is shown as is (PT-PT)."""


class CustomerOrderNotFoundError(CustomerOrderError):
    pass


def _money(value) -> float:
    return round(float(value or 0), 2)


def _kz(value) -> str:
    return f"{float(value or 0):,.2f}".replace(",", " ").replace(".", ",") + " Kz"


def reference(order: CustomerOrder) -> str:
    return f"ENC{order.year}/{order.number}"


async def order_activities(db: AsyncSession, company_id: uuid.UUID) -> list[Activity]:
    """The company's active activities whose sector has the Encomendas."""
    from app.services.sector_service import module_capabilities_map
    activities = (await db.execute(select(Activity).where(Activity.company_id == company_id, Activity.is_active.is_(True))
                                   .order_by(Activity.name))).scalars().all()
    capabilities = await module_capabilities_map(db, {a.module_id for a in activities})
    return [a for a in activities if "ORDERS" in capabilities.get(a.module_id, set())]


async def _check_header(db: AsyncSession, company_id: uuid.UUID, data: dict, creating: bool) -> dict:
    customer = (await db.execute(select(Customer).where(
        Customer.id == data.get("customer_id"), Customer.company_id == company_id))).scalar_one_or_none()
    if customer is None or not customer.is_active:
        raise CustomerOrderError("Escolha o cliente da encomenda")
    if customer.is_final_consumer:
        raise CustomerOrderError("Uma encomenda precisa de um cliente identificado (não o consumidor final): crie-o em Clientes")
    activities = await order_activities(db, company_id)
    activity = next((a for a in activities if a.id == data.get("activity_id")), None)
    if activity is None:
        if data.get("activity_id") or len(activities) != 1:
            raise CustomerOrderError("Escolha a atividade da encomenda" if activities
                                     else "Nenhuma atividade da empresa tem as Encomendas")
        activity = activities[0]
    delivery_at: datetime | None = data.get("delivery_at")
    if delivery_at is None:
        raise CustomerOrderError("Indique a data e a hora da entrega")
    if delivery_at.tzinfo is None:
        delivery_at = delivery_at.replace(tzinfo=LUANDA)
    if creating and delivery_at < datetime.now(LUANDA) - timedelta(minutes=5):
        raise CustomerOrderError("A data de entrega já passou")
    mode = (data.get("delivery_mode") or DELIVERY_PICKUP).upper()
    if mode not in (DELIVERY_PICKUP, DELIVERY_DELIVERY):
        raise CustomerOrderError("Modo de entrega inválido")
    address = " ".join((data.get("delivery_address") or "").split()) or None
    if mode == DELIVERY_DELIVERY and not address:
        raise CustomerOrderError("Indique a morada de entrega")
    return {
        "customer_id": customer.id, "activity_id": activity.id, "delivery_at": delivery_at, "delivery_mode": mode,
        "delivery_address": address if mode == DELIVERY_DELIVERY else None,
        "contact_name": " ".join((data.get("contact_name") or "").split())[:120] or None,
        "contact_phone": " ".join((data.get("contact_phone") or "").split())[:20] or None,
        "notes": (data.get("notes") or "").strip()[:1000] or None,
    }


async def _check_lines(db: AsyncSession, company_id: uuid.UUID, lines: list[dict], may_change_price: bool = True,
                       ) -> list[CustomerOrderLine]:
    if not lines:
        raise CustomerOrderError("A encomenda deve ter pelo menos um artigo")
    rates = dict((await db.execute(select(VAT.id, VAT.rate).where(VAT.company_id == company_id))).all())
    rows = []
    for position, line in enumerate(lines, start=1):
        product_id, service_id = line.get("product_id"), line.get("service_id")
        if bool(product_id) == bool(service_id):
            raise CustomerOrderError(f"Linha {position}: escolha um produto ou um serviço")
        if product_id:
            article = (await db.execute(select(Product).where(
                Product.id == product_id, Product.company_id == company_id, Product.is_active.is_(True),
                Product.is_raw_material.is_(False), Product.internal_use_only.is_(False)))).scalar_one_or_none()
        else:
            article = (await db.execute(select(Service).where(
                Service.id == service_id, Service.company_id == company_id, Service.is_active.is_(True)))).scalar_one_or_none()
        if article is None:
            raise CustomerOrderError(f"Linha {position}: artigo não encontrado ou inativo")
        try:
            quantity = float(line.get("quantity"))
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            raise CustomerOrderError(f"{article.name}: a quantidade deve ser maior que zero")
        catalogue = round(float(article.price or 0), 2)
        price = line.get("unit_price")
        price = catalogue if price is None else round(float(price), 2)
        if price < 0:
            raise CustomerOrderError(f"{article.name}: o preço não pode ser negativo")
        if price != catalogue and not may_change_price:
            raise CustomerOrderError(f"{article.name}: só o gestor pode alterar o preço do catálogo")
        rows.append(CustomerOrderLine(
            company_id=company_id, position=position, product_id=product_id if product_id else None,
            service_id=service_id if service_id else None, description=article.name[:255], quantity=quantity,
            unit_price=round(price, 2), vat_rate=float(rates.get(article.vat_id) or 0),
            production_note=(line.get("production_note") or "").strip()[:500] or None))
    return rows


async def get_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, lock: bool = False) -> CustomerOrder:
    query = select(CustomerOrder).where(CustomerOrder.id == order_id, CustomerOrder.company_id == company_id)
    if lock:
        query = query.with_for_update()
    order = (await db.execute(query)).scalar_one_or_none()
    if order is None:
        raise CustomerOrderNotFoundError("Encomenda não encontrada")
    return order


def _is_gestor(user) -> bool:
    role = getattr(user, "role", None)
    return user is None or (role.value if hasattr(role, "value") else str(role)) == "GESTOR"


async def create_order(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, data: dict, user=None) -> dict:
    """user: who registers it - only the gestor may change a catalogue price (None: the system, allowed)."""
    header = await _check_header(db, company_id, data, creating=True)
    lines = await _check_lines(db, company_id, data.get("lines") or [], may_change_price=_is_gestor(user))
    year = datetime.now(LUANDA).year  # numbered in the year it is ordered
    # the number: the next of the year, under a lock (two tills never take the same)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"orders:{company_id}:{year}"})
    last = (await db.execute(select(func.max(CustomerOrder.number)).where(
        CustomerOrder.company_id == company_id, CustomerOrder.year == year))).scalar_one()
    order = CustomerOrder(company_id=company_id, year=year, number=(last or 0) + 1, created_by_user_id=user_id,
                          status=CustomerOrderStatus.ENCOMENDADA, status_changed_at=datetime.now(LUANDA), **header)
    db.add(order)
    await db.flush()
    for row in lines:
        row.order_id = order.id
        db.add(row)
    await db.commit()
    return await order_detail(db, company_id, order.id)


def _same_line(old: CustomerOrderLine, new: CustomerOrderLine) -> bool:
    return (old.product_id, old.service_id, round(float(old.quantity), 3), round(float(old.unit_price), 2)) == \
        (new.product_id, new.service_id, round(float(new.quantity), 3), round(float(new.unit_price), 2))


async def update_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, data: dict, user=None) -> dict:
    order = await get_order(db, company_id, order_id, lock=True)
    if order.status not in EDITABLE:
        raise CustomerOrderError(f"A encomenda {reference(order)} está {STATUS_LABELS[order.status].lower()}: já não se altera")
    header = await _check_header(db, company_id, data, creating=False)
    existing = (await db.execute(select(CustomerOrderLine).where(CustomerOrderLine.order_id == order.id)
                                 .order_by(CustomerOrderLine.position))).scalars().all()
    lines = await _check_lines(db, company_id, data.get("lines") or [], may_change_price=True)
    if not _is_gestor(user):  # a price other than the catalogue's stays only if the gestor had agreed it already
        agreed = {(o.product_id, o.service_id, round(float(o.unit_price), 2)) for o in existing}
        for row in lines:
            if (row.product_id, row.service_id, round(float(row.unit_price), 2)) not in agreed:
                await _check_lines(db, company_id, [{"product_id": row.product_id, "service_id": row.service_id,
                                                     "quantity": 1, "unit_price": float(row.unit_price)}],
                                   may_change_price=False)
    if order.invoice_id is not None:
        # invoiced: its lines are those of the Fatura - only the notes, the delivery and the contact change
        if len(lines) != len(existing) or not all(_same_line(o, n) for o, n in zip(existing, lines)):
            raise CustomerOrderError(f"A encomenda {reference(order)} já está faturada: os artigos, as quantidades e "
                                     "os preços já não se alteram (cancele-a e registe outra)")
        for old, new in zip(existing, lines):
            old.production_note = new.production_note
        for key, value in header.items():
            if key != "customer_id" or value == order.customer_id:
                setattr(order, key, value)
        if header["customer_id"] != order.customer_id:
            raise CustomerOrderError("A encomenda já está faturada: o cliente já não se altera")
        await db.commit()
        return await order_detail(db, company_id, order.id)
    for key, value in header.items():
        setattr(order, key, value)
    for old in existing:
        await db.delete(old)
    await db.flush()
    for row in lines:
        row.order_id = order.id
        db.add(row)
    await db.commit()
    return await order_detail(db, company_id, order.id)


async def set_production_status(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, status: str) -> dict:
    order = await get_order(db, company_id, order_id, lock=True)
    try:
        target = CustomerOrderStatus(status)
    except ValueError:
        raise CustomerOrderError("Estado inválido")
    if target not in PRODUCTION_STEPS.get(order.status, set()):
        raise CustomerOrderError(
            f"A encomenda {reference(order)} está {STATUS_LABELS[order.status].lower()}: não pode passar a "
            f"{STATUS_LABELS[target].lower()}")
    order.status, order.status_changed_at = target, datetime.now(LUANDA)
    await db.commit()
    return await order_detail(db, company_id, order.id)


async def _invoice_of(db: AsyncSession, order: CustomerOrder):
    from app.models.invoice import Invoice
    from app.services.invoice_service import attach_amount_due
    if order.invoice_id is None:
        return None
    invoice = await db.get(Invoice, order.invoice_id)
    await attach_amount_due(db, [invoice])
    return invoice


async def cancel_info(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID) -> dict:
    """What cancelling asks: whether the order is invoiced, what was paid (a deposit to give back or keep), and the
    tills that can give cash back now."""
    from app.services.invoice_service import list_open_cash_points
    order = await get_order(db, company_id, order_id)
    invoice = await _invoice_of(db, order)
    return {"invoiced": invoice is not None, "paid": _money(invoice.amount_received) if invoice is not None else 0.0,
            "total": _money(invoice.total) if invoice is not None else None,
            "cash_points": await list_open_cash_points(db, company_id) if invoice is not None else []}


async def cancel_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, reason: str,
                       deposit: str | None = None, refund: dict | None = None, may_cancel_invoiced: bool = True) -> dict:
    """An order not invoiced is simply cancelled. Invoiced (may_cancel_invoiced: the gestor): its credit note is
    issued - deposit DEVOLVER (the whole FT credited, refund = {payment_method_id, pos_id | bank_account_id} for what
    was paid) or RETER (only the part not paid is credited; nothing paid: the whole FT)."""
    from app.models.invoice_line import InvoiceLine
    from app.services.invoice_service import create_credit_note
    order = await get_order(db, company_id, order_id, lock=True)
    reason = " ".join((reason or "").split())
    if len(reason) < 3:
        raise CustomerOrderError("Indique o motivo do cancelamento")
    if order.status not in OPEN:
        raise CustomerOrderError(f"A encomenda {reference(order)} está {STATUS_LABELS[order.status].lower()}: não se cancela")
    invoice = await _invoice_of(db, order)
    if invoice is not None:
        if not may_cancel_invoiced:
            raise CustomerOrderError(f"A encomenda {reference(order)} já está faturada: só o gestor a cancela "
                                     "(nota de crédito, valor pago devolvido ou retido)")
        paid = _money(invoice.amount_received)
        cash_due_total = float(invoice.total) - float(invoice.retention_total or 0)
        if paid > 0.005 and deposit not in ("DEVOLVER", "RETER"):
            raise CustomerOrderError(f"O cliente já pagou {_kz(paid)}: escolha se o valor pago é devolvido ou retido")
        keep = paid > 0.005 and deposit == "RETER"
        share = 1.0 if not keep else max(0.0, 1 - paid / cash_due_total) if cash_due_total > 0 else 0.0
        order_ref = reference(order)
        if share > 0.0005:
            lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
                                      .order_by(InvoiceLine.line_number))).scalars().all()
            refunds, refund_pos_id, refund_bank_id = [], None, None
            if paid > 0.005 and not keep:
                refund = refund or {}
                if not refund.get("payment_method_id"):
                    raise CustomerOrderError("Indique como o valor pago é devolvido (forma de pagamento)")
                refunds = [{"payment_method_id": refund["payment_method_id"], "amount": paid}]
                refund_pos_id, refund_bank_id = refund.get("pos_id"), refund.get("bank_account_id")
            try:
                note = await create_credit_note(
                    db, company_id, order.activity_id, invoice.id, "ANL",
                    f"Encomenda {order_ref} cancelada: {reason}"[:200],
                    [{"invoice_line_id": l.id, "quantity": round(float(l.quantity) * share, 3)} for l in lines],
                    restock=False,  # an order not delivered: its goods never left the stock
                    refunds=refunds, refund_pos_id=refund_pos_id, refund_bank_account_id=refund_bank_id,
                )
            except CustomerOrderError:
                raise
            except Exception as e:  # the invoicing's own refusal (period closed, refund impossible...), shown as is
                await db.rollback()
                raise CustomerOrderError(str(e) or "Não foi possível emitir a nota de crédito")
            order = await get_order(db, company_id, order_id, lock=True)
            order.credit_note_id = note.id
        order.deposit_outcome = None if paid <= 0.005 else ("RETIDO" if keep else "DEVOLVIDO")
    order.status, order.cancel_reason, order.status_changed_at = CustomerOrderStatus.CANCELADA, reason[:255], datetime.now(LUANDA)
    await db.commit()
    return await order_detail(db, company_id, order.id)


# ---------- The money, at a till of the order's activity

async def _till(db: AsyncSession, company_id: uuid.UUID, user, order: CustomerOrder, pos_id: uuid.UUID):
    from app.models.point_of_sale import PointOfSale
    from app.services.cash_session_service import get_open_session
    from app.services.user_cash_point_access_service import require_cash_point_access
    pos = (await db.execute(select(PointOfSale).where(PointOfSale.id == pos_id, PointOfSale.company_id == company_id))
           ).scalar_one_or_none()
    if pos is None:
        raise CustomerOrderError("Caixa não encontrada")
    if pos.activity_id != order.activity_id:
        raise CustomerOrderError("Esta encomenda pertence a outra atividade: receba-a numa caixa dessa atividade")
    await require_cash_point_access(db, company_id, user, pos.id)
    if await get_open_session(db, company_id, pos.id) is None:
        raise CustomerOrderError("Abra a caixa antes de receber")
    return pos


async def _sale_lines(db: AsyncSession, order: CustomerOrder) -> list[dict]:
    """The order's lines for its invoice, at the prices agreed: a product's own price when it differs from the
    catalogue (a free price, below the cost allowed: agreed by the gestor), a service's as given by the server."""
    lines = (await db.execute(select(CustomerOrderLine).where(CustomerOrderLine.order_id == order.id)
                              .order_by(CustomerOrderLine.position))).scalars().all()
    result = []
    for line in lines:
        price = round(float(line.unit_price), 2)
        if line.product_id is not None:
            product = await db.get(Product, line.product_id)
            entry = {"product_id": str(line.product_id), "service_id": None, "quantity": float(line.quantity),
                     "sale_unit_id": None}
            if product is not None and round(float(product.price or 0), 2) != price:
                entry.update({"free_price": price, "below_cost_ok": True})
        else:
            entry = {"product_id": None, "service_id": str(line.service_id), "quantity": float(line.quantity),
                     "sale_unit_id": None, "_resource_price": price}
        result.append(entry)
    return result


def _observations(order: CustomerOrder) -> str:
    when = order.delivery_at.astimezone(LUANDA).strftime("%d/%m/%Y %H:%M")
    how = f"entrega em {order.delivery_address}" if order.delivery_mode == DELIVERY_DELIVERY else "levantamento na loja"
    return f"Encomenda {reference(order)} - {how}, {when}"[:500]


async def _invoice_order(db: AsyncSession, company_id: uuid.UUID, user, order: CustomerOrder, pos, invoice_type: str,
                         payments: list[dict], terminal_id: uuid.UUID | None, deduct_stock: bool = True):
    from app.services.pos_service import checkout
    invoice = await checkout(db, company_id, pos.id, user, order.customer_id, await _sale_lines(db, order), payments,
                             invoice_type=invoice_type, observations=_observations(order), terminal_id=terminal_id,
                             deduct_stock=deduct_stock)
    order = await get_order(db, company_id, order.id, lock=True)
    order.invoice_id = invoice.id
    await db.commit()
    return order, invoice


async def _receive(db: AsyncSession, company_id: uuid.UUID, order: CustomerOrder, invoice, pos, amount: float,
                   payment_method_id: uuid.UUID, terminal_id: uuid.UUID | None):
    from app.services.invoice_service import create_receipt
    from app.services.payment_terminal_service import resolve_terminal
    terminal = await resolve_terminal(db, company_id, pos.id, [{"payment_method_id": payment_method_id, "amount": amount}],
                                      terminal_id)
    receipt = await create_receipt(
        db, company_id, order.activity_id, invoice.id, amount, observations=f"Encomenda {reference(order)}",
        payment_method_id=payment_method_id, cash_pos_id=pos.id,
        bank_account_id=terminal.bank_account_id if terminal is not None else None,
    )
    if terminal is not None:
        receipt.terminal_id = terminal.id
        await db.commit()
    return receipt


async def _goods_out(db: AsyncSession, company_id: uuid.UUID, order: CustomerOrder, invoice) -> None:
    """The goods of an order invoiced with its deposit leave the activity's warehouse at the delivery - the same
    movement as a sale, under its Fatura's reference (a product without stock control moves nothing). Not enough
    in stock: refused, nothing delivered (produce it first)."""
    from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
    from app.services.stock_service import InsufficientStockError, deduct_stock_for_sale
    activity = await db.get(Activity, order.activity_id)
    reference_text = f"{DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, 'FT')} {invoice.series}/{invoice.number}"
    lines = (await db.execute(select(CustomerOrderLine).where(
        CustomerOrderLine.order_id == order.id, CustomerOrderLine.product_id.is_not(None)))).scalars().all()
    try:
        for line in lines:
            await deduct_stock_for_sale(db, company_id=company_id, warehouse_id=activity.warehouse_id,
                                        product_id=line.product_id, quantity=float(line.quantity), reference=reference_text)
        await db.flush()
    except InsufficientStockError as e:
        await db.rollback()
        raise CustomerOrderError(f"{e} - registe a produção antes de entregar")


def _refused(e: Exception) -> CustomerOrderError:
    return e if isinstance(e, CustomerOrderError) else CustomerOrderError(str(e) or "Operação recusada")


async def pay_order(db: AsyncSession, company_id: uuid.UUID, user, order_id: uuid.UUID, pos_id: uuid.UUID,
                    amount: float, payment_method_id: uuid.UUID, terminal_id: uuid.UUID | None = None) -> dict:
    """A deposit (or the whole order paid in advance): its FT first if it has none, then a Recibo for the amount."""
    order = await get_order(db, company_id, order_id)
    if order.status not in OPEN:
        raise CustomerOrderError(f"A encomenda {reference(order)} está {STATUS_LABELS[order.status].lower()}")
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        raise CustomerOrderError("Indique o valor recebido")
    if not payment_method_id:
        raise CustomerOrderError("Escolha a forma de pagamento")
    pos = await _till(db, company_id, user, order, pos_id)
    try:
        invoice = await _invoice_of(db, order)
        if invoice is None:
            # the goods are handed over at the delivery: nothing leaves the stock now
            order, invoice = await _invoice_order(db, company_id, user, order, pos, "FACTURA", [], None, deduct_stock=False)
            invoice = await _invoice_of(db, order)
        if amount > float(invoice.amount_due) + 0.005:
            raise CustomerOrderError(f"O valor ({_kz(amount)}) é maior do que o que falta pagar ({_kz(invoice.amount_due)})")
        receipt = await _receive(db, company_id, order, invoice, pos, amount, payment_method_id, terminal_id)
    except Exception as e:
        raise _refused(e)
    detail = await order_detail(db, company_id, order.id)
    detail["document_id"] = receipt.id
    return detail


async def deliver_order(db: AsyncSession, company_id: uuid.UUID, user, order_id: uuid.UUID, pos_id: uuid.UUID,
                        payment_method_id: uuid.UUID | None = None, amount: float | None = None,
                        terminal_id: uuid.UUID | None = None, on_credit: bool = False) -> dict:
    """Handed over: what is still due is received (a Recibo; an order never invoiced: its Fatura/Recibo for amount),
    or left to be received (on_credit: a FT stays open)."""
    from app.services.document_rules import default_paid_on_issue_type
    order = await get_order(db, company_id, order_id)
    if order.status not in OPEN:
        raise CustomerOrderError(f"A encomenda {reference(order)} está {STATUS_LABELS[order.status].lower()}")
    pos = await _till(db, company_id, user, order, pos_id)
    document_id = None
    try:
        invoice = await _invoice_of(db, order)
        if invoice is None:
            if on_credit:
                order, invoice = await _invoice_order(db, company_id, user, order, pos, "FACTURA", [], None)
            else:
                if not payment_method_id:
                    raise CustomerOrderError("Escolha a forma de pagamento")
                order, invoice = await _invoice_order(
                    db, company_id, user, order, pos, await default_paid_on_issue_type(db),
                    [{"payment_method_id": str(payment_method_id), "amount": float(amount or 0)}], terminal_id)
            document_id = invoice.id
        else:
            if float(invoice.amount_due) > 0.005 and not on_credit and not payment_method_id:
                raise CustomerOrderError("Escolha a forma de pagamento")
            await _goods_out(db, company_id, order, invoice)  # invoiced with its deposit: the goods leave now
            if float(invoice.amount_due) > 0.005 and not on_credit:
                receipt = await _receive(db, company_id, order, invoice, pos, round(float(invoice.amount_due), 2),
                                         payment_method_id, terminal_id)
                document_id = receipt.id
    except Exception as e:
        raise _refused(e)
    order = await get_order(db, company_id, order_id, lock=True)
    order.status, order.status_changed_at = CustomerOrderStatus.ENTREGUE, datetime.now(LUANDA)
    await db.commit()
    detail = await order_detail(db, company_id, order.id)
    detail["document_id"] = document_id
    return detail


def _totals(lines) -> dict:
    subtotal = sum(_money(float(l.quantity) * float(l.unit_price)) for l in lines)
    vat = sum(_money(float(l.quantity) * float(l.unit_price) * float(l.vat_rate) / 100) for l in lines)
    return {"subtotal": _money(subtotal), "vat": _money(vat), "total": _money(subtotal + vat)}


def _line_dict(line: CustomerOrderLine) -> dict:
    return {"id": line.id, "position": line.position, "product_id": line.product_id, "service_id": line.service_id,
            "description": line.description, "quantity": float(line.quantity), "unit_price": _money(line.unit_price),
            "vat_rate": float(line.vat_rate), "production_note": line.production_note,
            "total": _money(float(line.quantity) * float(line.unit_price) * (1 + float(line.vat_rate) / 100))}


def _money_dict(order: CustomerOrder, invoice, credit_note_ref: str | None) -> dict:
    if invoice is None:
        return {"invoice_id": None, "invoice_reference": None, "paid": 0.0, "due": None, "credit_note_reference": None,
                "deposit_outcome": order.deposit_outcome}
    return {"invoice_id": invoice.id, "invoice_reference": f"{invoice.series}/{invoice.number}",  # the series names its type
            "paid": _money(invoice.amount_received), "due": _money(getattr(invoice, "amount_due", 0)),
            "credit_note_reference": credit_note_ref, "deposit_outcome": order.deposit_outcome}


def _order_dict(order: CustomerOrder, customer: Customer | None, activity_name: str | None, lines,
                money: dict | None = None) -> dict:
    return {**(money or _money_dict(order, None, None)),
        "id": order.id, "reference": reference(order), "status": order.status.value,
        "status_label": STATUS_LABELS[order.status], "activity_id": order.activity_id, "activity_name": activity_name,
        "customer_id": order.customer_id, "customer_name": customer.name if customer else None,
        "customer_nif": customer.nif if customer else None, "customer_phone": customer.phone_number if customer else None,
        "contact_name": order.contact_name, "contact_phone": order.contact_phone, "delivery_at": order.delivery_at,
        "delivery_mode": order.delivery_mode, "delivery_address": order.delivery_address, "notes": order.notes,
        "cancel_reason": order.cancel_reason, "created_at": order.created_at, "editable": order.status in EDITABLE,
        "lines_locked": order.invoice_id is not None,
        "lines": [_line_dict(l) for l in lines], **_totals(lines),
    }


async def order_detail(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID) -> dict:
    order = await get_order(db, company_id, order_id)
    customer = await db.get(Customer, order.customer_id)
    activity = await db.get(Activity, order.activity_id)
    lines = (await db.execute(select(CustomerOrderLine).where(CustomerOrderLine.order_id == order.id)
                              .order_by(CustomerOrderLine.position))).scalars().all()
    money = (await _money_of(db, [order]))[order.id]
    return _order_dict(order, customer, activity.name if activity else None, lines, money)


async def _money_of(db: AsyncSession, orders: list[CustomerOrder]) -> dict:
    from app.models.invoice import Invoice
    from app.services.invoice_service import attach_amount_due
    ids = {o.invoice_id for o in orders if o.invoice_id} | {o.credit_note_id for o in orders if o.credit_note_id}
    invoices = {i.id: i for i in (await db.execute(select(Invoice).where(Invoice.id.in_(ids)))).scalars().all()} if ids else {}
    await attach_amount_due(db, [invoices[o.invoice_id] for o in orders if o.invoice_id in invoices])
    result = {}
    for o in orders:
        note = invoices.get(o.credit_note_id)
        result[o.id] = _money_dict(o, invoices.get(o.invoice_id), f"{note.series}/{note.number}" if note else None)
    return result


async def list_orders(db: AsyncSession, company_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
                      status: str | None = None, search: str | None = None, customer_id: uuid.UUID | None = None,
                      activity_id: uuid.UUID | None = None) -> list[dict]:
    """The orders by delivery date (soonest first); «ABERTAS» = not delivered nor cancelled, whatever their date."""
    query = select(CustomerOrder).where(CustomerOrder.company_id == company_id)
    if date_from:
        query = query.where(CustomerOrder.delivery_at >= datetime.combine(date_from, time.min, LUANDA))
    if date_to:
        query = query.where(CustomerOrder.delivery_at < datetime.combine(date_to + timedelta(days=1), time.min, LUANDA))
    if status == "ABERTAS":
        query = query.where(CustomerOrder.status.in_(OPEN))
    elif status:
        try:
            query = query.where(CustomerOrder.status == CustomerOrderStatus(status))
        except ValueError:
            raise CustomerOrderError("Estado inválido")
    if customer_id:
        query = query.where(CustomerOrder.customer_id == customer_id)
    if activity_id:
        query = query.where(CustomerOrder.activity_id == activity_id)
    search = " ".join((search or "").split())
    if search:
        pattern = f"%{search}%"
        matching = select(Customer.id).where(Customer.company_id == company_id,
                                             or_(Customer.name.ilike(pattern), Customer.nif == search,
                                                 Customer.phone_number.ilike(pattern)))
        query = query.where(or_(CustomerOrder.customer_id.in_(matching), CustomerOrder.contact_name.ilike(pattern),
                                CustomerOrder.contact_phone.ilike(pattern)))
    orders = (await db.execute(query.order_by(CustomerOrder.delivery_at, CustomerOrder.number).limit(500))).scalars().all()
    if not orders:
        return []
    customers = {c.id: c for c in (await db.execute(select(Customer).where(
        Customer.id.in_({o.customer_id for o in orders})))).scalars().all()}
    activities = dict((await db.execute(select(Activity.id, Activity.name).where(
        Activity.id.in_({o.activity_id for o in orders})))).all())
    lines: dict = {}
    for line in (await db.execute(select(CustomerOrderLine).where(CustomerOrderLine.order_id.in_([o.id for o in orders]))
                                  .order_by(CustomerOrderLine.position))).scalars().all():
        lines.setdefault(line.order_id, []).append(line)
    money = await _money_of(db, list(orders))
    return [_order_dict(o, customers.get(o.customer_id), activities.get(o.activity_id), lines.get(o.id, []), money[o.id])
            for o in orders]


async def order_options(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """What the order form offers: the activities with Encomendas, the identified customers, the articles that sell
    (products and services, with their price without VAT and their rate)."""
    rates = dict((await db.execute(select(VAT.id, VAT.rate).where(VAT.company_id == company_id))).all())
    customers = (await db.execute(select(Customer).where(
        Customer.company_id == company_id, Customer.is_active.is_(True), Customer.is_final_consumer.is_(False))
        .order_by(Customer.name))).scalars().all()
    products = (await db.execute(select(Product).where(
        Product.company_id == company_id, Product.is_active.is_(True), Product.is_raw_material.is_(False),
        Product.internal_use_only.is_(False)).order_by(Product.name))).scalars().all()
    services = (await db.execute(select(Service).where(Service.company_id == company_id, Service.is_active.is_(True))
                                 .order_by(Service.name))).scalars().all()
    return {
        "activities": [{"id": a.id, "name": a.name} for a in await order_activities(db, company_id)],
        "customers": [{"id": c.id, "name": c.name, "nif": c.nif, "phone_number": c.phone_number} for c in customers],
        "articles": [{"kind": "product", "id": p.id, "code": p.code, "name": p.name, "price": _money(p.price),
                      "vat_rate": float(rates.get(p.vat_id) or 0)} for p in products]
                    + [{"kind": "service", "id": s.id, "code": s.code, "name": s.name, "price": _money(s.price),
                        "vat_rate": float(rates.get(s.vat_id) or 0)} for s in services],
    }
