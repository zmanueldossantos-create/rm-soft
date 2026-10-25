"""
The public site (rmsystem.co.ao): what it shows, read from the database - no login.

Only on the RM SOFT platform (PUBLIC_SITE=true): on a client's server these routes answer 404, as if they did not exist.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import SECTORS
from app.core.config import get_settings
from app.core.database import get_db
from app.core.plan_features import LIMITS, OPTIONS, TRIAL_DAYS
from app.models.plan import Plan
from app.schemas.demo_request import DemoRequestCreate
from app.services.demo_request_service import DemoRequestError, create_demo_request
from app.services.platform_settings_service import get_or_create_platform_settings

router = APIRouter(prefix="/api/v1/public", tags=["public"])


def _public_site_only() -> None:
    if not get_settings().PUBLIC_SITE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _price(value) -> float | None:
    return float(value) if value is not None else None


@router.get("/site", dependencies=[Depends(_public_site_only)])
async def get_site(response: Response, db: AsyncSession = Depends(get_db)):
    """Everything the site shows, in one call: the plans on sale, the sectors, the contacts, the AGT validation."""
    plans = (await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order, Plan.name))).scalars().all()
    platform = await get_or_create_platform_settings(db)
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "plans": [{
            "id": str(plan.id),
            "name": plan.name,
            "description": plan.description,
            "description_en": plan.description_en,
            "prices": {
                "MENSAL": _price(plan.price_monthly), "TRIMESTRAL": _price(plan.price_quarterly),
                "SEMESTRAL": _price(plan.price_semiannual), "ANUAL": _price(plan.price_annual),
                "VITALICIA": _price(plan.price_lifetime),
            },
            "maintenance_percent": _price(plan.maintenance_percent),
            "limits": {code: (plan.limits or {}).get(code) for code in LIMITS},  # null: unlimited
            "options": [code for code in OPTIONS if code in (plan.options or [])],
            "is_popular": plan.is_popular,
        } for plan in plans],
        "limits": [{"code": lim.code, "label": lim.label} for lim in LIMITS.values()],
        "options": [{"code": o.code, "label": o.label, "description": o.description} for o in OPTIONS.values()],
        "sectors": [{"code": s.code, "name": s.name, "description": s.description, "ready": s.ready} for s in SECTORS],
        "trial_days": TRIAL_DAYS,
        "contacts": {"whatsapp": platform.site_whatsapp, "email": platform.site_email},
        "agt_validation_number": platform.software_validation_number,
        "vendor_tax_id": platform.vendor_tax_id,
    }


def _client_ip(request: Request) -> str | None:
    """The visitor's address: the first of X-Forwarded-For behind the proxy (Caddy), else the connection's."""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return (forwarded or (request.client.host if request.client else "") or None)


@router.post("/demo-requests", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_public_site_only)])
async def post_demo_request(payload: DemoRequestCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """«Pedir demonstração»: kept for the SUPER_ADMIN («Pedidos») - a robot's (hidden field filled) as DESCARTADO."""
    try:
        await create_demo_request(db, payload.model_dump(), _client_ip(request))
    except DemoRequestError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS if e.too_many
                            else status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return {"ok": True}
