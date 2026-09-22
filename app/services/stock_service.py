"""
Business logic for stock management.
See specification v6/v7, section 5.1: every quantity change is logged as a
StockMovement (Recepcao, Saida, Transferencia, Ajuste, Inventario) -
Stock.quantity is never written directly, always through these functions.

Multi-warehouse model (see discussion on multi-activity stock): every
company has ONE central warehouse ("Armazem Principal", auto-seeded at
company creation) where all goods are received, and ONE dedicated
point-of-sale warehouse PER ACTIVITY (auto-created in activity_service),
stocked via internal transfer_stock() from the central warehouse. Sales
(deduct_stock_for_sale) always draw from the SELLING ACTIVITY's own
warehouse, never the central one directly.
"""
import uuid
from datetime import datetime, date, timedelta
from app.services.fiscal_period_service import is_period_open_for_date, PeriodClosedError

from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.stock_movement import StockMovement, MovementType, LossCategory
from app.models.warehouse import Warehouse
from app.models.product import Product
from app.models.recipe_ingredient import RecipeIngredient


class WarehouseNotFoundError(Exception):
    pass


class NoRecipeError(Exception):
    """Raised when trying to produce/estimate a product with no recipe defined."""
    pass


class InsufficientStockError(Exception):
    pass


def _format_quantity(value: float) -> str:
    """
    Formats a quantity for user-facing messages avoiding the period-as-
    thousands-separator ambiguity in pt-PT (46.000 reads as "quarenta e
    seis mil" in Portuguese) - whole numbers show with no decimals,
    fractional ones use a comma as the decimal separator (46,5).
    """
    if value == int(value):
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",")


async def get_default_warehouse(db: AsyncSession, company_id: uuid.UUID) -> Warehouse:
    """
    Returns the company's CENTRAL warehouse - where all goods are received
    (auto-seeded on company creation, section 5.2/2.8). Distinct from each
    activity's own point-of-sale warehouse (see Activity.warehouse_id).
    """
    result = await db.execute(
        select(Warehouse).where(Warehouse.company_id == company_id).order_by(Warehouse.created_at).limit(1)
    )
    warehouse = result.scalar_one_or_none()
    if warehouse is None:
        raise WarehouseNotFoundError("Nenhum armazem encontrado para esta empresa")
    return warehouse


async def list_warehouses(db: AsyncSession, company_id: uuid.UUID) -> list[Warehouse]:
    """Lists all of the company's warehouses (central + one per activity)."""
    result = await db.execute(
        select(Warehouse).where(Warehouse.company_id == company_id).order_by(Warehouse.created_at)
    )
    return list(result.scalars().all())


async def get_warehouse_or_raise(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    result = await db.execute(
        select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.company_id == company_id)
    )
    warehouse = result.scalar_one_or_none()
    if warehouse is None:
        raise WarehouseNotFoundError("Armazem nao encontrado")
    return warehouse


class CentralWarehouseNotEditableError(Exception):
    pass


async def create_warehouse(
    db: AsyncSession, company_id: uuid.UUID, name: str, code: str | None = None,
    province_id: uuid.UUID | None = None, municipality_id: uuid.UUID | None = None,
    address: str | None = None, allow_negative_stock: bool = False,
    entradas_bloqueadas: bool = False, saidas_bloqueadas: bool = False,
    gerido_por_familia_tipo: bool = False,
) -> Warehouse:
    """Creates an additional (secondary) warehouse for the company - GESTOR only. The
    default/central warehouse itself is only ever auto-created at company creation."""
    warehouse = Warehouse(
        company_id=company_id, name=name, code=code, province_id=province_id,
        municipality_id=municipality_id, address=address,
        allow_negative_stock=allow_negative_stock, entradas_bloqueadas=entradas_bloqueadas,
        saidas_bloqueadas=saidas_bloqueadas, gerido_por_familia_tipo=gerido_por_familia_tipo,
        is_active=True,
    )
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def update_warehouse(
    db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID, name: str,
    code: str | None = None, province_id: uuid.UUID | None = None,
    municipality_id: uuid.UUID | None = None, address: str | None = None,
    allow_negative_stock: bool = False, entradas_bloqueadas: bool = False,
    saidas_bloqueadas: bool = False, gerido_por_familia_tipo: bool = False,
) -> Warehouse:
    """Full edit of a SECONDARY warehouse - the central warehouse (oldest active one,
    see get_default_warehouse) can never be edited, matching "magasin principal
    auto-cree, non modifiable" from the spec."""
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    central = await get_default_warehouse(db, company_id)
    if warehouse.id == central.id:
        raise CentralWarehouseNotEditableError("O armazem central nao pode ser editado")

    warehouse.name = name
    warehouse.code = code
    warehouse.province_id = province_id
    warehouse.municipality_id = municipality_id
    warehouse.address = address
    warehouse.allow_negative_stock = allow_negative_stock
    warehouse.entradas_bloqueadas = entradas_bloqueadas
    warehouse.saidas_bloqueadas = saidas_bloqueadas
    warehouse.gerido_por_familia_tipo = gerido_por_familia_tipo
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def toggle_warehouse_status(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    """Activates/deactivates a SECONDARY warehouse - the central warehouse can never be
    deactivated (it is where all receptions land)."""
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    central = await get_default_warehouse(db, company_id)
    if warehouse.id == central.id:
        raise CentralWarehouseNotEditableError("O armazem central nao pode ser desativado")
    warehouse.is_active = not warehouse.is_active
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def rename_warehouse(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID, name: str) -> Warehouse:
    """Renames one of the company's warehouses - GESTOR only."""
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    warehouse.name = name
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def _get_or_create_stock_row(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID) -> Stock:
    result = await db.execute(
        select(Stock).where(Stock.product_id == product_id, Stock.warehouse_id == warehouse_id)
    )
    stock = result.scalar_one_or_none()
    if stock is None:
        stock = Stock(company_id=company_id, product_id=product_id, warehouse_id=warehouse_id, quantity=0)
        db.add(stock)
        await db.flush()
    return stock


async def receive_stock(
    db: AsyncSession,
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: float,
    reason: str | None = None,
) -> Stock:
    """Records incoming stock (purchase, production) into the CENTRAL warehouse - RECEPCAO movement."""
    if not await is_period_open_for_date(db, company_id, date.today()):
        raise PeriodClosedError(
            "O periodo ou ano fiscal correspondente a data de hoje nao esta aberto. "
            "Contacte o GESTOR para abrir o periodo antes de movimentar stock."
        )
    warehouse = await get_default_warehouse(db, company_id)
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse.id)

    stock.quantity = float(stock.quantity) + quantity
    db.add(StockMovement(
        company_id=company_id, product_id=product_id, warehouse_id=warehouse.id,
        movement_type=MovementType.RECEPCAO, quantity=quantity, reason=reason,
    ))

    await db.commit()
    await db.refresh(stock)
    return stock


async def transfer_stock(
    db: AsyncSession,
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    from_warehouse_id: uuid.UUID,
    to_warehouse_id: uuid.UUID,
    quantity: float,
    reason: str | None = None,
) -> None:
    """
    Internally moves stock between any two of the company's warehouses
    (central -> activity, activity -> central, or activity -> activity) -
    TRANSFERENCIA movement, logged as a pair (deduction from source,
    addition to destination) sharing the same reason so the audit trail
    reads as one transfer.
    """
    if not await is_period_open_for_date(db, company_id, date.today()):
        raise PeriodClosedError(
            "O periodo ou ano fiscal correspondente a data de hoje nao esta aberto. "
            "Contacte o GESTOR para abrir o periodo antes de movimentar stock."
        )
    if from_warehouse_id == to_warehouse_id:
        raise ValueError("O armazem de origem e destino nao pode ser o mesmo")

    await get_warehouse_or_raise(db, company_id, from_warehouse_id)
    await get_warehouse_or_raise(db, company_id, to_warehouse_id)

    source_stock = await _get_or_create_stock_row(db, company_id, product_id, from_warehouse_id)
    if float(source_stock.quantity) < quantity:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        product_name = product.name if product else str(product_id)
        raise InsufficientStockError(f"Stock insuficiente para {product_name} (disponível: {_format_quantity(float(source_stock.quantity))})")

    dest_stock = await _get_or_create_stock_row(db, company_id, product_id, to_warehouse_id)

    source_stock.quantity = float(source_stock.quantity) - quantity
    dest_stock.quantity = float(dest_stock.quantity) + quantity

    db.add(StockMovement(
        company_id=company_id, product_id=product_id, warehouse_id=from_warehouse_id,
        movement_type=MovementType.TRANSFERENCIA, quantity=quantity, reason=reason,
        counterpart_warehouse_id=to_warehouse_id, is_transfer_source=True,
    ))
    db.add(StockMovement(
        company_id=company_id, product_id=product_id, warehouse_id=to_warehouse_id,
        movement_type=MovementType.TRANSFERENCIA, quantity=quantity, reason=reason,
        counterpart_warehouse_id=from_warehouse_id, is_transfer_source=False,
    ))

    await db.commit()


async def record_stock_loss(
    db: AsyncSession,
    company_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: float,
    loss_category: str,
    reason: str | None = None,
) -> Stock:
    """
    Writes off stock with no sale - expiry, breakage, theft, or other
    (see LossCategory) - PERDA movement, distinct from a generic AJUSTE
    correction. Requires the category; free-text reason is optional detail.
    """
    if not await is_period_open_for_date(db, company_id, date.today()):
        raise PeriodClosedError(
            "O periodo ou ano fiscal correspondente a data de hoje nao esta aberto. "
            "Contacte o GESTOR para abrir o periodo antes de movimentar stock."
        )
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse.id)

    if float(stock.quantity) < quantity:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        product_name = product.name if product else str(product_id)
        raise InsufficientStockError(f"Stock insuficiente para {product_name} (disponível: {_format_quantity(float(stock.quantity))})")

    stock.quantity = float(stock.quantity) - quantity
    db.add(StockMovement(
        company_id=company_id, product_id=product_id, warehouse_id=warehouse.id,
        movement_type=MovementType.PERDA, quantity=quantity,
        loss_category=LossCategory(loss_category), reason=reason,
    ))

    await db.commit()
    await db.refresh(stock)
    return stock


async def adjust_stock(
    db: AsyncSession,
    company_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    new_quantity: float,
    reason: str,
) -> Stock:
    """
    Manually corrects stock to an exact new quantity (physical count
    reconciliation, damage, etc.) in a specific warehouse - AJUSTE
    movement, reason required.
    """
    if not await is_period_open_for_date(db, company_id, date.today()):
        raise PeriodClosedError(
            "O periodo ou ano fiscal correspondente a data de hoje nao esta aberto. "
            "Contacte o GESTOR para abrir o periodo antes de movimentar stock."
        )
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse.id)

    delta = new_quantity - float(stock.quantity)
    stock.quantity = new_quantity
    db.add(StockMovement(
        company_id=company_id, product_id=product_id, warehouse_id=warehouse.id,
        movement_type=MovementType.AJUSTE, quantity=delta, reason=reason,  # signed - preserves direction for display
    ))

    await db.commit()
    await db.refresh(stock)
    return stock


async def deduct_stock_for_sale(
    db: AsyncSession,
    company_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: float,
    reference: str,
) -> None:
    """
    Deducts stock for a sold line item from the SELLING ACTIVITY's own
    warehouse - SAIDA movement. Called from invoice_service.create_invoice
    within the same transaction, so a failed invoice never leaves a
    partial stock deduction behind. Raises InsufficientStockError if there
    is not enough stock - the invoice creation aborts entirely in that
    case (no partial sale).
    """
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse_id)

    if float(stock.quantity) < quantity:
        warehouse_result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
        warehouse = warehouse_result.scalar_one_or_none()
        if not (warehouse and warehouse.allow_negative_stock):
            result = await db.execute(select(Product).where(Product.id == product_id))
            product = result.scalar_one_or_none()
            product_name = product.name if product else str(product_id)
            raise InsufficientStockError(f"Stock insuficiente para {product_name} (disponível: {_format_quantity(float(stock.quantity))})")

    stock.quantity = float(stock.quantity) - quantity
    db.add(StockMovement(
        company_id=company_id, product_id=product_id, warehouse_id=warehouse_id,
        movement_type=MovementType.SAIDA, quantity=quantity, reference=reference,
    ))
    # No commit here - part of the caller's (invoice creation) transaction.


async def list_stock_levels(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> list[dict]:
    """Returns current stock quantity per product, for ONE specific warehouse."""
    result = await db.execute(
        select(Stock, Product)
        .join(Product, Product.id == Stock.product_id)
        .where(Stock.company_id == company_id, Stock.warehouse_id == warehouse_id)
        .order_by(Product.name)
    )
    rows = result.all()
    return [
        {
            "product_id": product.id,
            "product_code": product.code,
            "product_name": product.name,
            "quantity": float(stock.quantity),
            "min_stock_threshold": float(product.min_stock_threshold),
            "is_low": float(stock.quantity) <= float(product.min_stock_threshold),
        }
        for stock, product in rows
    ]


async def list_stock_movements(
    db: AsyncSession,
    company_id: uuid.UUID,
    warehouse_id: uuid.UUID | None = None,
    year: int | None = None,
    month: int | None = None,
    date_from=None,
    date_to=None,
    limit: int = 50,
    offset: int = 0,
) -> list[StockMovement]:
    """
    Lists stock movements, newest first, with optional filters (warehouse,
    year/month OR an explicit date_from/date_to range - all can combine)
    and pagination (limit/offset).
    """
    query = select(StockMovement).where(StockMovement.company_id == company_id)
    if warehouse_id is not None:
        query = query.where(StockMovement.warehouse_id == warehouse_id)
    if year is not None:
        query = query.where(extract("year", StockMovement.created_at) == year)
    if month is not None:
        query = query.where(extract("month", StockMovement.created_at) == month)
    if date_from is not None:
        query = query.where(StockMovement.created_at >= date_from)
    if date_to is not None:
        query = query.where(StockMovement.created_at <= date_to)
    query = query.order_by(StockMovement.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_movement_periods(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Returns the distinct (year, month) pairs that have stock movements - populates the Ano/Mes filters."""
    result = await db.execute(
        select(
            extract("year", StockMovement.created_at).label("year"),
            extract("month", StockMovement.created_at).label("month"),
        )
        .where(StockMovement.company_id == company_id)
        .distinct()
        .order_by(extract("year", StockMovement.created_at).desc(), extract("month", StockMovement.created_at).desc())
    )
    return [{"year": int(row.year), "month": int(row.month)} for row in result.all()]


async def _get_recipe_rows(db: AsyncSession, company_id: uuid.UUID, finished_product_id: uuid.UUID) -> list[RecipeIngredient]:
    result = await db.execute(
        select(RecipeIngredient).where(
            RecipeIngredient.company_id == company_id,
            RecipeIngredient.finished_product_id == finished_product_id,
        )
    )
    return list(result.scalars().all())


async def estimate_production_capacity(
    db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID, finished_product_id: uuid.UUID
) -> dict:
    """
    Estimates how many units of the finished product can be produced from
    the warehouse's CURRENT ingredient stock, in terms of the recipe's
    BATCH yield (see Product.batch_yield) - limited by whichever
    ingredient runs out first (the bottleneck), mirroring the classic
    "how many loaves can I bake with what I have" question.
    """
    recipe = await _get_recipe_rows(db, company_id, finished_product_id)
    if not recipe:
        raise NoRecipeError("Este produto nao tem receita definida")

    product_result = await db.execute(select(Product).where(Product.id == finished_product_id))
    product = product_result.scalar_one()
    batch_yield = float(product.batch_yield)

    max_batches = None
    bottleneck_product_id = None
    ingredient_breakdown = []

    for ing in recipe:
        stock = await _get_or_create_stock_row(db, company_id, ing.ingredient_product_id, warehouse_id)
        available = float(stock.quantity)
        per_batch = float(ing.quantity_per_batch)
        batches_from_this = available / per_batch if per_batch > 0 else float("inf")
        ingredient_breakdown.append({
            "ingredient_product_id": ing.ingredient_product_id,
            "available": available,
            "quantity_per_batch": per_batch,
        })
        if max_batches is None or batches_from_this < max_batches:
            max_batches = batches_from_this
            bottleneck_product_id = ing.ingredient_product_id

    import math
    max_units = math.floor(max_batches * batch_yield) if max_batches is not None else 0
    return {
        "max_units": max_units,
        "bottleneck_product_id": bottleneck_product_id,
        "ingredients": ingredient_breakdown,
    }


async def produce_stock(
    db: AsyncSession,
    company_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    finished_product_id: uuid.UUID,
    quantity_to_produce: float,
    reason: str | None = None,
) -> Stock:
    """
    Transforms ingredients into a finished product, within ONE warehouse
    (the activity's point-of-sale warehouse, where the physical
    transformation happens) - PRODUCAO movement. All-or-nothing: if ANY
    ingredient is insufficient, nothing is deducted or produced (raises
    InsufficientStockError before touching any row).
    """
    if not await is_period_open_for_date(db, company_id, date.today()):
        raise PeriodClosedError(
            "O periodo ou ano fiscal correspondente a data de hoje nao esta aberto. "
            "Contacte o GESTOR para abrir o periodo antes de produzir."
        )
    recipe = await _get_recipe_rows(db, company_id, finished_product_id)
    if not recipe:
        raise NoRecipeError("Este produto nao tem receita definida")

    await get_warehouse_or_raise(db, company_id, warehouse_id)

    product_result = await db.execute(select(Product).where(Product.id == finished_product_id))
    product = product_result.scalar_one()
    batches_needed = quantity_to_produce / float(product.batch_yield)

    # Validate ALL ingredients are sufficient BEFORE deducting any of them.
    ingredient_stocks = []
    for ing in recipe:
        needed = float(ing.quantity_per_batch) * batches_needed
        stock = await _get_or_create_stock_row(db, company_id, ing.ingredient_product_id, warehouse_id)
        if float(stock.quantity) < needed:
            result = await db.execute(select(Product).where(Product.id == ing.ingredient_product_id))
            product = result.scalar_one_or_none()
            product_name = product.name if product else str(ing.ingredient_product_id)
            raise InsufficientStockError(
                f"Stock insuficiente de {product_name} para produzir {_format_quantity(quantity_to_produce)} unidades "
                f"(necessario: {_format_quantity(needed)}, disponivel: {_format_quantity(float(stock.quantity))})"
            )
        ingredient_stocks.append((stock, needed, ing.ingredient_product_id))

    for stock, needed, ingredient_product_id in ingredient_stocks:
        stock.quantity = float(stock.quantity) - needed
        db.add(StockMovement(
            company_id=company_id, product_id=ingredient_product_id, warehouse_id=warehouse_id,
            movement_type=MovementType.PRODUCAO, quantity=needed, reason=reason,
            is_production_output=False,
        ))

    finished_stock = await _get_or_create_stock_row(db, company_id, finished_product_id, warehouse_id)
    finished_stock.quantity = float(finished_stock.quantity) + quantity_to_produce
    db.add(StockMovement(
        company_id=company_id, product_id=finished_product_id, warehouse_id=warehouse_id,
        movement_type=MovementType.PRODUCAO, quantity=quantity_to_produce, reason=reason,
        is_production_output=True,
    ))

    await db.commit()
    await db.refresh(finished_stock)
    return finished_stock


async def list_production_history(
    db: AsyncSession, company_id: uuid.UUID, year: int | None = None, month: int | None = None,
    date_from: str | None = None, date_to: str | None = None,
) -> list[dict]:
    """Reconstructs readable production batches from the StockMovement ledger - all rows
    from ONE produce_stock() call share the exact same created_at (transaction timestamp
    semantics), so grouping by (created_at, warehouse_id) reliably separates batches.
    year/month filter by calendar period ("Periodo"); date_from/date_to filter by an
    explicit range ("Intervalo") - the two are independent and can be combined."""
    conditions = [
        StockMovement.company_id == company_id,
        StockMovement.movement_type == MovementType.PRODUCAO,
    ]
    if year is not None:
        conditions.append(extract("year", StockMovement.created_at) == year)
    if month is not None:
        conditions.append(extract("month", StockMovement.created_at) == month)
    if date_from:
        conditions.append(StockMovement.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        conditions.append(StockMovement.created_at < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))

    result = await db.execute(
        select(StockMovement, Product, Warehouse)
        .join(Product, Product.id == StockMovement.product_id)
        .join(Warehouse, Warehouse.id == StockMovement.warehouse_id)
        .where(*conditions)
        .order_by(StockMovement.created_at.desc())
    )
    rows = result.all()

    batches = {}
    for movement, product, warehouse in rows:
        key = (movement.created_at, movement.warehouse_id)
        batch = batches.setdefault(key, {
            "created_at": movement.created_at,
            "warehouse_id": movement.warehouse_id,
            "warehouse_name": warehouse.name,
            "output": None,
            "ingredients": [],
        })
        entry = {"product_code": product.code, "product_name": product.name, "quantity": float(movement.quantity)}
        if movement.is_production_output:
            batch["output"] = entry
        else:
            batch["ingredients"].append(entry)

    return sorted(batches.values(), key=lambda b: b["created_at"], reverse=True)


async def get_stock_dashboard(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """Aggregated stock overview across all warehouses - per-product total quantity,
    low-stock flag (vs min_stock_threshold), and stock value (qty * purchase_price)."""
    result = await db.execute(
        select(Stock, Product)
        .join(Product, Product.id == Stock.product_id)
        .where(Stock.company_id == company_id, Product.is_active == True)  # noqa: E712
    )
    rows = result.all()

    totals: dict[uuid.UUID, dict] = {}
    for stock, product in rows:
        entry = totals.setdefault(product.id, {
            "product_id": product.id,
            "code": product.code,
            "name": product.name,
            "is_raw_material": product.is_raw_material,
            "min_stock_threshold": float(product.min_stock_threshold or 0),
            "purchase_price": float(product.purchase_price or 0),
            "sale_price": float(product.price or 0),
            "total_quantity": 0.0,
        })
        entry["total_quantity"] += float(stock.quantity)

    items = list(totals.values())
    for item in items:
        item["cost_value"] = round(item["total_quantity"] * item["purchase_price"], 2)
        item["sale_value"] = round(item["total_quantity"] * item["sale_price"], 2)
        item["is_low"] = item["total_quantity"] <= item["min_stock_threshold"]
        item["is_zero"] = item["total_quantity"] <= 0

    items.sort(key=lambda i: i["name"])

    return {
        "items": items,
        "total_products": len(items),
        "low_stock_count": sum(1 for i in items if i["is_low"]),
        "zero_stock_count": sum(1 for i in items if i["is_zero"]),
        "total_cost_value": round(sum(i["cost_value"] for i in items), 2),
        "total_sale_value": round(sum(i["sale_value"] for i in items), 2),
    }
