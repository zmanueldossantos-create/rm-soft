"""
Application entry point.
Behavior (CORS, deployment mode) is driven by app.core.config.
See specification v7, section 2.3 (hybrid Local / SaaS architecture).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import get_settings
import app.models  # loads all SQLAlchemy models before any request (avoids foreign key errors)
from app.api.v1.auth.routes import router as auth_router
from app.api.v1.admin.routes import router as admin_router
from app.api.v1.products.routes import router as products_router
from app.api.v1.vat.routes import router as vat_router
from app.api.v1.customers.routes import router as customers_router
from app.api.v1.fiscal_periods.routes import router as fiscal_router
from app.api.v1.invoices.routes import router as invoices_router
from app.api.v1.movements.routes import router as movements_router
from app.api.v1.company.routes import router as company_router
from app.api.v1.stock.routes import router as stock_router
from app.api.v1.saf_t.routes import router as saf_t_router
from app.api.v1.dashboard.routes import router as dashboard_router
from app.api.v1.activities.routes import router as activities_router
from app.api.v1.bookings.routes import router as bookings_router
from app.api.v1.open_accounts.routes import router as open_accounts_router
from app.api.v1.hotel.routes import router as hotel_router
from app.api.v1.internal_consumption.routes import router as internal_consumption_router
from app.api.v1.suppliers.routes import router as suppliers_router
from app.api.v1.permissions.routes import router as permissions_router
from app.api.v1.pos.routes import router as pos_router
from app.api.v1.catalogs.routes import router as catalogs_router
from app.api.v1.product_categories.routes import router as product_categories_router
from app.api.v1.service_types.routes import router as service_types_router
from app.api.v1.services.routes import router as services_router
from app.api.v1.establishments.routes import router as establishments_router
from app.api.v1.document_series.routes import router as document_series_router
from app.api.v1.tesouraria.routes import router as tesouraria_router
from app.api.v1.moedeiro.routes import router as moedeiro_router
from app.core.database import AsyncSessionLocal
from app.models.company import Company
from app.services.permission_service import seed_permission_catalog, seed_default_role_permissions
from sqlalchemy import select as sa_select

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="7.0.0",
)


@app.on_event("startup")
async def seed_permissions_on_startup() -> None:
    """
    Idempotent - keeps the platform-wide Permission catalog and each
    existing company's default RolePermission grants up to date on every
    boot. Safe to run repeatedly (see permission_service's docstrings) -
    new companies get their own seed at creation time (company_service),
    this only backfills companies that existed before the permission
    system shipped.
    """
    async with AsyncSessionLocal() as db:
        await seed_permission_catalog(db)
        companies_result = await db.execute(sa_select(Company.id))
        for (company_id,) in companies_result.all():
            await seed_default_role_permissions(db, company_id)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(products_router)
app.include_router(vat_router)
app.include_router(customers_router)
app.include_router(fiscal_router)
app.include_router(invoices_router)
app.include_router(movements_router)
app.include_router(company_router)
app.include_router(stock_router)
app.include_router(saf_t_router)
app.include_router(dashboard_router)
app.include_router(activities_router)
app.include_router(bookings_router)
app.include_router(open_accounts_router)
app.include_router(hotel_router)
app.include_router(internal_consumption_router)
app.include_router(suppliers_router)
app.include_router(permissions_router)
app.include_router(pos_router)
app.include_router(catalogs_router)
app.include_router(product_categories_router)
app.include_router(service_types_router)
app.include_router(services_router)
app.include_router(establishments_router)
app.include_router(document_series_router)
app.include_router(tesouraria_router)
app.include_router(moedeiro_router)

# Serve uploaded files (company logos, etc.) - local storage for Phase 1.
os.makedirs("uploads/logos", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
async def root():
    """Health check route - confirms the API is responding."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "deployment_mode": settings.DEPLOYMENT_MODE,
    }


@app.get("/health")
async def health():
    """Health check for supervision (SaaS mode notably)."""
    return {"status": "healthy"}






