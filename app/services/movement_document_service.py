"""
StockMovementDocument service - creates the printable Entrada/Saida document AND, for
traceability, writes the corresponding low-level StockMovement ledger rows and updates
the real Stock.quantity - see PARTIE1&2 GESTAO DE STOCK: "ce sont des documents comme
avec les factures".
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.warehouse import Warehouse
from app.models.product import Product
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.movement_type import MovementType as MovementTypeCatalog, MovementDirection
from app.models.movement_series import MovementSeries
from app.models.stock_movement import StockMovement, MovementType as LedgerMovementType
from app.models.stock_movement_document import StockMovementDocument, StockMovementDocumentLine
from app.services.stock_service import _get_or_create_stock_row, _stock_rule, InsufficientStockError as _StockRuleError, update_average_cost
from app.services.product_sale_unit_service import SaleUnitInvalidError, resolve_line_unit
from app.services.fiscal_period_service import ensure_period_open, PeriodClosedError, resolve_posting_period
import io
import openpyxl


class MovementTypeNotConfiguredError(Exception):
    pass


class MovementWarehouseNotFoundError(Exception):
    pass


class MovementProductNotFoundError(Exception):
    pass


class EmptyMovementError(Exception):
    pass


class InsufficientStockForMovementError(Exception):
    pass


async def _get_or_create_movement_series(db: AsyncSession, company_id: uuid.UUID, movement_type_id: uuid.UUID, year: int) -> MovementSeries:
    """Mirrors get_or_create_current_series (invoices) but simpler - no electronic mode,
    the code is always {movement_type.code}{year}, auto-created on first use."""
    result = await db.execute(select(MovementSeries).where(
        MovementSeries.company_id == company_id,
        MovementSeries.movement_type_id == movement_type_id,
        MovementSeries.year == year,
    ))
    series = result.scalar_one_or_none()
    if series is not None:
        return series

    type_result = await db.execute(select(MovementTypeCatalog).where(MovementTypeCatalog.id == movement_type_id))
    movement_type = type_result.scalar_one()
    series = MovementSeries(
        company_id=company_id, movement_type_id=movement_type_id, year=year,
        series_code=f"{movement_type.code}{year}", current_number=0,
    )
    db.add(series)
    await db.flush()
    return series


async def create_stock_movement_document(
    db: AsyncSession,
    company_id: uuid.UUID,
    movement_type_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    lines_input: list[dict],
    movement_date: date | None = None,
    description: str | None = None,
    supplier_id: uuid.UUID | None = None,
    fiscal_period_id: uuid.UUID | None = None,
) -> StockMovementDocument:
    """
    lines_input items: {product_id, quantity, purchase_price, sale_price}
    """
    movement_date = movement_date or date.today()

    # Internal entry: real date, booked in the chosen period (the soft-closed month for a late entry).
    posting_period = await resolve_posting_period(db, company_id, fiscal_period_id)
    # The date is the real date of the physical event (a delivery of 30 September entered on 1 October): never in the
    # future, never before the first day of the period it is booked in.
    from app.models.fiscal_year import FiscalYear
    from app.services.fiscal_period_service import MONTH_NAMES_PT, PeriodClosedError
    period_year = (await db.execute(select(FiscalYear.year).where(FiscalYear.id == posting_period.fiscal_year_id))).scalar_one()
    if movement_date > date.today():
        raise PeriodClosedError("A data do movimento nao pode ser futura")
    if movement_date < date(period_year, posting_period.month, 1):
        raise PeriodClosedError(
            f"A data do movimento ({movement_date.strftime('%d/%m/%Y')}) e anterior ao periodo escolhido "
            f"({MONTH_NAMES_PT[posting_period.month]} de {period_year})"
        )

    type_result = await db.execute(select(MovementTypeCatalog).where(MovementTypeCatalog.id == movement_type_id))
    movement_type = type_result.scalar_one_or_none()
    if movement_type is None or not movement_type.is_active:
        raise MovementTypeNotConfiguredError("Tipo de movimento nao encontrado ou inativo")

    warehouse_result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.company_id == company_id))
    warehouse = warehouse_result.scalar_one_or_none()
    if warehouse is None:
        raise MovementWarehouseNotFoundError("Armazem nao encontrado")

    if not lines_input:
        raise EmptyMovementError("O movimento deve ter pelo menos uma linha")

    series = await _get_or_create_movement_series(db, company_id, movement_type_id, movement_date.year)
    series.current_number += 1
    next_number = series.current_number

    total_quantity = 0.0
    total_value = 0.0
    line_objects = []
    is_entrada = movement_type.direction == MovementDirection.ENTRADA
    ledger_type = LedgerMovementType.RECEPCAO if is_entrada else LedgerMovementType.SAIDA

    for line_input in lines_input:
        product_result = await db.execute(select(Product).where(Product.id == line_input["product_id"], Product.company_id == company_id))
        product = product_result.scalar_one_or_none()
        if product is None:
            raise MovementProductNotFoundError("Produto nao encontrado")

        quantity = float(line_input["quantity"])
        # A line may be entered in one of the product's units (10 SC): its quantity and prices are per that unit, the stock
        # moves quantity x factor base units - the same conversion as a sale (resolve_line_unit).
        try:
            _unit_price, factor, line_sale_unit_id, unit_code = await resolve_line_unit(
                db, company_id, product, line_input.get("sale_unit_id"), quantity,
            )
        except SaleUnitInvalidError as e:
            raise MovementProductNotFoundError(str(e))
        base_quantity = quantity * factor
        purchase_price = float(line_input.get("purchase_price", 0) or 0)
        sale_price = float(line_input.get("sale_price", 0) or 0)
        line_value_price = purchase_price if is_entrada else sale_price
        line_total = round(quantity * line_value_price, 2)

        total_quantity += base_quantity  # base units: bags and kilos are never added up
        total_value += line_total

        # Update the real stock quantity + write the audit ledger row - see module docstring.
        try:
            await _stock_rule(db, product.id, warehouse_id, "in" if is_entrada else "out", strict=True)
        except _StockRuleError as e:
            raise InsufficientStockForMovementError(str(e))
        # A priced entry line moves the weighted average cost (its price per base unit); a line without a price enters
        # at the current cost. Computed BEFORE the quantity is added - see update_average_cost.
        if is_entrada and purchase_price > 0:
            await update_average_cost(db, company_id, product, base_quantity, purchase_price / factor)
        stock = await _get_or_create_stock_row(db, company_id, product.id, warehouse_id)
        if is_entrada:
            stock.quantity = float(stock.quantity) + base_quantity
        else:
            if float(stock.quantity) < base_quantity:
                raise InsufficientStockForMovementError(f"Stock insuficiente para {product.name}")
            stock.quantity = float(stock.quantity) - base_quantity

        db.add(StockMovement(
            company_id=company_id, fiscal_period_id=posting_period.id, product_id=product.id, warehouse_id=warehouse_id,
            movement_type=ledger_type, quantity=base_quantity,
            reason=description, reference=f"{movement_type.code}{movement_date.year}/{next_number}",
        ))

        line_objects.append(StockMovementDocumentLine(
            product_id=product.id,
            product_code_snapshot=product.code,
            product_name_snapshot=product.name,
            unit_snapshot=unit_code,
            sale_unit_id=line_sale_unit_id,
            unit_factor=factor,
            quantity=quantity,
            purchase_price=purchase_price,
            sale_price=sale_price,
            line_total=line_total,
        ))

    document = StockMovementDocument(
        company_id=company_id,
        fiscal_period_id=posting_period.id,
        movement_type_id=movement_type_id,
        warehouse_id=warehouse_id,
        supplier_id=supplier_id,
        series=f"{movement_type.code}{movement_date.year}",
        number=next_number,
        movement_date=movement_date,
        description=description,
        total_quantity=round(total_quantity, 3),
        total_value=round(total_value, 2),
    )
    db.add(document)
    await db.flush()

    for line in line_objects:
        line.document_id = document.id
        db.add(line)

    await db.commit()
    await db.refresh(document)
    return document


class MovementDocumentNotFoundError(Exception):
    pass


async def get_movement_document_with_lines(db: AsyncSession, company_id: uuid.UUID, document_id: uuid.UUID):
    doc_result = await db.execute(select(StockMovementDocument).where(StockMovementDocument.id == document_id, StockMovementDocument.company_id == company_id))
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise MovementDocumentNotFoundError("Movimento nao encontrado")
    lines_result = await db.execute(select(StockMovementDocumentLine).where(StockMovementDocumentLine.document_id == document_id))
    lines = list(lines_result.scalars().all())
    return document, lines


async def list_movement_documents(db: AsyncSession, company_id: uuid.UUID, limit: int = 50, offset: int = 0) -> list[StockMovementDocument]:
    result = await db.execute(
        select(StockMovementDocument)
        .where(StockMovementDocument.company_id == company_id)
        .order_by(StockMovementDocument.created_at.desc())
        .limit(limit).offset(offset)
    )
    return list(result.scalars().all())


class InvalidExcelFileError(Exception):
    pass


# "Unidade" (optional): the code of one of the product's units (SC...) - empty = its base unit; older 4-column files stay valid.
EXCEL_HEADERS = ["Codigo", "Quantidade", "Preco Compra", "Preco Venda", "Unidade"]


def generate_movement_excel_template() -> bytes:
    """Blank Excel template for automatic Entrada/Saida import - one row per product."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimento"
    ws.append(EXCEL_HEADERS)
    ws.append(["PROD-001", 10, 100.00, 150.00, ""])
    for col_idx, width in enumerate([16, 14, 16, 16, 12], start=1):
        ws.column_dimensions[chr(64 + col_idx)].width = width
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
