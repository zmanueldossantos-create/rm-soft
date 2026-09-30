"""
Stock movement document routes (Entrada/Saida) - scoped to the caller's company, same
multi-tenant isolation pattern as invoices.
"""
import uuid
from datetime import date as date_type
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.movement_document import (
    MovementDocumentCreateRequest, MovementDocumentResponse, MovementDocumentDetailResponse,
)
from app.services.fiscal_period_service import PeriodClosedError
from app.services.movement_document_service import (
    create_stock_movement_document,
    get_movement_document_with_lines,
    list_movement_documents,
    MovementTypeNotConfiguredError,
    MovementWarehouseNotFoundError,
    MovementProductNotFoundError,
    EmptyMovementError,
    InsufficientStockForMovementError,
    MovementDocumentNotFoundError,
    generate_movement_excel_template,
    InvalidExcelFileError,
)

router = APIRouter(prefix="/api/v1/movements", tags=["movements"])


@router.post("", response_model=MovementDocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_movement_document(
    payload: MovementDocumentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("movements:create")),
):
    try:
        document = await create_stock_movement_document(
            db,
            company_id=current_user.company_id,
            movement_type_id=payload.movement_type_id,
            warehouse_id=payload.warehouse_id,
            lines_input=[l.model_dump() for l in payload.lines],
            movement_date=payload.movement_date,
            description=payload.description,
            supplier_id=payload.supplier_id,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MovementTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except MovementWarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except MovementProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EmptyMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except InsufficientStockForMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return document


@router.get("", response_model=list[MovementDocumentResponse])
async def get_movement_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("movements:view")),
):
    return await list_movement_documents(db, current_user.company_id)


@router.get("/excel-template")
async def download_movement_excel_template(
    current_user: User = Depends(require_permission("movements:import")),
):
    """Downloads a blank Excel template for automatic Entrada/Saida import."""
    content = generate_movement_excel_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=modelo_movimento.xlsx"},
    )




@router.get("/{document_id}", response_model=MovementDocumentDetailResponse)
async def get_movement_document_detail(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("movements:view")),
):
    try:
        document, lines = await get_movement_document_with_lines(db, current_user.company_id, document_id)
    except MovementDocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return MovementDocumentDetailResponse(
        **MovementDocumentResponse.model_validate(document).model_dump(),
        lines=[l for l in lines],
    )
