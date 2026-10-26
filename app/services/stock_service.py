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
from app.services.fiscal_period_service import ensure_period_open, PeriodClosedError, resolve_posting_period

from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.stock_movement import StockMovement, MovementType, LossCategory
from app.models.warehouse import Warehouse
from app.models.product import Product
from app.models.recipe_ingredient import RecipeIngredient
from app.services.stock_lot_service import LotInputError, check_lot_input, lots_in, lots_out, parts_taken_by


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
        raise WarehouseNotFoundError("Armazem não encontrado")
    return warehouse


class CentralWarehouseNotEditableError(Exception):
    pass


async def create_warehouse(
    db: AsyncSession, company_id: uuid.UUID, name: str, code: str | None = None,
    province_id: uuid.UUID | None = None, municipality_id: uuid.UUID | None = None,
    address: str | None = None, allow_negative_stock: bool = False,
    entradas_bloqueadas: bool = False, saidas_bloqueadas: bool = False,
) -> Warehouse:
    """Creates an additional (secondary) warehouse for the company - GESTOR only. The
    default/central warehouse itself is only ever auto-created at company creation."""
    from app.services.plan_service import check_limit
    await check_limit(db, company_id, "max_warehouses")
    warehouse = Warehouse(
        company_id=company_id, name=name, code=code, province_id=province_id,
        municipality_id=municipality_id, address=address,
        allow_negative_stock=allow_negative_stock, entradas_bloqueadas=entradas_bloqueadas,
        saidas_bloqueadas=saidas_bloqueadas,
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
    saidas_bloqueadas: bool = False,
) -> Warehouse:
    """Full edit of a SECONDARY warehouse - the central warehouse (oldest active one,
    see get_default_warehouse) can never be edited, matching "magasin principal
    auto-cree, non modifiable" from the spec."""
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    central = await get_default_warehouse(db, company_id)
    if warehouse.id == central.id:
        raise CentralWarehouseNotEditableError("O armazem central não pode ser editado")

    warehouse.name = name
    warehouse.code = code
    warehouse.province_id = province_id
    warehouse.municipality_id = municipality_id
    warehouse.address = address
    warehouse.allow_negative_stock = allow_negative_stock
    warehouse.entradas_bloqueadas = entradas_bloqueadas
    warehouse.saidas_bloqueadas = saidas_bloqueadas
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


async def toggle_warehouse_status(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    """Activates/deactivates a SECONDARY warehouse - the central warehouse can never be
    deactivated (it is where all receptions land)."""
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    central = await get_default_warehouse(db, company_id)
    if warehouse.id == central.id:
        raise CentralWarehouseNotEditableError("O armazem central não pode ser desativado")
    if not warehouse.is_active:  # switched back on - unless an activity's own warehouse (not counted)
        from app.models.activity import Activity
        from app.services.plan_service import check_limit
        if (await db.execute(select(Activity.id).where(Activity.warehouse_id == warehouse.id))).first() is None:
            await check_limit(db, company_id, "max_warehouses")
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


class StockBlockedError(InsufficientStockError):
    """A stock operation refused by a rule (warehouse frozen, product without stock). A subclass of InsufficientStockError
    so every caller that already reports stock refusals (invoices, credit notes...) reports it too, message included."""


async def _stock_rule(db: AsyncSession, product_id: uuid.UUID, warehouse_id: uuid.UUID, direction: str, strict: bool) -> bool:
    """
    THE stock rules, in one place: every operation that moves stock asks here first.
    direction: "in" (reception, transfer in, credit note return, production output), "out" (sale, transfer out, loss,
    production input, exit document) or "adjust" (inventory count - still allowed in a frozen warehouse).
    Returns False for a product without stock (managed_by_stock off): nothing moves - silently for an automatic
    operation (a sale), refused for a manual one (strict). A frozen warehouse refuses its blocked direction.
    Negative stock stays the sale's own rule (deduct_stock_for_sale, per warehouse): a transfer or a loss can never
    move goods that are not there.
    """
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if product is not None and not product.managed_by_stock:
        if strict:
            raise StockBlockedError(f"{product.name} não e gerido por stock")
        return False
    warehouse = (await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))).scalar_one_or_none()
    if warehouse is not None:
        name = getattr(warehouse, "name", "") or ""
        if direction == "in" and warehouse.entradas_bloqueadas:
            raise StockBlockedError(f"Entradas bloqueadas no armazem {name}".strip())
        if direction == "out" and warehouse.saidas_bloqueadas:
            raise StockBlockedError(f"Saídas bloqueadas no armazem {name}".strip())
    return True


async def ensure_available_at_period_end(
    db: AsyncSession, company_id: uuid.UUID, posting_period, product_id: uuid.UUID, warehouse_id: uuid.UUID,
    quantity: float, error_class: type[Exception],
) -> None:
    """Stock à data (company option): an exit booked in the SOFT-CLOSED period may not take more than the stock at
    that period's end - a late loss of 30 September cannot use what came in on 5 October. The active period needs no
    check of its own (its end is today: the current stock, checked by each caller). A warehouse allowing negative stock
    is never blocked. Raises error_class, the caller's own insufficient-stock error."""
    from app.models.company import Company
    from app.models.fiscal_year import FiscalYear
    from app.services.fiscal_period_service import MONTH_NAMES_PT
    from app.services.stock_period_closing_service import quantity_at_period_end  # local: it imports this module

    if getattr(posting_period.status, "value", posting_period.status) != "FECHO_PARCIAL" or quantity <= 0:
        return
    if not (await db.execute(select(Company.stock_check_at_period_end).where(Company.id == company_id))).scalar_one():
        return
    warehouse = (await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))).scalar_one_or_none()
    if warehouse is not None and warehouse.allow_negative_stock:
        return
    year = (await db.execute(select(FiscalYear.year).where(FiscalYear.id == posting_period.fiscal_year_id))).scalar_one()
    available = await quantity_at_period_end(db, company_id, posting_period, year, product_id, warehouse_id)
    if available < quantity:
        name = (await db.execute(select(Product.name).where(Product.id == product_id))).scalar_one_or_none() or str(product_id)
        raise error_class(
            f"Stock insuficiente para {name} no fim de {MONTH_NAMES_PT[posting_period.month]} de {year} "
            f"(disponível nessa data: {_format_quantity(available)}) - um lançamento tardio usa o stock do seu período"
        )


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


# Used by the tests only, to seed a company's central warehouse: the application receives stock through
# movement documents (Registar Rececao), the old /stock/receive route is gone.
async def receive_stock(
    db: AsyncSession,
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: float,
    reason: str | None = None,
    fiscal_period_id: uuid.UUID | None = None,
    lot_number: str | None = None,
    expiry_date: date | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> Stock:
    """Records incoming stock (purchase, production) into the CENTRAL warehouse - RECEPCAO movement."""
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id) if warehouse_id else await get_default_warehouse(db, company_id)
    await _stock_rule(db, product_id, warehouse.id, "in", strict=True)
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    lot_number, expiry_date = check_lot_input(product, lot_number, expiry_date)
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse.id)

    stock_before = float(stock.quantity)
    stock.quantity = stock_before + quantity
    movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=product_id, warehouse_id=warehouse.id,
        movement_type=MovementType.RECEPCAO, quantity=quantity, reason=reason,
    )
    db.add(movement)
    await lots_in(db, company_id, product_id, warehouse.id, quantity, movement, stock_before,
                  [(lot_number, expiry_date, quantity)])

    await db.commit()
    await db.refresh(stock)
    return stock


async def update_average_cost(db: AsyncSession, company_id: uuid.UUID, product: Product, base_quantity: float,
                              unit_cost: float) -> tuple[float | None, float]:
    """
    THE weighted average cost (CMP) rule, called before an entry's quantity is added to the stock: the new cost is
    (stock x current cost + quantity x unit cost) / (stock + quantity), on the company's whole stock (every warehouse).
    With no stock (or a negative one) or no known cost yet, the cost is this entry's. Only priced entries call it: a
    line without a price enters at the current cost. Exits never change the unit cost.
    Returns (cost before, cost after) - written on the entry's ledger row, the history of the cost.
    """
    from sqlalchemy import func as _func
    stock_before = float((await db.execute(
        select(_func.sum(Stock.quantity)).where(Stock.company_id == company_id, Stock.product_id == product.id)
    )).scalar() or 0)
    current = float(product.average_cost) if product.average_cost is not None else None
    if current is None or stock_before <= 0:
        product.average_cost = round(unit_cost, 4)
    else:
        product.average_cost = round((stock_before * current + base_quantity * unit_cost) / (stock_before + base_quantity), 4)
    return current, float(product.average_cost)


class StockQuantityError(Exception):
    """A quantity that cannot be taken: unit not one of the product's, decimal quantity in a whole unit."""


async def _to_base_quantity(db: AsyncSession, company_id: uuid.UUID, product_id: uuid.UUID, quantity: float,
                            sale_unit_id: uuid.UUID | None) -> float:
    """
    A quantity entered in one of the product's units (2 SC) in base units (50 KG) - the same conversion as sales and
    receptions (resolve_line_unit): an unknown unit or a decimal quantity in a whole unit is refused.
    """
    from app.services.product_sale_unit_service import SaleUnitInvalidError, resolve_line_unit
    product = (await db.execute(
        select(Product).where(Product.id == product_id, Product.company_id == company_id)
    )).scalar_one_or_none()
    if product is None:
        raise StockQuantityError("Produto não encontrado")
    try:
        _price, factor, _sale_unit_id, _code = await resolve_line_unit(db, company_id, product, sale_unit_id, quantity)
    except SaleUnitInvalidError as e:
        raise StockQuantityError(str(e))
    return quantity * factor


async def transfer_stock(
    db: AsyncSession,
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    from_warehouse_id: uuid.UUID,
    to_warehouse_id: uuid.UUID,
    quantity: float,
    reason: str | None = None,
    sale_unit_id: uuid.UUID | None = None,  # entered in one of the product's units (SC...); empty = base unit
    fiscal_period_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,  # a product followed by lot: the lot moved (empty = FEFO, never an expired one)
) -> None:
    """
    Internally moves stock between any two of the company's warehouses
    (central -> activity, activity -> central, or activity -> activity) -
    TRANSFERENCIA movement, logged as a pair (deduction from source,
    addition to destination) sharing the same reason so the audit trail
    reads as one transfer.
    """
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    quantity = await _to_base_quantity(db, company_id, product_id, quantity, sale_unit_id)
    if from_warehouse_id == to_warehouse_id:
        raise ValueError("O armazem de origem e destino não pode ser o mesmo")

    await get_warehouse_or_raise(db, company_id, from_warehouse_id)
    await get_warehouse_or_raise(db, company_id, to_warehouse_id)

    await _stock_rule(db, product_id, from_warehouse_id, "out", strict=True)
    await _stock_rule(db, product_id, to_warehouse_id, "in", strict=True)
    await ensure_available_at_period_end(db, company_id, posting_period, product_id, from_warehouse_id, quantity, InsufficientStockError)
    source_stock = await _get_or_create_stock_row(db, company_id, product_id, from_warehouse_id)
    if float(source_stock.quantity) < quantity:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        product_name = product.name if product else str(product_id)
        raise InsufficientStockError(f"Stock insuficiente para {product_name} (disponível: {_format_quantity(float(source_stock.quantity))})")

    dest_stock = await _get_or_create_stock_row(db, company_id, product_id, to_warehouse_id)

    dest_before = float(dest_stock.quantity)
    source_stock.quantity = float(source_stock.quantity) - quantity
    dest_stock.quantity = dest_before + quantity

    out_movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=product_id, warehouse_id=from_warehouse_id,
        movement_type=MovementType.TRANSFERENCIA, quantity=quantity, reason=reason,
        counterpart_warehouse_id=to_warehouse_id, is_transfer_source=True,
    )
    in_movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=product_id, warehouse_id=to_warehouse_id,
        movement_type=MovementType.TRANSFERENCIA, quantity=quantity, reason=reason,
        counterpart_warehouse_id=from_warehouse_id, is_transfer_source=False,
    )
    db.add(out_movement)
    db.add(in_movement)
    # the lots travel with the goods: same number and date in the destination warehouse
    taken = await lots_out(db, company_id, product_id, from_warehouse_id, quantity, out_movement, lot_id=lot_id,
                           usable_only=lot_id is None)
    await lots_in(db, company_id, product_id, to_warehouse_id, quantity, in_movement, dest_before, taken)

    await db.commit()


async def record_stock_loss(
    db: AsyncSession,
    company_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: float,
    loss_category: str,
    reason: str | None = None,
    sale_unit_id: uuid.UUID | None = None,  # entered in one of the product's units (SC...); empty = base unit
    fiscal_period_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,  # a product followed by lot: the lot lost (empty = FEFO, the expired first)
) -> Stock:
    """
    Writes off stock with no sale - expiry, breakage, theft, or other
    (see LossCategory) - PERDA movement, distinct from a generic AJUSTE
    correction. Requires the category; free-text reason is optional detail.
    """
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    quantity = await _to_base_quantity(db, company_id, product_id, quantity, sale_unit_id)
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    await _stock_rule(db, product_id, warehouse.id, "out", strict=True)
    await ensure_available_at_period_end(db, company_id, posting_period, product_id, warehouse.id, quantity, InsufficientStockError)
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse.id)

    if float(stock.quantity) < quantity:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        product_name = product.name if product else str(product_id)
        raise InsufficientStockError(f"Stock insuficiente para {product_name} (disponível: {_format_quantity(float(stock.quantity))})")

    stock.quantity = float(stock.quantity) - quantity
    movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=product_id, warehouse_id=warehouse.id,
        movement_type=MovementType.PERDA, quantity=quantity,
        loss_category=LossCategory(loss_category), reason=reason,
    )
    db.add(movement)
    await lots_out(db, company_id, product_id, warehouse.id, quantity, movement, lot_id=lot_id)

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
    sale_unit_id: uuid.UUID | None = None,  # entered in one of the product's units (SC...); empty = base unit
    fiscal_period_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,  # a product followed by lot - a decrease: the lot it takes (empty = FEFO)
    lot_number: str | None = None,  # an increase: the lot it fills
    expiry_date: date | None = None,
) -> Stock:
    """
    Manually corrects stock to an exact new quantity (physical count
    reconciliation, damage, etc.) in a specific warehouse - AJUSTE
    movement, reason required.
    """
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    new_quantity = await _to_base_quantity(db, company_id, product_id, new_quantity, sale_unit_id)
    warehouse = await get_warehouse_or_raise(db, company_id, warehouse_id)
    await _stock_rule(db, product_id, warehouse.id, "adjust", strict=True)
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse.id)

    stock_before = float(stock.quantity)
    delta = new_quantity - stock_before
    await ensure_available_at_period_end(db, company_id, posting_period, product_id, warehouse.id, -delta, InsufficientStockError)
    if delta > 0:
        product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
        try:
            lot_number, expiry_date = check_lot_input(product, lot_number, expiry_date)
        except LotInputError as e:
            raise InsufficientStockError(str(e))
    stock.quantity = new_quantity
    movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=product_id, warehouse_id=warehouse.id,
        movement_type=MovementType.AJUSTE, quantity=delta, reason=reason,  # signed - preserves direction for display
    )
    db.add(movement)
    if delta > 0:
        await lots_in(db, company_id, product_id, warehouse.id, delta, movement, stock_before, [(lot_number, expiry_date, delta)])
    elif delta < 0:
        await lots_out(db, company_id, product_id, warehouse.id, -delta, movement, lot_id=lot_id, allow_uncovered=True)

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
    fiscal_period_id: uuid.UUID | None = None,
) -> None:
    """
    Deducts stock for a sold line item from the SELLING ACTIVITY's own
    warehouse - SAIDA movement. Called from invoice_service.create_invoice
    within the same transaction, so a failed invoice never leaves a
    partial stock deduction behind. Raises InsufficientStockError if there
    is not enough stock - the invoice creation aborts entirely in that
    case (no partial sale).
    """
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    if not await _stock_rule(db, product_id, warehouse_id, "out", strict=False):
        return  # a product without stock: sold, nothing moves
    await ensure_available_at_period_end(db, company_id, posting_period, product_id, warehouse_id, quantity, InsufficientStockError)
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse_id)
    warehouse = (await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))).scalar_one_or_none()
    allow_negative = bool(warehouse and warehouse.allow_negative_stock)

    if float(stock.quantity) < quantity and not allow_negative:
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        product_name = product.name if product else str(product_id)
        raise InsufficientStockError(f"Stock insuficiente para {product_name} (disponível: {_format_quantity(float(stock.quantity))})")

    before = float(stock.quantity)
    stock.quantity = before - quantity
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    minimum = float(product.min_stock_threshold or 0) if product is not None else 0
    if minimum > 0 and before > minimum >= before - quantity:  # Notificações: stock baixo, once, at the crossing
        from app.services.notification_service import notify_low_stock
        await notify_low_stock(db, company_id, product, warehouse, before, before - quantity)
    movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=product_id, warehouse_id=warehouse_id,
        movement_type=MovementType.SAIDA, quantity=quantity, reference=reference,
    )
    db.add(movement)
    # FEFO, never an expired lot - a product followed by lot (see stock_lot_service)
    await lots_out(db, company_id, product_id, warehouse_id, quantity, movement, usable_only=True,
                   allow_uncovered=allow_negative)
    # No commit here - part of the caller's (invoice creation) transaction.


async def return_stock_for_credit_note(
    db: AsyncSession,
    company_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: float,
    reference: str,
    fiscal_period_id: uuid.UUID | None = None,
    sale_reference: str | None = None,  # the invoice credited: its goods go back into the lots its sale took
) -> None:
    """
    Puts credited goods back into the warehouse the sale took them from - the mirror of
    deduct_stock_for_sale. Recorded as a RECEPCAO movement whose reference is the credit note, so the
    sale (SAIDA, reference = invoice) and its return can be matched. Only called when the credit note
    explicitly asks for it. No commit here - part of the credit note's own transaction.
    """
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    if not await _stock_rule(db, product_id, warehouse_id, "in", strict=False):
        return
    stock = await _get_or_create_stock_row(db, company_id, product_id, warehouse_id)
    stock_before = float(stock.quantity)
    stock.quantity = stock_before + quantity
    movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=product_id, warehouse_id=warehouse_id,
        movement_type=MovementType.RECEPCAO, quantity=quantity, reference=reference,
        reason="Devolução - nota de crédito",
    )
    db.add(movement)
    parts = await parts_taken_by(db, company_id, product_id, warehouse_id, sale_reference, [MovementType.SAIDA]) if sale_reference else []
    await lots_in(db, company_id, product_id, warehouse_id, quantity, movement, stock_before, parts)


async def list_stock_levels(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> list[dict]:
    """Returns current stock quantity per product, for ONE specific warehouse."""
    result = await db.execute(
        select(Stock, Product)
        .join(Product, Product.id == Stock.product_id)
        .where(Stock.company_id == company_id, Stock.warehouse_id == warehouse_id)
        .order_by(Product.name)
    )
    rows = result.all()
    # a product followed by lot: how much of it has expired here (never sold - see stock_lot_service)
    from sqlalchemy import func as _func
    from app.models.stock_lot import StockLot
    from app.services.stock_lot_service import is_followed
    expired = dict((await db.execute(
        select(StockLot.product_id, _func.sum(StockLot.quantity)).where(
            StockLot.warehouse_id == warehouse_id, StockLot.quantity > 0, StockLot.expiry_date < date.today(),
        ).group_by(StockLot.product_id)
    )).all())
    # emplacements (optional): where each product is kept in this warehouse
    from app.models.warehouse_location import ProductLocation
    locations = dict((await db.execute(
        select(ProductLocation.product_id, ProductLocation.location_id).where(ProductLocation.warehouse_id == warehouse_id)
    )).all())
    from app.services.location_service import location_codes
    codes = await location_codes(db, [warehouse_id])
    return [
        {
            "product_id": product.id,
            "product_code": product.code,
            "product_name": product.name,
            "active_substance": product.active_substance if product.is_medicine else None,  # Farmácia: found by its DCI
            "quantity": float(stock.quantity),
            "min_stock_threshold": float(product.min_stock_threshold),
            "is_low": float(stock.quantity) <= float(product.min_stock_threshold),
            "followed_by_lot": is_followed(product),
            "expired_quantity": float(expired.get(product.id, 0) or 0),
            "location_id": locations.get(product.id),
            "location_code": codes.get((product.id, warehouse_id)),
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
        raise NoRecipeError("Este produto não tem receita definida")

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
    fiscal_period_id: uuid.UUID | None = None,
    sale_unit_id: uuid.UUID | None = None,  # produce in a package (5 CX)
    lot_number: str | None = None,  # a product followed by lot: the batch made (empty = P + the date, e.g. P20261016)
    expiry_date: date | None = None,  # a product followed by expiry: its date (required)
) -> Stock:
    """
    Transforms ingredients into a finished product, within ONE warehouse
    (the activity's point-of-sale warehouse, where the physical
    transformation happens) - PRODUCAO movement. All-or-nothing: if ANY
    ingredient is insufficient, nothing is deducted or produced (raises
    InsufficientStockError before touching any row).
    """
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    quantity_to_produce = await _to_base_quantity(db, company_id, finished_product_id, quantity_to_produce, sale_unit_id)  # 5 CX -> 150 UN
    recipe = await _get_recipe_rows(db, company_id, finished_product_id)
    if not recipe:
        raise NoRecipeError("Este produto não tem receita definida")

    await get_warehouse_or_raise(db, company_id, warehouse_id)
    await _stock_rule(db, finished_product_id, warehouse_id, "in", strict=True)

    product_result = await db.execute(select(Product).where(Product.id == finished_product_id))
    product = product_result.scalar_one()
    batches_needed = quantity_to_produce / float(product.batch_yield)
    if product.managed_by_batch and not (lot_number or "").strip():
        lot_number = f"P{date.today():%Y%m%d}"
    try:
        lot_number, expiry_date = check_lot_input(product, lot_number, expiry_date)
    except LotInputError as e:
        raise InsufficientStockError(str(e))

    # Validate ALL ingredients are sufficient BEFORE deducting any of them.
    ingredient_stocks = []
    for ing in recipe:
        needed = float(ing.quantity_per_batch) * batches_needed
        if not await _stock_rule(db, ing.ingredient_product_id, warehouse_id, "out", strict=False):
            continue  # an ingredient without stock (water...): used, nothing moves
        await ensure_available_at_period_end(db, company_id, posting_period, ing.ingredient_product_id, warehouse_id, needed,
                                             InsufficientStockError)
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

    # The cost of what is consumed (each ingredient at its average cost) becomes the cost of what is made. An
    # ingredient without a known cost never blocks the production: its cost stays incomplete (no CMP update).
    ingredient_costs = {}
    for _stock, _needed, ingredient_product_id in ingredient_stocks:
        ingredient = (await db.execute(select(Product).where(Product.id == ingredient_product_id))).scalar_one()
        ingredient_costs[ingredient_product_id] = float(ingredient.average_cost) if ingredient.average_cost is not None else None
    cost_complete = bool(ingredient_stocks) and all(c is not None for c in ingredient_costs.values())
    produced_unit_cost = (
        round(sum(needed * ingredient_costs[ing_id] for _s, needed, ing_id in ingredient_stocks) / quantity_to_produce, 4)
        if cost_complete else None
    )

    for stock, needed, ingredient_product_id in ingredient_stocks:
        stock.quantity = float(stock.quantity) - needed
        movement = StockMovement(
            company_id=company_id, fiscal_period_id=posting_period.id, product_id=ingredient_product_id, warehouse_id=warehouse_id,
            movement_type=MovementType.PRODUCAO, quantity=needed, reason=reason,
            is_production_output=False, unit_cost=ingredient_costs.get(ingredient_product_id),
        )
        db.add(movement)
        await lots_out(db, company_id, ingredient_product_id, warehouse_id, needed, movement, usable_only=True)

    cost_before = cost_after = None
    if produced_unit_cost is not None:  # THE average cost rule, before the quantity made is added (as a reception)
        finished = (await db.execute(select(Product).where(Product.id == finished_product_id))).scalar_one()
        cost_before, cost_after = await update_average_cost(db, company_id, finished, quantity_to_produce, produced_unit_cost)
    finished_stock = await _get_or_create_stock_row(db, company_id, finished_product_id, warehouse_id)
    finished_before = float(finished_stock.quantity)
    finished_stock.quantity = finished_before + quantity_to_produce
    movement = StockMovement(
        company_id=company_id, fiscal_period_id=posting_period.id, product_id=finished_product_id, warehouse_id=warehouse_id,
        movement_type=MovementType.PRODUCAO, quantity=quantity_to_produce, reason=reason,
        is_production_output=True, unit_cost=produced_unit_cost,
        average_cost_before=cost_before, average_cost_after=cost_after,
    )
    db.add(movement)
    await lots_in(db, company_id, finished_product_id, warehouse_id, quantity_to_produce, movement, finished_before,
                  [(lot_number, expiry_date, quantity_to_produce)])

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
        entry = {"product_code": product.code, "product_name": product.name, "quantity": float(movement.quantity),
                 "unit_cost": float(movement.unit_cost) if movement.unit_cost is not None else None}
        if movement.is_production_output:
            batch["output"] = entry
        else:
            batch["ingredients"].append(entry)

    return sorted(batches.values(), key=lambda b: b["created_at"], reverse=True)


def ledger_signed_quantity():
    """The quantity of a ledger row with its direction: + into the warehouse, - out of it (AJUSTE is stored as the
    signed difference already) - the one sign rule of the stock reports."""
    from sqlalchemy import case
    return case(
        (StockMovement.movement_type == MovementType.RECEPCAO, StockMovement.quantity),
        (StockMovement.movement_type == MovementType.AJUSTE, StockMovement.quantity),
        (StockMovement.movement_type == MovementType.TRANSFERENCIA,
         case((StockMovement.is_transfer_source.is_(True), -StockMovement.quantity), else_=StockMovement.quantity)),
        (StockMovement.movement_type == MovementType.PRODUCAO,
         case((StockMovement.is_production_output.is_(True), StockMovement.quantity), else_=-StockMovement.quantity)),
        else_=-StockMovement.quantity,  # SAIDA, PERDA
    )


async def get_stock_dashboard(db: AsyncSession, company_id: uuid.UUID, fiscal_period_id: uuid.UUID | None = None) -> dict:
    """
    Aggregated stock overview across all warehouses - per-product total quantity, low-stock flag (vs
    min_stock_threshold), stock value (qty * purchase_price) and the product's units (for the equivalence column).
    Without a period: the current stock. With a fiscal period: the stock at the END of that period, summed from the
    stock ledger (every movement booked up to and including it; movements without a period count when dated before
    the end of its month) - the ledger is complete, so it adds up to the stock table for the current period.
    """
    from datetime import date as _date
    from sqlalchemy import and_, func, or_
    from app.models.fiscal_period import FiscalPeriod
    from app.models.fiscal_year import FiscalYear
    from app.models.product_sale_unit import ProductSaleUnit
    from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
    from app.services.fiscal_period_service import MONTH_NAMES_PT

    quantities: dict[uuid.UUID, float] = {}
    period_label = None
    if fiscal_period_id is None:
        for product_id, quantity in (await db.execute(
            select(Stock.product_id, func.sum(Stock.quantity)).where(Stock.company_id == company_id).group_by(Stock.product_id)
        )).all():
            quantities[product_id] = float(quantity or 0)
    else:
        chosen = (await db.execute(
            select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(
                FiscalPeriod.id == fiscal_period_id, FiscalPeriod.company_id == company_id,
            )
        )).first()
        if chosen is None:
            raise StockQuantityError("Período fiscal inválido")
        period, year = chosen
        period_label = f"{MONTH_NAMES_PT[period.month]} {year}"
        end_of_month = _date(year + (1 if period.month == 12 else 0), period.month % 12 + 1, 1)
        signed = ledger_signed_quantity()
        rows = (await db.execute(
            select(StockMovement.product_id, func.sum(signed))
            .select_from(StockMovement)
            .outerjoin(FiscalPeriod, FiscalPeriod.id == StockMovement.fiscal_period_id)
            .outerjoin(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
            .where(
                StockMovement.company_id == company_id,
                or_(
                    and_(StockMovement.fiscal_period_id.is_(None), StockMovement.created_at < end_of_month),
                    FiscalYear.year < year,
                    and_(FiscalYear.year == year, FiscalPeriod.month <= period.month),
                ),
            )
            .group_by(StockMovement.product_id)
        )).all()
        quantities = {product_id: float(quantity or 0) for product_id, quantity in rows}

    products = (await db.execute(
        select(Product).where(Product.company_id == company_id, Product.is_active == True, Product.id.in_(list(quantities)))  # noqa: E712
    )).scalars().all() if quantities else []

    unit_codes = dict((await db.execute(select(UnitOfMeasureCatalog.id, UnitOfMeasureCatalog.code))).all())
    sale_units: dict[uuid.UUID, list[dict]] = {}
    for product_id, unit_id, factor in (await db.execute(
        select(ProductSaleUnit.product_id, ProductSaleUnit.unit_of_measure_id, ProductSaleUnit.factor).where(
            ProductSaleUnit.company_id == company_id, ProductSaleUnit.is_active.is_(True),
        )
    )).all():
        sale_units.setdefault(product_id, []).append({"code": unit_codes.get(unit_id), "factor": float(factor)})

    items = []
    for product in products:
        quantity = quantities.get(product.id, 0.0)
        average_cost = float(product.average_cost) if product.average_cost is not None else None
        sale_price = float(product.price or 0)
        cost_value = round(quantity * average_cost, 2) if average_cost is not None else 0.0
        sale_value = None if product.is_raw_material else round(quantity * sale_price, 2)  # a raw material is never sold
        threshold = float(product.min_stock_threshold or 0)
        items.append({
            "product_id": product.id,
            "code": product.code,
            "name": product.name,
            "is_raw_material": product.is_raw_material,
            "min_stock_threshold": threshold,
            "average_cost": average_cost,
            "cost_unknown": average_cost is None,
            "sale_price": sale_price,
            "total_quantity": quantity,
            "unit_code": unit_codes.get(product.unit_of_measure_id),
            "sale_units": sorted(sale_units.get(product.id, []), key=lambda u: -u["factor"]),
            "cost_value": cost_value,
            "sale_value": sale_value,
            # Potential margin if the whole stock were sold at the base unit's price - only when the cost is known.
            "margin_value": round(sale_value - cost_value, 2) if average_cost is not None and sale_value is not None else None,
            "is_low": quantity <= threshold,
            "is_zero": quantity <= 0,
        })
    items.sort(key=lambda i: i["name"])

    periods = [
        {"id": p.id, "label": f"{MONTH_NAMES_PT[p.month]} {year}", "status": p.status}
        for p, year in (await db.execute(
            select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
            .where(FiscalPeriod.company_id == company_id).order_by(FiscalYear.year.desc(), FiscalPeriod.month.desc())
        )).all()
    ]

    known = [i for i in items if not i["cost_unknown"] and i["sale_value"] is not None]  # sellable, with a known cost
    known_sales = sum(i["sale_value"] for i in known)
    return {
        "items": items,
        "total_products": len(items),
        "low_stock_count": sum(1 for i in items if i["is_low"]),
        "zero_stock_count": sum(1 for i in items if i["is_zero"]),
        "total_cost_value": round(sum(i["cost_value"] for i in items), 2),
        "total_sale_value": round(sum(i["sale_value"] for i in items if i["sale_value"] is not None), 2),
        "total_margin_value": round(sum(i["margin_value"] for i in known), 2),
        "margin_rate": round(100 * sum(i["margin_value"] for i in known) / known_sales, 1) if known_sales else None,
        "unknown_cost_count": sum(1 for i in items if i["cost_unknown"] and i["total_quantity"] > 0),
        "period_label": period_label,
        "periods": periods,
        # lots et péremption, today (whatever the period shown): lots expired and lots expiring within the alert days
        **await _expiry_counts(db, company_id),
    }


async def _expiry_counts(db: AsyncSession, company_id: uuid.UUID) -> dict:
    from app.services.stock_lot_service import list_expiring
    expiring = await list_expiring(db, company_id)
    return {"lots_expired_count": expiring["expired_count"], "lots_expiring_count": expiring["expiring_count"],
            "expiry_alert_days": expiring["alert_days"]}


