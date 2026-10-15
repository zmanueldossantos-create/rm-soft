"""
Guias - the documents that travel with the goods (GoodsMovement; SAF-T MovementOfGoods): GR to a customer, GT between
two warehouses of the company, GD back to a supplier. Issued like an invoice: the document type's AGT series of the
year, the next number, a hash and an ATCUD (simulated until the AGT homologation, like the invoices), on a day of an
OPEN period (a fiscal document).

The stock moves with the guide, in the same transaction: GR and GD take the goods out of the loading warehouse, GT
transfers them to the destination warehouse - each ledger row carries the guide's number. A line is entered in one of
the product's units (2 SC = 40 KG). Prices: a GR at the sale price of the unit with the product's VAT (what the invoice
will charge); a GT or a GD at the current cost of the goods, without VAT.

Cancelling (with a reason) puts the stock back - the goods came back; an invoiced GR is never cancelled.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.customer import Customer, CustomerStatus
from app.models.document_type import DocumentType
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.goods_movement import GoodsMovement, GoodsMovementLine, GoodsMovementStatus
from app.models.product import Product
from app.models.purchase_invoice import PurchaseInvoice
from app.models.stock_movement import MovementType, StockMovement
from app.models.supplier import Supplier
from app.models.user import User
from app.models.vat import VAT
from app.models.warehouse import Warehouse
from app.services.document_series_service import SeriesNotFoundError, get_next_number, get_or_create_current_series
from app.services.fiscal_period_service import ensure_period_open
from app.services.invoice_service import _exemption_for, _simulate_atcud, _simulate_hash
from app.services.product_sale_unit_service import SaleUnitInvalidError, resolve_line_unit
from app.services.stock_service import InsufficientStockError, _get_or_create_stock_row, _stock_rule, ensure_available_at_period_end

MOVEMENT_TYPES = {"GR": "Guia de Remessa", "GT": "Guia de Transporte", "GD": "Guia de Devolução"}
# A customer in one of these states receives no goods
BLOCKED_CUSTOMER = {CustomerStatus.BLOQUEADO, CustomerStatus.ELIMINADO, CustomerStatus.INACTIVO, CustomerStatus.SUSPENSO}


class GoodsMovementError(Exception):
    """A guide that cannot be issued or changed as asked (the message says why)."""


class GoodsMovementNotFoundError(Exception):
    pass


def _money(value: float) -> float:
    return round(value + 0.0, 2)


def reference(movement: GoodsMovement) -> str:
    """The guide's number as the SAF-T writes it: GR GR2026/1."""
    return f"{movement.movement_type} {movement.series}/{movement.number}"


async def _warehouse(db: AsyncSession, company_id: uuid.UUID, warehouse_id, label: str) -> Warehouse:
    warehouse = (await db.execute(select(Warehouse).where(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id))).scalar_one_or_none() if warehouse_id else None
    if warehouse is None or not warehouse.is_active:
        raise GoodsMovementError(f"Escolha o armazém de {label}")
    return warehouse


async def _move(db: AsyncSession, company_id: uuid.UUID, period: FiscalPeriod, product: Product, quantity: float,
                origin_id: uuid.UUID, destination_id: uuid.UUID | None, ref: str, back: bool = False) -> None:
    """
    The stock of one line, in base units: out of the origin (GR, GD), or from the origin to the destination (GT).
    back=True undoes it (a cancellation): the goods come back to the origin. A product without stock moves nothing.
    """
    if not product.managed_by_stock:
        return
    out_id, in_id = (destination_id, origin_id) if back else (origin_id, destination_id)
    if out_id is not None:  # the goods leave a warehouse: its rules and its stock (at the period's end, a late entry)
        await _stock_rule(db, product.id, out_id, "out", strict=True)
        await ensure_available_at_period_end(db, company_id, period, product.id, out_id, quantity, GoodsMovementError)
        stock = await _get_or_create_stock_row(db, company_id, product.id, out_id)
        if float(stock.quantity) < quantity:
            raise GoodsMovementError(f"Stock insuficiente para {product.name} (disponível: {float(stock.quantity):g})")
        stock.quantity = float(stock.quantity) - quantity
    if in_id is not None:
        await _stock_rule(db, product.id, in_id, "in", strict=True)
        stock = await _get_or_create_stock_row(db, company_id, product.id, in_id)
        stock.quantity = float(stock.quantity) + quantity
    reason = ("Anulação da " if back else "") + ref
    common = dict(company_id=company_id, fiscal_period_id=period.id, product_id=product.id, quantity=quantity,
                  reason=reason, reference=ref)
    if out_id is not None and in_id is not None:  # a transfer: the pair of the ledger
        db.add(StockMovement(**common, warehouse_id=out_id, movement_type=MovementType.TRANSFERENCIA,
                             counterpart_warehouse_id=in_id, is_transfer_source=True))
        db.add(StockMovement(**common, warehouse_id=in_id, movement_type=MovementType.TRANSFERENCIA,
                             counterpart_warehouse_id=out_id, is_transfer_source=False))
    elif out_id is not None:
        db.add(StockMovement(**common, warehouse_id=out_id, movement_type=MovementType.SAIDA))
    else:
        db.add(StockMovement(**common, warehouse_id=in_id, movement_type=MovementType.RECEPCAO))


async def _build_lines(db: AsyncSession, company_id: uuid.UUID, period: FiscalPeriod, movement_type: str,
                       lines: list[dict], origin: Warehouse, destination: Warehouse | None, ref: str) -> tuple[list, float, float]:
    """The lines of a guide (in the unit entered), their prices and VAT, and the stock they move."""
    rows, net_total, vat_total = [], 0.0, 0.0
    for position, line in enumerate(lines, start=1):
        quantity = float(line.get("quantity") or 0)
        if quantity <= 0:
            raise GoodsMovementError(f"Linha {position}: a quantidade deve ser maior que zero")
        product = (await db.execute(select(Product).where(
            Product.id == line.get("product_id"), Product.company_id == company_id))).scalar_one_or_none()
        if product is None:
            raise GoodsMovementError(f"Linha {position}: produto não encontrado")
        try:
            sale_price, factor, sale_unit_id, unit_code = await resolve_line_unit(
                db, company_id, product, line.get("sale_unit_id"), quantity)
        except SaleUnitInvalidError as e:
            raise GoodsMovementError(f"Linha {position}: {e}")
        if movement_type == "GR" and product.is_raw_material:  # never sold, so never sent to a customer
            raise GoodsMovementError(f"Linha {position}: {product.name} é uma matéria-prima - não pode ser enviada a um cliente")
        if movement_type == "GR":  # what the invoice will charge: the unit's sale price and the product's VAT
            vat = (await db.execute(select(VAT).where(VAT.id == product.vat_id))).scalar_one_or_none() if product.vat_id else None
            vat_rate, tax_code = (float(vat.rate), vat.tax_category) if vat else (0.0, "ISE")
            exemption_code, exemption_reason = await _exemption_for(db, product, tax_code)
            proposed = sale_price
        else:  # goods carried or returned: at their current cost, without VAT
            vat_rate, tax_code, exemption_code, exemption_reason = 0.0, "NS", None, None
            proposed = float(product.average_cost or product.purchase_price or 0) * factor
        unit_price = float(line["unit_price"]) if line.get("unit_price") not in (None, "") else proposed
        if unit_price < 0:
            raise GoodsMovementError(f"Linha {position}: o preço não pode ser negativo")
        line_net = _money(quantity * unit_price)
        line_vat = _money(line_net * vat_rate / 100)
        net_total += line_net
        vat_total += line_vat
        await _move(db, company_id, period, product, quantity * factor, origin.id,
                    destination.id if destination else None, ref)
        rows.append(GoodsMovementLine(
            position=position, product_id=product.id, product_code=product.code, description=product.name[:255],
            sale_unit_id=sale_unit_id, unit_code=unit_code, unit_factor=factor, quantity=quantity,
            unit_price=_money(unit_price), vat_rate=vat_rate, tax_code=tax_code, exemption_code=exemption_code,
            exemption_reason=exemption_reason, line_net=line_net, line_vat=line_vat,
        ))
    return rows, net_total, vat_total

async def create_goods_movement(
    db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, movement_type: str, origin_warehouse_id: uuid.UUID,
    lines: list[dict], start_time: datetime | None = None, customer_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None, purchase_invoice_id: uuid.UUID | None = None,
    destination_warehouse_id: uuid.UUID | None = None, load_address: str | None = None,
    unload_address: str | None = None, vehicle_plate: str | None = None, notes: str | None = None,
) -> GoodsMovement:
    """lines: [{product_id, sale_unit_id, quantity, unit_price}] - unit_price optional (the proposed one)."""
    if movement_type not in MOVEMENT_TYPES:
        raise GoodsMovementError("Tipo de guia inválido")
    if not lines:
        raise GoodsMovementError("A guia deve ter pelo menos uma linha")
    today = date.today()
    await ensure_period_open(db, company_id, today)  # a fiscal document: issued in an open period
    period = (await db.execute(
        select(FiscalPeriod).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.company_id == company_id, FiscalYear.year == today.year, FiscalPeriod.month == today.month)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    start_time = start_time or now
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if (now - start_time).total_seconds() > 300:  # a few minutes of tolerance for the clock
        raise GoodsMovementError("O início do transporte não pode ser anterior à emissão da guia")

    origin = await _warehouse(db, company_id, origin_warehouse_id, "carga")
    destination, customer, supplier = None, None, None
    if movement_type == "GR":
        customer = (await db.execute(select(Customer).where(
            Customer.id == customer_id, Customer.company_id == company_id))).scalar_one_or_none() if customer_id else None
        if customer is None:
            raise GoodsMovementError("Escolha o cliente da guia de remessa")
        if not customer.is_active or customer.status in BLOCKED_CUSTOMER:
            raise GoodsMovementError(f"O cliente {customer.name} está {customer.status.value.lower()} - não pode receber mercadoria")
        default_unload = customer.address
    elif movement_type == "GT":
        destination = await _warehouse(db, company_id, destination_warehouse_id, "descarga")
        if destination.id == origin.id:
            raise GoodsMovementError("O armazém de descarga deve ser diferente do armazém de carga")
        default_unload = destination.address or destination.name
    else:
        supplier = (await db.execute(select(Supplier).where(
            Supplier.id == supplier_id, Supplier.company_id == company_id))).scalar_one_or_none() if supplier_id else None
        if supplier is None:
            raise GoodsMovementError("Escolha o fornecedor a quem a mercadoria é devolvida")
        if purchase_invoice_id is not None and (await db.execute(select(PurchaseInvoice.id).where(
                PurchaseInvoice.id == purchase_invoice_id, PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.supplier_id == supplier.id))).scalar_one_or_none() is None:
            raise GoodsMovementError("A fatura de compra indicada não é deste fornecedor")
        default_unload = supplier.address
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
    load_address = " ".join((load_address or origin.address or company.address or origin.name).split())[:250]
    unload_address = " ".join((unload_address or default_unload or "").split())[:250]
    if not unload_address:
        raise GoodsMovementError("Indique o local de descarga")

    doc_type = (await db.execute(select(DocumentType).where(DocumentType.code == movement_type))).scalar_one_or_none()
    if doc_type is None or not doc_type.is_active:
        raise GoodsMovementError(f"O tipo de documento {movement_type} não está ativo no catálogo")
    try:
        series_row = await get_or_create_current_series(db, company, doc_type.id)
    except SeriesNotFoundError as e:
        raise GoodsMovementError(str(e))
    number = await get_next_number(db, series_row)
    ref = f"{movement_type} {series_row.series_code}/{number}"

    try:  # the number, the stock and the guide stand or fall together
        rows, net_total, vat_total = await _build_lines(db, company_id, period, movement_type, lines, origin,
                                                        destination, ref)
    except (GoodsMovementError, InsufficientStockError) as e:
        await db.rollback()
        raise GoodsMovementError(str(e))
    except Exception:  # an article without its VAT rule or exemption motive...: nothing is kept
        await db.rollback()
        raise
    gross = _money(net_total + vat_total)
    movement = GoodsMovement(
        company_id=company_id, document_type_id=doc_type.id, movement_type=movement_type, series=series_row.series_code,
        number=number, fiscal_period_id=period.id, movement_date=today, start_time=start_time,
        customer_id=customer.id if customer else None, supplier_id=supplier.id if supplier else None,
        purchase_invoice_id=purchase_invoice_id if supplier else None, origin_warehouse_id=origin.id,
        destination_warehouse_id=destination.id if destination else None, load_address=load_address,
        unload_address=unload_address, vehicle_plate=(" ".join((vehicle_plate or "").split()).upper() or None),
        notes=(notes or None), net_total=_money(net_total), vat_total=_money(vat_total), gross_total=gross,
        atcud=_simulate_atcud(company_id, series_row.series_code, number),
        document_hash=_simulate_hash(company_id, series_row.series_code, number, gross, today),
        status=GoodsMovementStatus.EMITIDA, created_by_user_id=user_id,
    )
    db.add(movement)
    await db.flush()
    for row in rows:
        row.goods_movement_id = movement.id
        db.add(row)
    await db.commit()
    await db.refresh(movement)
    return movement


async def _get(db: AsyncSession, company_id: uuid.UUID, movement_id: uuid.UUID) -> GoodsMovement:
    movement = (await db.execute(select(GoodsMovement).where(
        GoodsMovement.id == movement_id, GoodsMovement.company_id == company_id))).scalar_one_or_none()
    if movement is None:
        raise GoodsMovementNotFoundError("Guia não encontrada")
    return movement


async def cancel_goods_movement(db: AsyncSession, company_id: uuid.UUID, movement_id: uuid.UUID, user_id: uuid.UUID,
                                reason: str) -> GoodsMovement:
    """Cancelled with its reason: the goods come back (into the period open today); an invoiced GR never is."""
    movement = await _get(db, company_id, movement_id)
    if movement.status == GoodsMovementStatus.ANULADA:
        raise GoodsMovementError("Esta guia já está anulada")
    if movement.status == GoodsMovementStatus.FATURADA:
        raise GoodsMovementError("Esta guia já foi faturada - anule primeiro a fatura com uma nota de crédito")
    reason = " ".join((reason or "").split())
    if not reason:
        raise GoodsMovementError("Indique o motivo da anulação")
    today = date.today()
    await ensure_period_open(db, company_id, today)
    period = (await db.execute(
        select(FiscalPeriod).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.company_id == company_id, FiscalYear.year == today.year, FiscalPeriod.month == today.month)
    )).scalar_one()
    lines = (await db.execute(select(GoodsMovementLine).where(GoodsMovementLine.goods_movement_id == movement.id))).scalars().all()
    ref = reference(movement)
    try:
        for line in lines:
            product = (await db.execute(select(Product).where(Product.id == line.product_id))).scalar_one()
            await _move(db, company_id, period, product, float(line.quantity) * float(line.unit_factor),
                        movement.origin_warehouse_id, movement.destination_warehouse_id, ref, back=True)
    except (GoodsMovementError, InsufficientStockError) as e:
        await db.rollback()
        raise GoodsMovementError(f"Não é possível anular: {e}")
    movement.status = GoodsMovementStatus.ANULADA
    movement.cancel_reason = reason[:300]
    movement.cancelled_at = datetime.now(timezone.utc)
    movement.cancelled_by_user_id = user_id
    await db.commit()
    await db.refresh(movement)
    return movement


async def invoice_goods_movements(db: AsyncSession, company_id: uuid.UUID, movement_ids: list[uuid.UUID],
                                  activity_id: uuid.UUID):
    """
    Invoices one or several guias de remessa of the same customer in ONE Fatura (FT) of the given activity - paid later
    with a receipt, like any FT (a FR would need the cash point where the money enters, chosen on the invoicing screen): the
    lines of each GR, in its unit and at its price, each naming its GR (SAF-T OrderReferences); the goods already left
    the stock with the guides, so the invoice does not take them out again. Every GR becomes FATURADA with the invoice
    - all in one transaction: a guide invoiced twice is impossible.
    """
    from app.models.invoice import Invoice
    from app.services import invoice_service
    from app.workers.agt_worker import submit_invoice_to_agt
    ids = list(dict.fromkeys(movement_ids or []))
    if not ids:
        raise GoodsMovementError("Escolha as guias de remessa a faturar")
    movements = (await db.execute(select(GoodsMovement).where(
        GoodsMovement.id.in_(ids), GoodsMovement.company_id == company_id)
        .order_by(GoodsMovement.series, GoodsMovement.number).with_for_update())).scalars().all()
    if len(movements) != len(ids):
        raise GoodsMovementNotFoundError("Guia não encontrada")
    for m in movements:
        if m.movement_type != "GR":
            raise GoodsMovementError(f"{reference(m)}: só uma guia de remessa é faturada")
        if m.status != GoodsMovementStatus.EMITIDA:
            state = "já faturada" if m.status == GoodsMovementStatus.FATURADA else "anulada"
            raise GoodsMovementError(f"{reference(m)} está {state}")
    if len({m.customer_id for m in movements}) > 1:
        raise GoodsMovementError("As guias de uma fatura devem ser do mesmo cliente")
    customer = (await db.execute(select(Customer).where(Customer.id == movements[0].customer_id))).scalar_one()
    if not customer.is_active or customer.status in BLOCKED_CUSTOMER:
        raise GoodsMovementError(f"O cliente {customer.name} está {customer.status.value.lower()} - não pode ser faturado")

    lines = (await db.execute(select(GoodsMovementLine).where(GoodsMovementLine.goods_movement_id.in_(ids)))).scalars().all()
    order = {m.id: i for i, m in enumerate(movements)}
    lines_input = [{
        "product_id": l.product_id, "sale_unit_id": l.sale_unit_id, "quantity": float(l.quantity),
        "unit_price": float(l.unit_price), "goods_movement_id": l.goods_movement_id,
    } for l in sorted(lines, key=lambda l: (order[l.goods_movement_id], l.position))]
    refs = ", ".join(reference(m) for m in movements)
    try:
        invoice = await invoice_service.create_invoice(
            db, company_id=company_id, activity_id=activity_id, customer_id=customer.id, invoice_type="FACTURA",
            lines_input=lines_input, payment_term_id=customer.payment_term_id, payment_method_id=customer.payment_method_id,
            document_reference=(("Guias: " if len(movements) > 1 else "Guia: ") + refs)[:255],
            deduct_stock=False, commit=False,
        )
    except (invoice_service.ActivityNotFoundError, invoice_service.EmptyInvoiceError, invoice_service.ProductNotFoundError,
            invoice_service.SeriesNotConfiguredError, invoice_service.DocumentTypeNotConfiguredError,
            invoice_service.PaymentAmountMismatchError, invoice_service.PaymentMethodNotAllowedError,
            invoice_service.CashPointRequiredError, invoice_service.MissingExemptionReasonError) as e:
        await db.rollback()
        raise GoodsMovementError(str(e))
    except Exception:
        await db.rollback()
        raise
    for m in movements:
        m.status = GoodsMovementStatus.FATURADA
        m.invoice_id = invoice.id
    await db.commit()
    invoice = (await db.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    submit_invoice_to_agt.delay(str(invoice.id))  # a fiscal invoice: sent to the AGT like any other
    return invoice


async def _names(db: AsyncSession, model, ids) -> dict:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    return dict((await db.execute(select(model.id, model.name).where(model.id.in_(ids)))).all())


def _summary(m: GoodsMovement, names: dict) -> dict:
    party = names["customers"].get(m.customer_id) or names["suppliers"].get(m.supplier_id) \
        or names["warehouses"].get(m.destination_warehouse_id)
    return {
        "id": m.id, "customer_id": m.customer_id, "movement_type": m.movement_type, "type_label": MOVEMENT_TYPES[m.movement_type],
        "reference": reference(m), "status": m.status.value, "movement_date": m.movement_date, "start_time": m.start_time,
        "party": party, "origin_warehouse": names["warehouses"].get(m.origin_warehouse_id),
        "net_total": float(m.net_total), "vat_total": float(m.vat_total), "gross_total": float(m.gross_total),
        "vehicle_plate": m.vehicle_plate,
    }


async def _all_names(db: AsyncSession, movements) -> dict:
    return {
        "customers": await _names(db, Customer, {m.customer_id for m in movements}),
        "suppliers": await _names(db, Supplier, {m.supplier_id for m in movements}),
        "warehouses": await _names(db, Warehouse, {w for m in movements for w in (m.origin_warehouse_id, m.destination_warehouse_id)}),
    }


async def list_goods_movements(db: AsyncSession, company_id: uuid.UUID, movement_type: str | None = None,
                               status: str | None = None, date_from: date | None = None,
                               date_to: date | None = None) -> list[dict]:
    query = select(GoodsMovement).where(GoodsMovement.company_id == company_id)
    if movement_type:
        query = query.where(GoodsMovement.movement_type == movement_type)
    if status:
        query = query.where(GoodsMovement.status == GoodsMovementStatus(status))
    if date_from:
        query = query.where(GoodsMovement.movement_date >= date_from)
    if date_to:
        query = query.where(GoodsMovement.movement_date <= date_to)
    movements = (await db.execute(query.order_by(GoodsMovement.created_at.desc()))).scalars().all()
    names = await _all_names(db, movements)
    return [_summary(m, names) for m in movements]


async def get_goods_movement(db: AsyncSession, company_id: uuid.UUID, movement_id: uuid.UUID) -> dict:
    movement = await _get(db, company_id, movement_id)
    names = await _all_names(db, [movement])
    lines = (await db.execute(select(GoodsMovementLine).where(GoodsMovementLine.goods_movement_id == movement.id)
                              .order_by(GoodsMovementLine.position))).scalars().all()
    users = dict((await db.execute(select(User.id, User.full_name).where(
        User.id.in_([u for u in (movement.created_by_user_id, movement.cancelled_by_user_id) if u])))).all())
    purchase = None
    if movement.purchase_invoice_id:
        pi = (await db.execute(select(PurchaseInvoice).where(PurchaseInvoice.id == movement.purchase_invoice_id))).scalar_one()
        purchase = f"{pi.series}/{pi.number} · {pi.supplier_document}"
    invoice_reference = None
    if movement.invoice_id:  # the invoice of a GR invoiced: FT FT2026/9
        from app.models.invoice import Invoice
        from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
        inv = (await db.execute(select(Invoice).where(Invoice.id == movement.invoice_id))).scalar_one()
        invoice_reference = f"{DOC_CODE_BY_INVOICE_TYPE.get(inv.invoice_type.value, 'FT')} {inv.series}/{inv.number}"
    party_nif = None
    if movement.customer_id:
        party_nif = (await db.execute(select(Customer.nif).where(Customer.id == movement.customer_id))).scalar_one()
    elif movement.supplier_id:
        party_nif = (await db.execute(select(Supplier.nif).where(Supplier.id == movement.supplier_id))).scalar_one()
    return {
        **_summary(movement, names), "party_nif": party_nif,
        "destination_warehouse": names["warehouses"].get(movement.destination_warehouse_id),
        "purchase_invoice": purchase, "invoice_id": movement.invoice_id, "invoice_reference": invoice_reference,
        "load_address": movement.load_address, "unload_address": movement.unload_address,
        "notes": movement.notes, "atcud": movement.atcud, "document_hash": movement.document_hash,
        "created_at": movement.created_at, "created_by": users.get(movement.created_by_user_id),
        "cancel_reason": movement.cancel_reason, "cancelled_at": movement.cancelled_at,
        "cancelled_by": users.get(movement.cancelled_by_user_id),
        "lines": [{
            "position": l.position, "product_code": l.product_code, "description": l.description, "unit": l.unit_code,
            "quantity": float(l.quantity), "unit_price": float(l.unit_price), "vat_rate": float(l.vat_rate),
            "tax_code": l.tax_code, "exemption_code": l.exemption_code, "line_net": float(l.line_net),
            "line_vat": float(l.line_vat),
        } for l in lines],
    }
