"""Guias (point 1): GR to a customer, GT between warehouses, GD back to a supplier - issue, read, print, cancel."""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.company import Company
from app.models.user import User
from app.services.fiscal_period_service import PeriodClosedError
from app.services.goods_movement_service import (
    GoodsMovementError, GoodsMovementNotFoundError, cancel_goods_movement, create_goods_movement, get_goods_movement,
    invoice_goods_movements, list_goods_movements,
)

router = APIRouter(prefix="/api/v1/guias", tags=["guias"])

ERRORS = {GoodsMovementError: status.HTTP_422_UNPROCESSABLE_ENTITY, PeriodClosedError: status.HTTP_409_CONFLICT,
          GoodsMovementNotFoundError: status.HTTP_404_NOT_FOUND}


class GuiaLineInput(BaseModel):
    product_id: uuid.UUID
    sale_unit_id: uuid.UUID | None = None
    quantity: float
    unit_price: float | None = None  # empty: the proposed price (sale price of a GR, cost of a GT or GD)


class GuiaCreateRequest(BaseModel):
    movement_type: str  # GR, GT, GD
    origin_warehouse_id: uuid.UUID
    start_time: datetime | None = None
    customer_id: uuid.UUID | None = None  # GR
    destination_warehouse_id: uuid.UUID | None = None  # GT
    supplier_id: uuid.UUID | None = None  # GD
    purchase_invoice_id: uuid.UUID | None = None  # GD, optional
    load_address: str | None = None
    unload_address: str | None = None
    vehicle_plate: str | None = None
    notes: str | None = None
    lines: list[GuiaLineInput]


class GuiaCancelRequest(BaseModel):
    reason: str


class GuiaInvoiceRequest(BaseModel):
    guia_ids: list[uuid.UUID]  # guias de remessa of one customer
    activity_id: uuid.UUID  # the activity whose FT series the invoice takes


def _http(e: Exception) -> HTTPException:
    return HTTPException(status_code=ERRORS[type(e)], detail=str(e))


@router.get("")
async def get_guias(movement_type: str | None = None, guia_status: str | None = None, date_from: date | None = None,
                    date_to: date | None = None, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("guias:view"))):
    return await list_goods_movements(db, current_user.company_id, movement_type, guia_status, date_from, date_to)


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_guia(payload: GuiaCreateRequest, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("guias:manage"))):
    try:
        movement = await create_goods_movement(
            db, current_user.company_id, current_user.id, payload.movement_type, payload.origin_warehouse_id,
            [l.model_dump() for l in payload.lines], payload.start_time, payload.customer_id, payload.supplier_id,
            payload.purchase_invoice_id, payload.destination_warehouse_id, payload.load_address,
            payload.unload_address, payload.vehicle_plate, payload.notes,
        )
        return await get_goods_movement(db, current_user.company_id, movement.id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.post("/invoice", status_code=status.HTTP_201_CREATED)
async def post_invoice_guias(payload: GuiaInvoiceRequest, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("guias:invoice"))):
    """One Fatura for the selected guias de remessa of a customer - the goods already left the stock with them."""
    try:
        invoice = await invoice_goods_movements(db, current_user.company_id, payload.guia_ids, payload.activity_id)
    except tuple(ERRORS) as e:
        raise _http(e)
    return {"id": invoice.id, "reference": f"FT {invoice.series}/{invoice.number}", "total": float(invoice.total)}


@router.get("/{guia_id}")
async def get_guia(guia_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(require_permission("guias:view"))):
    try:
        return await get_goods_movement(db, current_user.company_id, guia_id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.post("/{guia_id}/cancel")
async def post_cancel_guia(guia_id: uuid.UUID, payload: GuiaCancelRequest, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("guias:manage"))):
    try:
        await cancel_goods_movement(db, current_user.company_id, guia_id, current_user.id, payload.reason)
        return await get_goods_movement(db, current_user.company_id, guia_id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.get("/{guia_id}/pdf")
async def get_guia_pdf(guia_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("guias:view"))):
    from app.services.cash_report_service import _company_dict
    from app.utils.guia_pdf import generate_guia_pdf
    try:
        data = await get_goods_movement(db, current_user.company_id, guia_id)
    except tuple(ERRORS) as e:
        raise _http(e)
    company = (await db.execute(select(Company).where(Company.id == current_user.company_id))).scalar_one()
    pdf = generate_guia_pdf(data, _company_dict(company))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{data["reference"].replace("/", "-").replace(" ", "_")}.pdf"'})
