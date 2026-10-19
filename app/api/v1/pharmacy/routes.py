"""
Farmácia routes - the context of the product form (is the Farmácia on, the forms, the medicine exemption motive), the
GESTOR's list of pharmaceutical forms, and the registers (the trace of a lot, the receitas, the psicotrópicos). Scoped to
the caller's company.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.company import Company
from app.models.user import User
from app.services.pharmacy_register_service import (
    LotNotFoundError, RegisterError, list_prescriptions, psychotropic_register, trace_lot,
)
from app.services.pharmacy_service import (
    MedicineError, PharmaceuticalFormAlreadyExistsError, PharmaceuticalFormNotFoundError, create_form, list_forms,
    pharmacy_context, toggle_form, update_form,
)

router = APIRouter(prefix="/api/v1/pharmacy", tags=["pharmacy"])


class PharmaceuticalFormRequest(BaseModel):
    name: str


class PharmaceuticalFormResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/context")
async def get_pharmacy_context(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:view")),
):
    """Is the Farmácia on for the company, its pharmaceutical forms and the exemption motive proposed for a medicine."""
    return await pharmacy_context(db, current_user.company_id)


@router.get("/forms", response_model=list[PharmaceuticalFormResponse])
async def get_forms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:view")),
):
    return await list_forms(db, current_user.company_id)


@router.post("/forms", response_model=PharmaceuticalFormResponse, status_code=status.HTTP_201_CREATED)
async def post_form(
    payload: PharmaceuticalFormRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:manage")),
):
    try:
        return await create_form(db, current_user.company_id, payload.name)
    except PharmaceuticalFormAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MedicineError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/forms/{form_id}", response_model=PharmaceuticalFormResponse)
async def patch_form(
    form_id: uuid.UUID,
    payload: PharmaceuticalFormRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:manage")),
):
    try:
        return await update_form(db, current_user.company_id, form_id, payload.name)
    except PharmaceuticalFormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PharmaceuticalFormAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MedicineError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/forms/{form_id}/toggle-status", response_model=PharmaceuticalFormResponse)
async def patch_form_status(
    form_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:manage")),
):
    try:
        return await toggle_form(db, current_user.company_id, form_id)
    except PharmaceuticalFormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Registers (livraison 3): the trace of a lot, the registo de receitas, the registo de psicotrópicos


async def _company(db: AsyncSession, company_id: uuid.UUID) -> dict:
    from app.services.cash_report_service import _company_dict
    return _company_dict((await db.execute(select(Company).where(Company.id == company_id))).scalar_one())


def _pdf(content: bytes, name: str) -> Response:
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


def _register_error(e: RegisterError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND if isinstance(e, LotNotFoundError) else status.HTTP_422_UNPROCESSABLE_ENTITY,
                         detail=str(e))


@router.get("/lots/{lot_id}/trace")
async def get_lot_trace(lot_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("stock:lot_trace"))):
    """Where one lot came from and where it went (every sector: a recall)."""
    try:
        return await trace_lot(db, current_user.company_id, lot_id)
    except RegisterError as e:
        raise _register_error(e)


@router.get("/lots/{lot_id}/trace/pdf")
async def get_lot_trace_pdf(lot_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("stock:lot_trace"))):
    from app.utils.pharmacy_pdf import generate_lot_trace_pdf
    try:
        data = await trace_lot(db, current_user.company_id, lot_id)
    except RegisterError as e:
        raise _register_error(e)
    return _pdf(generate_lot_trace_pdf(data, await _company(db, current_user.company_id)),
                "Lote_" + (data["lot_number"] or "sem_numero"))


@router.get("/prescriptions")
async def get_prescriptions(date_from: date, date_to: date, special: bool | None = None, q: str | None = None,
                            db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("pharmacy:registers"))):
    """The registo de receitas of a period."""
    try:
        return await list_prescriptions(db, current_user.company_id, date_from, date_to, special, q)
    except RegisterError as e:
        raise _register_error(e)


@router.get("/prescriptions/pdf")
async def get_prescriptions_pdf(date_from: date, date_to: date, special: bool | None = None, q: str | None = None,
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("pharmacy:registers"))):
    from app.utils.pharmacy_pdf import generate_prescriptions_pdf
    try:
        entries = await list_prescriptions(db, current_user.company_id, date_from, date_to, special, q)
    except RegisterError as e:
        raise _register_error(e)
    return _pdf(generate_prescriptions_pdf(entries, await _company(db, current_user.company_id), date_from, date_to),
                f"Registo_receitas_{date_from}_{date_to}")


@router.get("/psychotropics")
async def get_psychotropics(date_from: date, date_to: date, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("pharmacy:registers"))):
    """The registo de psicotrópicos e estupefacientes of a period."""
    try:
        return await psychotropic_register(db, current_user.company_id, date_from, date_to)
    except RegisterError as e:
        raise _register_error(e)


@router.get("/psychotropics/pdf")
async def get_psychotropics_pdf(date_from: date, date_to: date, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("pharmacy:registers"))):
    from app.utils.pharmacy_pdf import generate_psychotropics_pdf
    try:
        products = await psychotropic_register(db, current_user.company_id, date_from, date_to)
    except RegisterError as e:
        raise _register_error(e)
    return _pdf(generate_psychotropics_pdf(products, await _company(db, current_user.company_id), date_from, date_to),
                f"Registo_psicotropicos_{date_from}_{date_to}")
