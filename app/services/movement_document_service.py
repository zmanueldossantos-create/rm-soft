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
from app.services.stock_service import _get_or_create_stock_row, _stock_rule, InsufficientStockError as _StockRuleError
from app.services.fiscal_period_service import ensure_period_open, PeriodClosedError
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
) -> StockMovementDocument:
    """
    lines_input items: {product_id, quantity, purchase_price, sale_price}
    """
    movement_date = movement_date or date.today()

    await ensure_period_open(db, company_id, movement_date)

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

        unit_code = None
        if product.unit_of_measure_id:
            unit_result = await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.id == product.unit_of_measure_id))
            unit = unit_result.scalar_one_or_none()
            unit_code = unit.code if unit else None

        quantity = float(line_input["quantity"])
        purchase_price = float(line_input.get("purchase_price", 0) or 0)
        sale_price = float(line_input.get("sale_price", 0) or 0)
        line_value_price = purchase_price if is_entrada else sale_price
        line_total = round(quantity * line_value_price, 2)

        total_quantity += quantity
        total_value += line_total

        # Update the real stock quantity + write the audit ledger row - see module docstring.
        try:
            await _stock_rule(db, product.id, warehouse_id, "in" if is_entrada else "out", strict=True)
        except _StockRuleError as e:
            raise InsufficientStockForMovementError(str(e))
        stock = await _get_or_create_stock_row(db, company_id, product.id, warehouse_id)
        if is_entrada:
            stock.quantity = float(stock.quantity) + quantity
        else:
            if float(stock.quantity) < quantity:
                raise InsufficientStockForMovementError(f"Stock insuficiente para {product.name}")
            stock.quantity = float(stock.quantity) - quantity

        db.add(StockMovement(
            company_id=company_id, product_id=product.id, warehouse_id=warehouse_id,
            movement_type=ledger_type, quantity=quantity,
            reason=description, reference=f"{movement_type.code}{movement_date.year}/{next_number}",
        ))

        line_objects.append(StockMovementDocumentLine(
            product_id=product.id,
            product_code_snapshot=product.code,
            product_name_snapshot=product.name,
            unit_snapshot=unit_code,
            quantity=quantity,
            purchase_price=purchase_price,
            sale_price=sale_price,
            line_total=line_total,
        ))

    document = StockMovementDocument(
        company_id=company_id,
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


EXCEL_HEADERS = ["Codigo", "Quantidade", "Preco Compra", "Preco Venda"]


def generate_movement_excel_template() -> bytes:
    """Blank Excel template for automatic Entrada/Saida import - one row per product."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimento"
    ws.append(EXCEL_HEADERS)
    ws.append(["PROD-001", 10, 100.00, 150.00])
    for col_idx, width in enumerate([16, 14, 16, 16], start=1):
        ws.column_dimensions[chr(64 + col_idx)].width = width
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


async def parse_movement_excel(db: AsyncSession, company_id: uuid.UUID, file_bytes: bytes) -> list[dict]:
    """Reads an uploaded Excel file (Codigo/Quantidade/Preco Compra/Preco Venda columns)
    and resolves each product code into a product_id, returning the same lines_input
    shape create_stock_movement_document expects."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
    except Exception:
        raise InvalidExcelFileError("Ficheiro Excel invalido ou corrompido")

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise InvalidExcelFileError("Ficheiro Excel vazio")

    lines_input = []
    for row in rows[1:]:  # skip header row
        if row is None or all(v is None for v in row):
            continue
        code = str(row[0]).strip() if row[0] is not None else None
        if not code:
            continue
        quantity = float(row[1]) if len(row) > 1 and row[1] is not None else 0
        purchase_price = float(row[2]) if len(row) > 2 and row[2] is not None else 0
        sale_price = float(row[3]) if len(row) > 3 and row[3] is not None else 0

        product_result = await db.execute(select(Product).where(Product.code == code, Product.company_id == company_id))
        product = product_result.scalar_one_or_none()
        if product is None:
            raise MovementProductNotFoundError(f"Produto com codigo \'{code}\' nao encontrado")

        lines_input.append({
            "product_id": product.id,
            "quantity": quantity,
            "purchase_price": purchase_price,
            "sale_price": sale_price,
        })

    if not lines_input:
        raise EmptyMovementError("O ficheiro Excel nao contem linhas validas")

    return lines_input
