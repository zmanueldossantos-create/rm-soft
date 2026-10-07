"""
Shared pytest fixtures for the test suite.
Uses a dedicated Postgres database (erp_agt_test, same container as dev -
see DATABASE_URL in .env) so tests never touch real data. Tables are
created once per test session from the current SQLAlchemy models (not
via Alembic replay); all tables are truncated before each test for
isolation, since our service layer commits directly (no savepoint
wrapping) - simplest way to get a clean slate every time.

Each test gets its OWN engine (function-scoped) rather than a shared one,
to avoid the classic "attached to a different loop" error that comes from
sharing an asyncpg connection pool across pytest-asyncio's per-test event
loops (see: never override the event_loop fixture, and never share an
async engine across fixture scopes wider than the loop that created it).
"""
import uuid
from datetime import date

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base
from app.core.security import hash_password
import app.models  # noqa: F401 - ensures every model is registered on Base.metadata

from app.models.company import Company
from app.models.fiscal_regime import FiscalRegime
from app.models.module import Module
from app.models.company_module import CompanyModule
from app.models.activity import Activity
from app.models.warehouse import Warehouse
from app.models.vat import VAT
from app.models.country import Country
from app.models.vat_code import VatCode
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.legal_vat_rate import LegalVatRate
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.company_payment_method_preference import CompanyPaymentMethodPreference
from app.models.product import Product, ProductType
from app.models.user import User, UserRole
from app.models.fiscal_year import FiscalYear
from app.models.fiscal_period import FiscalPeriod
from app.models.document_type import DocumentType
import importlib.util as _ilu
import pathlib as _pathlib


def _load_document_type_rules() -> dict:
    """
    The rules of the official document types, from the migrations that define them - dynamic, so a future
    migration is picked up automatically without editing this fixture.

    l8b5c1e46f30 exposes the base RULES dict (one entry per document type code, with the columns it added).
    Any later migration that adjusts a rule may expose RULES_OVERRIDES = {code: {field: value}}; every
    versions/*.py file is scanned (order does not matter - overrides are applied on top of the base RULES,
    last file wins on a given (code, field) if more than one ever touches the same one) and merged in.
    """
    versions_dir = _pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
    base_path = next(versions_dir.glob("l8b5c1e46f30_*.py"))
    spec = _ilu.spec_from_file_location("document_type_rules_migration", base_path)
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    rules = {code: dict(fields) for code, fields in module.RULES.items()}

    for path in sorted(versions_dir.glob("*.py")):
        if path == base_path:
            continue
        spec = _ilu.spec_from_file_location(path.stem, path)
        module = _ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        overrides = getattr(module, "RULES_OVERRIDES", None)
        if not overrides:
            continue
        for code, fields in overrides.items():
            rules.setdefault(code, {}).update(fields)
    return rules


DOCUMENT_TYPE_RULES = _load_document_type_rules()
from app.models.point_of_sale import PointOfSale

TEST_DATABASE_URL = "postgresql+asyncpg://erp_user:erp_password@localhost:5436/erp_agt_test"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """
    Drops and recreates every table once per test session, using a
    short-lived engine of its own - schema must be rebuilt from the
    CURRENT models each run, since create_all() alone never alters an
    already-existing table (e.g. a newly added column would silently be
    missing otherwise).
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def test_engine():
    """A fresh engine per test - avoids sharing a connection pool across different tests' event loops."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(test_engine, setup_database):
    """Truncates every table before each test, children-first, for a clean slate."""
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield


@pytest_asyncio.fixture
async def db(test_engine):
    session_maker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def company_with_essentials(db):
    """
    Creates a ready-to-use Company with: Regime Geral (all VAT rates),
    the 3 VAT rates, a central Warehouse, a Module + Activity (with its
    own point-of-sale Warehouse) and a GESTOR user - everything most
    service-level tests need, in one fixture.
    """
    regime = FiscalRegime(name="Regime Geral (teste)", allows_nor=True, allows_red=True, allows_ise=True)
    db.add(regime)
    await db.flush()

    company = Company(
        name=f"Empresa Teste {uuid.uuid4().hex[:8]}",
        nif="5000000000",
        email=f"{uuid.uuid4().hex[:8]}@teste.co.ao",
        phone_number=f"+244{uuid.uuid4().int % 900000000 + 900000000}",
        fiscal_regime_id=regime.id,
    )
    db.add(company)
    await db.flush()

    # The official exemption motive of the exempt test articles: an exempt article cannot be sold without one.
    country = Country(code="AO", name="Angola")
    db.add(country)
    await db.flush()
    exemption_m11 = VatCode(code="M11", name="Isento nos termos da al\u00ednea b) do n\u00ba1 do artigo 12.\u00ba do CIVA",
                            rate=0, country_id=country.id, valid_from=date(2021, 1, 1))
    db.add(exemption_m11)
    await db.flush()
    # The base unit of the test articles: every article has one.
    unit_un = (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.code == "UN"))).scalar_one_or_none()
    if unit_un is None:
        unit_un = UnitOfMeasureCatalog(code="UN", name="Unidade")
        db.add(unit_un)
        await db.flush()
    vat_ise = VAT(company_id=company.id, name="Isento", rate=0, tax_category="ISE")
    vat_red = VAT(company_id=company.id, name="Taxa reduzida", rate=5, tax_category="RED")
    vat_nor = VAT(company_id=company.id, name="Taxa normal", rate=14, tax_category="NOR")
    db.add_all([vat_ise, vat_red, vat_nor])

    pm_numerario = PaymentMethodCatalog(code="NU", name="Numerario", is_cash=True)
    pm_mb = PaymentMethodCatalog(code="MB", name="Referencia Multicaixa", is_cash=False)
    db.add_all([pm_numerario, pm_mb])
    await db.flush()
    db.add_all([
        CompanyPaymentMethodPreference(company_id=company.id, payment_method_id=pm_numerario.id, available_at_pos=True),
        CompanyPaymentMethodPreference(company_id=company.id, payment_method_id=pm_mb.id, available_at_pos=True),
    ])

    central_warehouse = Warehouse(company_id=company.id, name="Armazem Principal")
    db.add(central_warehouse)
    await db.flush()

    module = Module(name=f"Modulo Teste {uuid.uuid4().hex[:8]}")
    db.add(module)
    await db.flush()

    company_module = CompanyModule(company_id=company.id, module_id=module.id, is_enabled=True)
    db.add(company_module)

    activity_warehouse = Warehouse(company_id=company.id, name="Atividade - Ponto de Venda")
    db.add(activity_warehouse)
    await db.flush()

    activity = Activity(
        company_id=company.id, module_id=module.id, warehouse_id=activity_warehouse.id,
        name="Atividade Teste",
    )
    db.add(activity)
    await db.flush()  # get activity.id before creating its default POS

    default_pos = PointOfSale(company_id=company.id, activity_id=activity.id, name="Caixa Teste", is_default=True)
    db.add(default_pos)

    gestor = User(
        company_id=company.id, full_name="Gestor Teste",
        phone_number=f"+244{uuid.uuid4().int % 900000000 + 900000000}",
        password_hash=hash_password("Teste@2026"), role=UserRole.GESTOR,
    )
    db.add(gestor)

    year = FiscalYear(company_id=company.id, year=date.today().year, status="ABERTO")
    db.add(year)
    await db.flush()

    period = FiscalPeriod(company_id=company.id, fiscal_year_id=year.id, month=date.today().month, status="ABERTO")
    db.add(period)

    # Platform-wide DocumentType catalog - invoice creation looks up "FT" (and other
    # InvoiceType-mapped codes) here; get-or-create since the catalog is shared, not
    # company-scoped, and other fixtures/tests may have already seeded it.
    existing_ft = (await db.execute(select(DocumentType).where(DocumentType.code == "FT"))).scalar_one_or_none()
    if existing_ft is None:
        db.add(DocumentType(code="FT", name="Fatura", area="FACTURACAO", electronic_eligible=True, **DOCUMENT_TYPE_RULES["FT"]))
    existing_fr = (await db.execute(select(DocumentType).where(DocumentType.code == "FR"))).scalar_one_or_none()
    if existing_fr is None:
        db.add(DocumentType(code="FR", name="Fatura/Recibo", area="FACTURACAO", electronic_eligible=True, **DOCUMENT_TYPE_RULES["FR"]))
    existing_nc = (await db.execute(select(DocumentType).where(DocumentType.code == "NC"))).scalar_one_or_none()
    if existing_nc is None:
        db.add(DocumentType(code="NC", name="Nota de Credito", area="FACTURACAO", electronic_eligible=True, **DOCUMENT_TYPE_RULES["NC"]))
    existing_nd = (await db.execute(select(DocumentType).where(DocumentType.code == "ND"))).scalar_one_or_none()
    if existing_nd is None:
        db.add(DocumentType(code="ND", name="Nota de Debito", area="FACTURACAO", electronic_eligible=True, **DOCUMENT_TYPE_RULES["ND"]))
    existing_rc = (await db.execute(select(DocumentType).where(DocumentType.code == "RC"))).scalar_one_or_none()
    if existing_rc is None:
        db.add(DocumentType(code="RC", name="Recibo", area="TESOURARIA", electronic_eligible=True, **DOCUMENT_TYPE_RULES["RC"]))
    existing_fp = (await db.execute(select(DocumentType).where(DocumentType.code == "FP"))).scalar_one_or_none()
    if existing_fp is None:
        db.add(DocumentType(code="FP", name="Fatura Pro-forma", area="FACTURACAO", electronic_eligible=False, is_fiscal=False, **DOCUMENT_TYPE_RULES["FP"]))

    await db.commit()
    await db.refresh(company)
    await db.refresh(activity)
    await db.refresh(central_warehouse)
    await db.refresh(activity_warehouse)
    await db.refresh(vat_nor)
    await db.refresh(vat_red)
    await db.refresh(vat_ise)
    await db.refresh(gestor)
    await db.refresh(default_pos)

    return {
        "company": company,
        "central_warehouse": central_warehouse,
        "activity": activity,
        "activity_warehouse": activity_warehouse,
        "pos": default_pos,
        "vat_nor": vat_nor,
        "vat_red": vat_red,
        "vat_ise": vat_ise,

        "exemption_m11": exemption_m11,
        "unit_un": unit_un,
        "gestor": gestor,
        "pm_numerario": pm_numerario,
        "pm_mb": pm_mb,
    }


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _capability_enforcement_off_by_default(monkeypatch):
    """The suite tests business logic, not the sector separation: force ENFORCE_CAPABILITIES off
    whatever the developer's .env says (tests/test_capability_enforcement.py turns it on where it
    is the subject)."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "ENFORCE_CAPABILITIES", False)


@pytest_asyncio.fixture
async def legal_vat_rates(db):
    """The legal VAT rates catalog as migration o8r5s0t49e71 seeds it: companies receive their rates from it."""
    rates = [
        LegalVatRate(tax_category="ISE", name="Isento", rate=0),
        LegalVatRate(tax_category="RED", name="Taxa reduzida", rate=5),
        LegalVatRate(tax_category="NOR", name="Taxa normal", rate=14),
    ]
    db.add_all(rates)
    await db.commit()
    return rates
