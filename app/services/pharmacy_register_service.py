"""
Farmácia, livraison 3 - the registers built from what is already recorded (the stock ledger, its lots, the sales
documents and their receitas); nothing new is entered:

- trace_lot: where one lot (a product's number and expiry) came from and where it went - every entry, transfer,
  sale, guide and loss of it, with the customer of each sale and its receita, and what is left in each warehouse.
  What a recall by the manufacturer or the ARMED needs.
- list_prescriptions: the registo de receitas - every sale dispensed against a receita, with its medicines and lots.
- psychotropic_register: per medicine of receita especial, over a period: the stock at the start, every entry and
  exit (sales with their receita, patient and document; losses and adjustments with their reason), the stock at the
  end - for the inspection. The whole company (every warehouse): a transfer between its warehouses is not listed.
"""
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.prescription import Prescription
from app.models.product import Product
from app.models.stock_lot import StockLot, StockMovementLot
from app.models.stock_movement import MovementType, StockMovement
from app.models.warehouse import Warehouse
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
from app.services.stock_lot_service import document_lot_text, lot_label, lots_of_document

INVOICE_TYPE_BY_CODE = {code: kind for kind, code in DOC_CODE_BY_INVOICE_TYPE.items()}

MOVEMENT_LABELS = {
    MovementType.RECEPCAO: "Entrada", MovementType.SAIDA: "Saída", MovementType.PERDA: "Perda",
    MovementType.AJUSTE: "Ajuste", MovementType.TRANSFERENCIA: "Transferência", MovementType.PRODUCAO: "Produção",
}
LOSS_LABELS = {"EXPIRACAO": "expirado", "QUEBRA": "quebra", "ROUBO": "roubo", "OUTRO": "outro"}


class RegisterError(Exception):
    """A register asked for something it cannot give (an invalid period) - a 422."""


class LotNotFoundError(RegisterError):
    """The lot is not one of the company's - a 404."""


def _signed(movement: StockMovement) -> float:
    """+ into the warehouse, - out of it - the same rule as stock_service.ledger_signed_quantity."""
    quantity = float(movement.quantity)
    kind = movement.movement_type
    if kind in (MovementType.RECEPCAO, MovementType.AJUSTE):
        return quantity
    if kind == MovementType.TRANSFERENCIA:
        return -quantity if movement.is_transfer_source else quantity
    if kind == MovementType.PRODUCAO:
        return quantity if movement.is_production_output else -quantity
    return -quantity  # SAIDA, PERDA


def _day_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    if date_to < date_from:
        raise RegisterError("A data final não pode ser anterior à data inicial")
    return datetime.combine(date_from, time.min), datetime.combine(date_to + timedelta(days=1), time.min)


async def _documents_of(db: AsyncSession, company_id: uuid.UUID, references: set) -> dict:
    """reference ('FT FT2026/9', 'GR GR2026/3') -> {customer, prescription} of the sale or guide it names."""
    out: dict = {}
    invoice_keys, guide_keys = {}, {}
    for ref in references:
        if not ref or " " not in ref or "/" not in ref:
            continue
        code, rest = ref.split(" ", 1)
        series, _, number = rest.rpartition("/")
        if not number.isdigit():
            continue
        if code in INVOICE_TYPE_BY_CODE:
            invoice_keys[(INVOICE_TYPE_BY_CODE[code], series, int(number))] = ref
        elif code in ("GR", "GT", "GD"):
            guide_keys[(code, series, int(number))] = ref
    if invoice_keys:
        series_list = {s for _, s, _ in invoice_keys}
        rows = (await db.execute(
            select(Invoice, Customer.name, Prescription)
            .outerjoin(Customer, Customer.id == Invoice.customer_id)
            .outerjoin(Prescription, Prescription.invoice_id == Invoice.id)
            .where(Invoice.company_id == company_id, Invoice.series.in_(series_list))
        )).all()
        for invoice, customer_name, prescription in rows:
            ref = invoice_keys.get((invoice.invoice_type.value, invoice.series, invoice.number))
            if ref:
                out[ref] = {"customer": customer_name or "Consumidor final", "prescription": prescription,
                            "invoice_id": invoice.id}
    if guide_keys:
        from app.models.goods_movement import GoodsMovement
        rows = (await db.execute(
            select(GoodsMovement, Customer.name)
            .outerjoin(Customer, Customer.id == GoodsMovement.customer_id)
            .where(GoodsMovement.company_id == company_id, GoodsMovement.series.in_({s for _, s, _ in guide_keys}))
        )).all()
        for guide, customer_name in rows:
            ref = guide_keys.get((guide.movement_type, guide.series, guide.number))
            if ref:
                out[ref] = {"customer": customer_name, "prescription": None, "invoice_id": None}
    return out


def _detail(movement: StockMovement, document: dict | None, warehouses: dict) -> str:
    """What the line says about the movement: the customer of a sale, the warehouses of a transfer, the reason."""
    if movement.movement_type == MovementType.TRANSFERENCIA:
        other = warehouses.get(movement.counterpart_warehouse_id, "-")
        return ("para " if movement.is_transfer_source else "de ") + other
    if document and document.get("customer"):
        return document["customer"]
    reason = movement.reason or ""
    if movement.movement_type == MovementType.PERDA and movement.loss_category is not None:
        label = LOSS_LABELS.get(movement.loss_category.value, "")
        reason = f"{label} - {reason}" if reason else label
    return reason


async def _warehouse_names(db: AsyncSession, company_id: uuid.UUID) -> dict:
    return dict((await db.execute(select(Warehouse.id, Warehouse.name).where(Warehouse.company_id == company_id))).all())


# ---------- Rastreabilidade de lote

async def trace_lot(db: AsyncSession, company_id: uuid.UUID, lot_id: uuid.UUID) -> dict:
    """The whole path of one lot - the same number and expiry of the same product, in every warehouse."""
    lot = (await db.execute(select(StockLot).where(StockLot.id == lot_id, StockLot.company_id == company_id))).scalar_one_or_none()
    if lot is None:
        raise LotNotFoundError("Lote não encontrado")
    product = (await db.execute(select(Product).where(Product.id == lot.product_id))).scalar_one()
    same = (await db.execute(select(StockLot).where(
        StockLot.company_id == company_id, StockLot.product_id == lot.product_id,
        StockLot.lot_number.is_(None) if lot.lot_number is None else StockLot.lot_number == lot.lot_number,
        StockLot.expiry_date.is_(None) if lot.expiry_date is None else StockLot.expiry_date == lot.expiry_date,
    ))).scalars().all()
    warehouses = await _warehouse_names(db, company_id)
    rows = (await db.execute(
        select(StockMovement, StockMovementLot.quantity)
        .join(StockMovementLot, StockMovementLot.movement_id == StockMovement.id)
        .where(StockMovementLot.lot_id.in_([l.id for l in same]))
        # the two legs of a transfer share their time: the warehouse it leaves first, then the one it enters
        .order_by(StockMovement.created_at, StockMovement.is_transfer_source.desc().nulls_last(), StockMovement.id)
    )).all()
    documents = await _documents_of(db, company_id, {m.reference for m, _ in rows})
    movements, sold = [], 0.0
    for movement, quantity in rows:
        signed = float(quantity) if _signed(movement) >= 0 else -float(quantity)
        document = documents.get(movement.reference)
        prescription = document.get("prescription") if document else None
        if movement.movement_type == MovementType.SAIDA and document and document.get("invoice_id"):
            sold += float(quantity)
        movements.append({
            "date": movement.created_at, "type": MOVEMENT_LABELS[movement.movement_type],
            "reference": movement.reference, "warehouse": warehouses.get(movement.warehouse_id, "-"),
            "quantity_in": signed if signed > 0 else None, "quantity_out": -signed if signed < 0 else None,
            "detail": _detail(movement, document, warehouses),
            "prescription": prescription.number if prescription else None,
        })
    return {
        "product_id": product.id, "product_code": product.code, "product_name": product.name,
        "lot_number": lot.lot_number, "expiry_date": lot.expiry_date, "label": lot_label(lot.lot_number, lot.expiry_date),
        "remaining": [{"warehouse": warehouses.get(l.warehouse_id, "-"), "quantity": float(l.quantity)}
                      for l in same if float(l.quantity) > 0],
        "remaining_total": sum(float(l.quantity) for l in same),
        "sold_total": sold,
        "movements": movements,
    }


# ---------- Registo de receitas

async def list_prescriptions(db: AsyncSession, company_id: uuid.UUID, date_from: date, date_to: date,
                             special: bool | None = None, search: str | None = None) -> list[dict]:
    """The sales dispensed against a receita between two dates (the documents' dates), newest first, each with its
    medicines, quantities and lots. special: only the receitas especiais (True) or only the others (False)."""
    if date_to < date_from:
        raise RegisterError("A data final não pode ser anterior à data inicial")
    query = (
        select(Prescription, Invoice, Customer.name)
        .join(Invoice, Invoice.id == Prescription.invoice_id)
        .outerjoin(Customer, Customer.id == Invoice.customer_id)
        .where(Prescription.company_id == company_id, Invoice.business_date >= date_from, Invoice.business_date <= date_to)
        .order_by(Invoice.business_date.desc(), Invoice.created_at.desc())
    )
    if special is not None:
        query = query.where(Prescription.is_special.is_(special))
    rows = (await db.execute(query)).all()
    if not rows:
        return []
    lines_by_invoice: dict = {}
    for line in (await db.execute(
        select(InvoiceLine).where(InvoiceLine.invoice_id.in_([inv.id for _, inv, _ in rows]), InvoiceLine.product_id.is_not(None))
        .order_by(InvoiceLine.created_at, InvoiceLine.id)
    )).scalars().all():
        lines_by_invoice.setdefault(line.invoice_id, []).append(line)
    medicine_ids = set((await db.execute(select(Product.id).where(
        Product.company_id == company_id, Product.is_medicine.is_(True),
        Product.dispensing_regime.in_(("RECEITA", "RECEITA_ESPECIAL")),
    ))).scalars().all())
    q = (search or "").strip().lower()
    out = []
    for prescription, invoice, customer_name in rows:
        reference = f"{DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, 'FT')} {invoice.series}/{invoice.number}"
        lots = await lots_of_document(db, company_id, reference)
        items = []
        for line in lines_by_invoice.get(invoice.id, []):
            if line.product_id not in medicine_ids:
                continue  # the receita covers the medicines on prescription; a soap on the same sale is not listed
            items.append({"product_name": line.product_name_snapshot, "quantity": float(line.quantity),
                          "unit": line.unit_code_snapshot, "lots": lots.get(line.product_id, [])})
        entry = {
            "id": prescription.id, "invoice_id": invoice.id, "date": invoice.business_date, "reference": reference,
            "customer": customer_name or "Consumidor final", "number": prescription.number,
            "prescriber": prescription.prescriber, "health_unit": prescription.health_unit,
            "patient_name": prescription.patient_name, "patient_document": prescription.patient_document,
            "is_special": prescription.is_special, "items": items,
        }
        if q:
            haystack = " ".join(str(v or "") for v in (entry["number"], entry["prescriber"], entry["health_unit"],
                                                        entry["patient_name"], entry["reference"],
                                                        *[i["product_name"] for i in items])).lower()
            if q not in haystack:
                continue
        out.append(entry)
    return out


# ---------- Registo de psicotrópicos e estupefacientes

async def psychotropic_register(db: AsyncSession, company_id: uuid.UUID, date_from: date, date_to: date) -> list[dict]:
    """Per medicine of receita especial: the stock on date_from, every entry and exit up to date_to (transfers between
    the company's warehouses left out - they change nothing to its stock), the stock at the end."""
    start, end = _day_bounds(date_from, date_to)
    products = (await db.execute(select(Product).where(
        Product.company_id == company_id, Product.is_medicine.is_(True), Product.dispensing_regime == "RECEITA_ESPECIAL",
    ).order_by(Product.name))).scalars().all()
    if not products:
        return []
    from app.services.stock_service import ledger_signed_quantity
    signed = ledger_signed_quantity()
    openings = dict((await db.execute(
        select(StockMovement.product_id, func.coalesce(func.sum(signed), 0))
        .where(StockMovement.company_id == company_id, StockMovement.product_id.in_([p.id for p in products]),
               StockMovement.created_at < start)
        .group_by(StockMovement.product_id)
    )).all())
    movements = (await db.execute(
        select(StockMovement).where(
            StockMovement.company_id == company_id, StockMovement.product_id.in_([p.id for p in products]),
            StockMovement.created_at >= start, StockMovement.created_at < end,
            StockMovement.movement_type != MovementType.TRANSFERENCIA,
        ).order_by(StockMovement.created_at, StockMovement.id)
    )).scalars().all()
    documents = await _documents_of(db, company_id, {m.reference for m in movements})
    warehouses = await _warehouse_names(db, company_id)
    lot_rows = (await db.execute(
        select(StockMovementLot.movement_id, StockLot.lot_number, StockLot.expiry_date, StockMovementLot.quantity)
        .join(StockLot, StockLot.id == StockMovementLot.lot_id)
        .where(StockMovementLot.movement_id.in_([m.id for m in movements]))
    )).all() if movements else []
    lots_by_movement: dict = {}
    for movement_id, number, expiry, _quantity in lot_rows:
        text = document_lot_text(number, expiry)
        if text and text not in lots_by_movement.setdefault(movement_id, []):
            lots_by_movement[movement_id].append(text)

    out = []
    for product in products:
        opening = float(openings.get(product.id, 0) or 0)
        balance, total_in, total_out, lines = opening, 0.0, 0.0, []
        for movement in (m for m in movements if m.product_id == product.id):
            quantity = _signed(movement)
            balance += quantity
            total_in += max(quantity, 0)
            total_out += max(-quantity, 0)
            document = documents.get(movement.reference)
            prescription = document.get("prescription") if document else None
            lines.append({
                "date": movement.created_at, "type": MOVEMENT_LABELS[movement.movement_type],
                "reference": movement.reference, "warehouse": warehouses.get(movement.warehouse_id, "-"),
                "detail": _detail(movement, document, warehouses), "lots": lots_by_movement.get(movement.id, []),
                "prescription": prescription.number if prescription else None,
                "patient": prescription.patient_name if prescription else None,
                "patient_document": prescription.patient_document if prescription else None,
                "quantity_in": quantity if quantity > 0 else None, "quantity_out": -quantity if quantity < 0 else None,
                "balance": round(balance, 3),
            })
        if not lines and opening == 0:
            continue  # a medicine never held in the period: nothing to declare
        out.append({
            "product_id": product.id, "product_code": product.code, "product_name": product.name,
            "active_substance": product.active_substance, "dosage": product.dosage,
            "opening": round(opening, 3), "total_in": round(total_in, 3), "total_out": round(total_out, 3),
            "closing": round(balance, 3), "lines": lines,
        })
    return out
