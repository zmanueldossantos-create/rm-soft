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
from app.services.sector_service import seed_sector_catalog, ModuleNotAvailableError
from app.services.product_service import ExemptionReasonRequiredError as ProductExemptionReasonRequiredError
from sqlalchemy import select as sa_select

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="RM System - Conforme RGIFT 2.0 (AGT)",
    version="7.0.0",
)


@app.exception_handler(ModuleNotAvailableError)
async def module_not_available_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# Only the create routes of products / services translated these errors: an update of an exempt (0%)
# article without a reason - or of a product without a VAT rate - ended as a 500. Same answer as the
# create routes: 422 with the message.
async def _unprocessable_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"detail": str(exc)})


app.add_exception_handler(ProductExemptionReasonRequiredError, _unprocessable_handler)


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
        await seed_sector_catalog(db)
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


# A stock rule refusal (warehouse frozen, product without stock) that no route catches itself: a clear 409, never a 500.
from fastapi import Request as _Request  # noqa: E402
from fastapi.responses import JSONResponse as _JSONResponse  # noqa: E402
from app.services.stock_service import StockBlockedError as _StockBlockedError  # noqa: E402


@app.exception_handler(_StockBlockedError)
async def _stock_blocked_handler(request: _Request, exc: _StockBlockedError):
    return _JSONResponse(status_code=409, content={"detail": str(exc)})

# Request validation errors (a quantity typed "1," in a number field...) in Portuguese, one place for every route: the field
# is named, the line too when the error comes from a list; our own validators already speak Portuguese and pass as they are.
# The response keeps its shape (422, a list of {type, loc, msg}) - the screens read msg (utils/errors.js).
from fastapi.exceptions import RequestValidationError as _RequestValidationError  # noqa: E402

_FIELD_LABELS = {
    "quantity": "Quantidade", "price": "Preco", "unit_price": "Preco unitario", "amount": "Valor",
    "discount_percent": "Desconto", "discount_global_percent": "Desconto global", "factor": "Fator",
    "purchase_price": "Preco de compra", "sale_price": "Preco de venda", "barcode": "Codigo de barras",
    "code": "Codigo", "name": "Nome", "phone_number": "Telefone", "email": "Email", "nif": "NIF",
    "business_date": "Data", "due_date": "Data de vencimento", "payment_date": "Data de pagamento",
    "product_id": "Produto", "service_id": "Servico", "customer_id": "Cliente", "rate": "Taxa",
}
_TYPE_MESSAGES = {
    "float_parsing": "valor numerico invalido", "float_type": "valor numerico invalido",
    "decimal_parsing": "valor numerico invalido", "decimal_type": "valor numerico invalido",
    "int_parsing": "numero inteiro invalido", "int_type": "numero inteiro invalido",
    "missing": "campo obrigatorio", "uuid_parsing": "identificador invalido", "uuid_type": "identificador invalido",
    "date_parsing": "data invalida", "date_from_datetime_parsing": "data invalida", "date_type": "data invalida",
    "bool_parsing": "valor invalido", "bool_type": "valor invalido",
    "string_too_short": "texto demasiado curto", "string_too_long": "texto demasiado longo", "string_type": "texto invalido",
    "greater_than": "deve ser maior que {gt}", "greater_than_equal": "deve ser maior ou igual a {ge}",
    "less_than": "deve ser menor que {lt}", "less_than_equal": "deve ser menor ou igual a {le}",
    "json_invalid": "pedido invalido", "enum": "valor nao permitido",
}


def _pt_validation_message(error: dict) -> str:
    if error.get("type") == "value_error":
        return str(error.get("msg", ""))  # our own validators: already Portuguese ("Value error, ..." stripped on screen)
    loc = [part for part in error.get("loc", ()) if part not in ("body", "query", "path")]
    field = next((part for part in reversed(loc) if isinstance(part, str)), "")
    line = next((part for part in loc if isinstance(part, int)), None)
    text = _TYPE_MESSAGES.get(error.get("type", ""), "valor invalido")
    try:
        text = text.format(**(error.get("ctx") or {}))
    except (KeyError, IndexError, ValueError):
        pass
    label = _FIELD_LABELS.get(field, field)
    prefix = (f"Linha {line + 1} - " if line is not None else "") + (f"{label}: " if label else "")
    return prefix + text


@app.exception_handler(_RequestValidationError)
async def _pt_validation_handler(request: _Request, exc: _RequestValidationError):
    detail = [
        {"type": e.get("type"), "loc": [str(part) for part in e.get("loc", ())], "msg": _pt_validation_message(e)}
        for e in exc.errors()
    ]
    return _JSONResponse(status_code=422, content={"detail": detail})



# A fiscal period refusal (closed, soft-closed for an automatic operation...) that no route catches itself: a clear 409.
from app.services.fiscal_period_service import PeriodClosedError as _PeriodClosedError  # noqa: E402


@app.exception_handler(_PeriodClosedError)
async def _period_closed_handler(request: _Request, exc: _PeriodClosedError):
    return _JSONResponse(status_code=409, content={"detail": str(exc)})


# A stock quantity that cannot be taken (unit not the product's, decimal quantity in a whole unit): a clear 422.
from app.services.stock_service import StockQuantityError as _StockQuantityError  # noqa: E402


@app.exception_handler(_StockQuantityError)
async def _stock_quantity_handler(request: _Request, exc: _StockQuantityError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})


# The base unit of a product with a history cannot change: a clear 409.
from app.services.product_service import BaseUnitLockedError as _BaseUnitLockedError  # noqa: E402


@app.exception_handler(_BaseUnitLockedError)
async def _base_unit_locked_handler(request: _Request, exc: _BaseUnitLockedError):
    return _JSONResponse(status_code=409, content={"detail": str(exc)})


# A payment method used against its direction (money in / out): a clear 422.
from app.services.invoice_service import PaymentMethodNotAllowedError as _PaymentMethodNotAllowedError  # noqa: E402


@app.exception_handler(_PaymentMethodNotAllowedError)
async def _payment_method_direction_handler(request: _Request, exc: _PaymentMethodNotAllowedError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})


# A refusal of the database no route caught: a duplicate (unique index, case-insensitive on catalogs) or a missing /
# still-used related record - a clear 409 instead of a 500.
from sqlalchemy.exc import IntegrityError as _IntegrityError  # noqa: E402


@app.exception_handler(_IntegrityError)
async def _integrity_handler(request: _Request, exc: _IntegrityError):
    text = str(exc.orig)
    if 'UniqueViolation' in repr(exc.orig) or 'duplicate key' in text or 'unique constraint' in text:
        return _JSONResponse(status_code=409, content={"detail": "Ja existe um registo com este codigo ou nome."})
    return _JSONResponse(status_code=409, content={"detail": "Operacao recusada: dados relacionados em falta ou ainda em uso."})


# A point of sale used against its state (inactive, or deactivated with an open session): a clear 409.
from app.services.point_of_sale_service import PosStateError as _PosStateError  # noqa: E402


@app.exception_handler(_PosStateError)
async def _pos_state_handler(request: _Request, exc: _PosStateError):
    return _JSONResponse(status_code=409, content={"detail": str(exc)})


# A series asked for a year the AGT does not allow: a clear 422.
from app.services.document_series_service import SeriesYearNotAllowedError as _SeriesYearNotAllowedError  # noqa: E402


@app.exception_handler(_SeriesYearNotAllowedError)
async def _series_year_handler(request: _Request, exc: _SeriesYearNotAllowedError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})


# An exempt article without a valid exemption motive cannot be issued: a clear 422.
from app.services.invoice_service import MissingExemptionReasonError as _MissingExemptionReasonError  # noqa: E402


@app.exception_handler(_MissingExemptionReasonError)
async def _missing_exemption_handler(request: _Request, exc: _MissingExemptionReasonError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})


# An exemption motive the SAF-T would reject: a clear 422 in the catalog screen.
from app.services.catalog_service import ExemptionMotiveInvalidError as _ExemptionMotiveInvalidError  # noqa: E402


@app.exception_handler(_ExemptionMotiveInvalidError)
async def _exemption_motive_handler(request: _Request, exc: _ExemptionMotiveInvalidError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})


# A regime whose settings contradict each other: a clear 422.
from app.services.fiscal_regime_service import FiscalRegimeInvalidError as _FiscalRegimeInvalidError  # noqa: E402


@app.exception_handler(_FiscalRegimeInvalidError)
async def _fiscal_regime_handler(request: _Request, exc: _FiscalRegimeInvalidError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})


# A VAT rate or exemption motive an article cannot carry under its company's regime: a clear 422.
from app.services.vat_rule_service import ArticleVatError as _ArticleVatError  # noqa: E402


@app.exception_handler(_ArticleVatError)
async def _article_vat_handler(request: _Request, exc: _ArticleVatError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})


# A product or service saved without a base unit: a clear 422.
from app.services.product_service import ArticleUnitRequiredError as _ArticleUnitRequiredError  # noqa: E402


@app.exception_handler(_ArticleUnitRequiredError)
async def _article_unit_handler(request: _Request, exc: _ArticleUnitRequiredError):
    return _JSONResponse(status_code=422, content={"detail": str(exc)})
