"""
Lots et péremption (point 4) - THE lot rules, in one place: every operation that moves the stock of a product followed
by lot (managed_by_batch) or by expiry (managed_by_expiry) asks here, right after it has written its ledger row
(StockMovement) and changed Stock.quantity. A product not followed returns at once - nothing changes for it.

- an entry fills a lot: the one typed (number and/or date - check_lot_input says which is required), or the lots an
  earlier exit took (a return, a transfer's destination). The same number and date add to the same lot.
- an exit takes the lots FEFO (the first to expire first; lots without a date after, oldest first), or the one lot
  asked for. An automatic exit that sells or uses the goods (usable_only) never takes an expired lot.
- the lots of a warehouse always add up to its Stock.quantity (zero while a warehouse allowing negative stock is below
  zero): an exit takes more than its lots only in such a warehouse and only once every lot is empty, and the next
  entry first fills that gap.
See app/models/stock_lot.py.
"""
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.stock_lot import StockLot, StockMovementLot
from app.models.stock_movement import StockMovement

# A part of an entry: the lot it fills (number, date) and how much of it.
LotPart = tuple[str | None, date | None, float]

_EPS = 1e-9


def is_followed(product: Product | None) -> bool:
    """A product whose stock is followed by lot: by number, by expiry date, or both."""
    return product is not None and bool(product.managed_by_batch or product.managed_by_expiry) and product.managed_by_stock


def _fmt(value: float) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def lot_label(lot_number: str | None, expiry_date: date | None) -> str:
    """How a lot is named on screen: L123 (val. 31/12/2026), L123, val. 31/12/2026, or Sem lote."""
    parts = []
    if lot_number:
        parts.append(lot_number)
    if expiry_date:
        parts.append(f"val. {expiry_date.strftime('%d/%m/%Y')}")
    if not parts:
        return "Sem lote"
    return parts[0] if len(parts) == 1 else f"{parts[0]} ({parts[1]})"


class LotInputError(Exception):
    """A lot that cannot be entered as typed (missing number or date, a date already past)."""


def check_lot_input(product: Product, lot_number: str | None, expiry_date: date | None,
                    movement_date: date | None = None) -> tuple[str | None, date | None]:
    """
    The lot of an entry, as typed, checked against the product: the number is required when it is followed by lot,
    the date when it is followed by expiry (each optional otherwise). A date already past on the entry's day is
    refused - expired goods never enter the stock. A product not followed keeps neither.
    """
    if not is_followed(product):
        return None, None
    lot_number = " ".join((lot_number or "").split())[:60] or None
    if product.managed_by_batch and not lot_number:
        raise LotInputError(f"Indique o lote de {product.name}")
    if product.managed_by_expiry and expiry_date is None:
        raise LotInputError(f"Indique a validade de {product.name}")
    day = movement_date or date.today()
    if expiry_date is not None and expiry_date < day:
        raise LotInputError(f"A validade de {product.name} ({expiry_date.strftime('%d/%m/%Y')}) já passou")
    return lot_number, expiry_date


async def _product(db: AsyncSession, product_id: uuid.UUID) -> Product | None:
    return (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()


async def _find_or_create_lot(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID,
                              lot_number: str | None, expiry_date: date | None) -> StockLot:
    lot = (await db.execute(select(StockLot).where(
        StockLot.product_id == product_id, StockLot.warehouse_id == warehouse_id,
        StockLot.lot_number.is_not_distinct_from(lot_number), StockLot.expiry_date.is_not_distinct_from(expiry_date),
    ).with_for_update())).scalars().first()
    if lot is None:
        lot = StockLot(id=uuid.uuid4(), company_id=company_id, product_id=product_id, warehouse_id=warehouse_id,
                       lot_number=lot_number, expiry_date=expiry_date, quantity=0)
        db.add(lot)
    return lot


async def lots_in(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID,
                  quantity: float, movement: StockMovement, stock_before: float,
                  parts: list[LotPart] | None = None) -> list[StockLot]:
    """
    An entry of `quantity` base units into the lots, after its ledger row `movement`. `stock_before` is the
    warehouse's Stock.quantity before the entry: below zero, that gap is filled first (the goods already left without
    a lot). `parts` say which lots it fills, in order; what they do not cover goes to "Sem lote". Returns the lots
    filled (for the document line), empty for a product not followed.
    """
    if quantity <= _EPS or not is_followed(await _product(db, product_id)):
        return []
    remaining_gap = max(0.0, -float(stock_before))
    filled: list[StockLot] = []
    plan = list(parts or [])
    covered = sum(p[2] for p in plan)
    if quantity - covered > _EPS:
        plan.append((None, None, quantity - covered))
    for lot_number, expiry_date, part_quantity in plan:
        part_quantity = min(float(part_quantity), quantity)
        if part_quantity <= _EPS:
            continue
        gap = min(remaining_gap, part_quantity)
        remaining_gap -= gap
        into_lot = round(part_quantity - gap, 3)
        if into_lot <= _EPS:
            continue
        lot = await _find_or_create_lot(db, company_id, product_id, warehouse_id, lot_number, expiry_date)
        lot.quantity = round(float(lot.quantity or 0) + into_lot, 3)
        db.add(StockMovementLot(movement=movement, lot=lot, quantity=into_lot))
        filled.append(lot)
    return filled


async def lots_out(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID,
                   quantity: float, movement: StockMovement, *, lot_id: uuid.UUID | None = None,
                   usable_only: bool = False, allow_uncovered: bool = False,
                   error_class: type[Exception] | None = None, today: date | None = None) -> list[LotPart]:
    """
    An exit of `quantity` base units out of the lots, after its ledger row `movement`. FEFO, or the one lot `lot_id`.
    usable_only: a sale, a consumption, a production, a guide, a transfer - an expired lot is never taken.
    allow_uncovered: a warehouse allowing negative stock - once every lot is empty, the rest leaves without a lot.
    Raises error_class (the caller's insufficient-stock error) when the lots cannot give it. Returns what was taken,
    as parts (number, date, quantity) - what a transfer or a return puts back.
    """
    if quantity <= _EPS:
        return []
    product = await _product(db, product_id)
    if not is_followed(product):
        return []
    if error_class is None:
        from app.services.stock_service import InsufficientStockError  # local: stock_service imports this module
        error_class = InsufficientStockError
    today = today or date.today()

    query = select(StockLot).where(StockLot.product_id == product_id, StockLot.warehouse_id == warehouse_id,
                                   StockLot.quantity > 0)
    if lot_id is not None:
        lot = (await db.execute(query.where(StockLot.id == lot_id).with_for_update())).scalar_one_or_none()
        if lot is None:
            raise error_class(f"Lote não encontrado ou sem stock para {product.name}")
        if float(lot.quantity) + _EPS < quantity:
            raise error_class(f"Quantidade insuficiente no lote {lot_label(lot.lot_number, lot.expiry_date)} de "
                              f"{product.name} (disponível: {_fmt(float(lot.quantity))})")
        candidates, others = [lot], []
    else:
        lots = list((await db.execute(query.order_by(
            StockLot.expiry_date.asc().nulls_last(), StockLot.created_at, StockLot.id).with_for_update())).scalars().all())
        if usable_only:
            candidates = [l for l in lots if l.expiry_date is None or l.expiry_date >= today]
            others = [l for l in lots if not (l.expiry_date is None or l.expiry_date >= today)]
        else:
            candidates, others = lots, []

    taken: list[LotPart] = []
    remaining = float(quantity)
    for lot in candidates:
        if remaining <= _EPS:
            break
        part = round(min(float(lot.quantity), remaining), 3)
        lot.quantity = round(float(lot.quantity) - part, 3)
        remaining = round(remaining - part, 3)
        db.add(StockMovementLot(movement=movement, lot=lot, quantity=part))
        taken.append((lot.lot_number, lot.expiry_date, part))

    if remaining > _EPS:
        expired = sum(float(l.quantity) for l in others)
        if not allow_uncovered or expired > _EPS:
            available = float(quantity) - remaining
            text = f"Stock insuficiente para {product.name} (disponível: {_fmt(available)}"
            if expired > _EPS:
                text += f"; {_fmt(expired)} expirado - registe a perda"
            raise error_class(text + ")")
    return taken


async def parts_taken_by(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID,
                         reference: str, movement_types: list) -> list[LotPart]:
    """The lots earlier exits of a document (its reference: a sale, a guide) took from a warehouse - what a return
    (credit note, cancellation) puts back into them."""
    rows = (await db.execute(
        select(StockLot.lot_number, StockLot.expiry_date, func.sum(StockMovementLot.quantity))
        .join(StockMovementLot, StockMovementLot.lot_id == StockLot.id)
        .join(StockMovement, StockMovement.id == StockMovementLot.movement_id)
        .where(StockMovement.company_id == company_id, StockMovement.product_id == product_id,
               StockMovement.warehouse_id == warehouse_id, StockMovement.reference == reference,
               StockMovement.movement_type.in_(movement_types))
        .group_by(StockLot.lot_number, StockLot.expiry_date)
        .order_by(StockLot.expiry_date.desc().nulls_first())
    )).all()
    return [(n, d, float(q)) for n, d, q in rows]


async def lots_followed_total(db: AsyncSession, product_id: uuid.UUID, warehouse_id: uuid.UUID) -> float:
    return float((await db.execute(select(func.coalesce(func.sum(StockLot.quantity), 0)).where(
        StockLot.product_id == product_id, StockLot.warehouse_id == warehouse_id))).scalar_one())


async def list_lots(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID,
                    warehouse_id: uuid.UUID | None = None, today: date | None = None) -> list[dict]:
    """The lots of a product still holding stock, per warehouse, FEFO - with how many days are left."""
    from app.models.warehouse import Warehouse
    today = today or date.today()
    query = (select(StockLot, Warehouse.name).join(Warehouse, Warehouse.id == StockLot.warehouse_id)
             .where(StockLot.company_id == company_id, StockLot.product_id == product_id, StockLot.quantity > 0))
    if warehouse_id is not None:
        query = query.where(StockLot.warehouse_id == warehouse_id)
    rows = (await db.execute(query.order_by(Warehouse.name, StockLot.expiry_date.asc().nulls_last(), StockLot.created_at))).all()
    return [{
        "id": lot.id, "warehouse_id": lot.warehouse_id, "warehouse_name": name, "lot_number": lot.lot_number,
        "expiry_date": lot.expiry_date, "quantity": float(lot.quantity), "label": lot_label(lot.lot_number, lot.expiry_date),
        "days_left": (lot.expiry_date - today).days if lot.expiry_date else None,
        "expired": bool(lot.expiry_date and lot.expiry_date < today),
    } for lot, name in rows]
