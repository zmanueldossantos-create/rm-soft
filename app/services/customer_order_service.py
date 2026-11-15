"""
Encomendas (capability ORDERS): a customer's order to be made and handed over later. This step keeps the order itself
- who, when, how it is delivered, what (with a production note per line) and where it stands; the money (FT + Recibo
for a deposit, Recibo or FR at the delivery, NC when cancelled after its FT) comes in the next step, through the till.

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


async def _check_lines(db: AsyncSession, company_id: uuid.UUID, lines: list[dict]) -> list[CustomerOrderLine]:
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
        price = line.get("unit_price")
        price = float(article.price or 0) if price is None else float(price)
        if price < 0:
            raise CustomerOrderError(f"{article.name}: o preço não pode ser negativo")
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


async def create_order(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, data: dict) -> dict:
    header = await _check_header(db, company_id, data, creating=True)
    lines = await _check_lines(db, company_id, data.get("lines") or [])
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


async def update_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, data: dict) -> dict:
    order = await get_order(db, company_id, order_id, lock=True)
    if order.status not in EDITABLE:
        raise CustomerOrderError(f"A encomenda {reference(order)} está {STATUS_LABELS[order.status].lower()}: já não se altera")
    header = await _check_header(db, company_id, data, creating=False)
    lines = await _check_lines(db, company_id, data.get("lines") or [])
    for key, value in header.items():
        setattr(order, key, value)
    for old in (await db.execute(select(CustomerOrderLine).where(CustomerOrderLine.order_id == order.id))).scalars().all():
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


async def cancel_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, reason: str) -> dict:
    order = await get_order(db, company_id, order_id, lock=True)
    reason = " ".join((reason or "").split())
    if len(reason) < 3:
        raise CustomerOrderError("Indique o motivo do cancelamento")
    if order.status not in OPEN:
        raise CustomerOrderError(f"A encomenda {reference(order)} está {STATUS_LABELS[order.status].lower()}: não se cancela")
    order.status, order.cancel_reason, order.status_changed_at = CustomerOrderStatus.CANCELADA, reason[:255], datetime.now(LUANDA)
    await db.commit()
    return await order_detail(db, company_id, order.id)


def _totals(lines) -> dict:
    subtotal = sum(_money(float(l.quantity) * float(l.unit_price)) for l in lines)
    vat = sum(_money(float(l.quantity) * float(l.unit_price) * float(l.vat_rate) / 100) for l in lines)
    return {"subtotal": _money(subtotal), "vat": _money(vat), "total": _money(subtotal + vat)}


def _line_dict(line: CustomerOrderLine) -> dict:
    return {"id": line.id, "position": line.position, "product_id": line.product_id, "service_id": line.service_id,
            "description": line.description, "quantity": float(line.quantity), "unit_price": _money(line.unit_price),
            "vat_rate": float(line.vat_rate), "production_note": line.production_note,
            "total": _money(float(line.quantity) * float(line.unit_price) * (1 + float(line.vat_rate) / 100))}


def _order_dict(order: CustomerOrder, customer: Customer | None, activity_name: str | None, lines) -> dict:
    return {
        "id": order.id, "reference": reference(order), "status": order.status.value,
        "status_label": STATUS_LABELS[order.status], "activity_id": order.activity_id, "activity_name": activity_name,
        "customer_id": order.customer_id, "customer_name": customer.name if customer else None,
        "customer_nif": customer.nif if customer else None, "customer_phone": customer.phone_number if customer else None,
        "contact_name": order.contact_name, "contact_phone": order.contact_phone, "delivery_at": order.delivery_at,
        "delivery_mode": order.delivery_mode, "delivery_address": order.delivery_address, "notes": order.notes,
        "cancel_reason": order.cancel_reason, "created_at": order.created_at, "editable": order.status in EDITABLE,
        "lines": [_line_dict(l) for l in lines], **_totals(lines),
    }


async def order_detail(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID) -> dict:
    order = await get_order(db, company_id, order_id)
    customer = await db.get(Customer, order.customer_id)
    activity = await db.get(Activity, order.activity_id)
    lines = (await db.execute(select(CustomerOrderLine).where(CustomerOrderLine.order_id == order.id)
                              .order_by(CustomerOrderLine.position))).scalars().all()
    return _order_dict(order, customer, activity.name if activity else None, lines)


async def list_orders(db: AsyncSession, company_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
                      status: str | None = None, search: str | None = None, customer_id: uuid.UUID | None = None) -> list[dict]:
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
    return [_order_dict(o, customers.get(o.customer_id), activities.get(o.activity_id), lines.get(o.id, [])) for o in orders]


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
