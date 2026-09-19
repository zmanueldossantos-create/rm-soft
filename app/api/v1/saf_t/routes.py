"""
SAF-T export routes - GESTOR only ("Modo Fatura" monthly export, section 4.2).
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.services.saf_t_export_service import export_saf_t_for_period, CompanyNotFoundError

router = APIRouter(prefix="/api/v1/saf-t", tags=["saf-t"])


@router.get("/export")
async def export_saf_t(
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("saf_t:export")),
):
    """
    Generates and returns the SAF-T AuditFile XML for one calendar month
    - "Modo Fatura" (section 4.2), submitted manually to the AGT portal.
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mes invalido")

    try:
        xml_bytes = await export_saf_t_for_period(db, current_user.company_id, year, month)
    except CompanyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    filename = f"SAFT_{current_user.company_id}_{year}{month:02d}.xml"
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
