"""
Histórico do custo - how the weighted average cost (CMP) of a product moved: every entry that changed it (a priced
reception, a production with a complete cost), with its unit cost and the CMP before and after. A read of the stock
ledger (StockMovement.average_cost_before / _after, written by stock_service.update_average_cost's callers), nothing
stored here. The history starts with the version that records it: older entries carry no cost.
"""
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.stock_movement import MovementType, StockMovement
from app.models.stock_movement_document import StockMovementDocument
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services.hotel_service import LUANDA


class CostHistoryProductNotFoundError(Exception):
    pass


def _cost(value) -> float | None:
    return round(float(value), 4) if value is not None else None


async def get_cost_history(
    db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID,
    date_from: date | None = None, date_to: date | None = None,
) -> dict:
    """{current_cost, last_purchase_price, min_unit_cost, max_unit_cost, entries: [...]} - entries most recent first;
    the date of a reception is its document's (the real day of the delivery), a production's its own day."""
    product = (await db.execute(
        select(Product).where(Product.id == product_id, Product.company_id == company_id)
    )).scalar_one_or_none()
    if product is None:
        raise CostHistoryProductNotFoundError("Produto não encontrado")

    query = select(StockMovement).where(
        StockMovement.company_id == company_id, StockMovement.product_id == product_id,
        StockMovement.average_cost_after.is_not(None),
    )
    if date_from is not None:
        query = query.where(StockMovement.created_at >= datetime.combine(date_from, time.min, tzinfo=LUANDA))
    if date_to is not None:
        query = query.where(StockMovement.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=LUANDA))
    movements = (await db.execute(query.order_by(StockMovement.created_at.desc()))).scalars().all()

    # the reception document of each entry (its reference is "<series>/<number>"): its real date and supplier
    references = {m.reference for m in movements if m.reference}
    documents = {}
    if references:
        rows = (await db.execute(
            select(StockMovementDocument, Supplier.name)
            .outerjoin(Supplier, Supplier.id == StockMovementDocument.supplier_id)
            .where(StockMovementDocument.company_id == company_id,
                   func.concat(StockMovementDocument.series, "/", StockMovementDocument.number).in_(references))
        )).all()
        documents = {f"{doc.series}/{doc.number}": (doc, supplier) for doc, supplier in rows}
    warehouses = dict((await db.execute(
        select(Warehouse.id, Warehouse.name).where(Warehouse.company_id == company_id)
    )).all())

    entries = []
    for m in movements:
        document, supplier = documents.get(m.reference, (None, None))
        before, after = _cost(m.average_cost_before), _cost(m.average_cost_after)
        entries.append({
            "id": m.id,
            "kind": "PRODUCAO" if m.movement_type == MovementType.PRODUCAO else "RECEPCAO",
            "date": document.movement_date if document is not None else m.created_at.astimezone(LUANDA).date(),
            "created_at": m.created_at,
            "reference": m.reference,
            "supplier": supplier,
            "warehouse": warehouses.get(m.warehouse_id),
            "quantity": round(float(m.quantity), 3),
            "unit_cost": _cost(m.unit_cost),
            "cost_before": before,
            "cost_after": after,
            # the change of the CMP, in % - none for the first known cost
            "change_pct": round((after - before) / before * 100, 2) if before else None,
        })
    unit_costs = [e["unit_cost"] for e in entries if e["unit_cost"] is not None]
    return {
        "current_cost": _cost(product.average_cost),
        "last_purchase_price": round(float(product.purchase_price), 2) if product.purchase_price is not None else None,
        "min_unit_cost": min(unit_costs) if unit_costs else None,
        "max_unit_cost": max(unit_costs) if unit_costs else None,
        "entries": entries,
    }
