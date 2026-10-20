"""
SaaS livraison 2 - isolation between client companies (cahier des charges v7 §2.5: "suite de tests dédiée vérifiant
qu'aucune requête ne peut retourner de données d'un autre tenant, avant toute mise en production du mode SaaS").

Two companies, A and B, each with a bit of everything (documents, customers, stock, tills, bookings, accounts...).
The GESTOR of A - every permission - then calls EVERY route of the application:
- each read: nothing of B may appear in the answer (nor one of B's files);
- each change of one object (an id in the address) given B's object: refused;
- each change whose form refers to other objects (customer, product, till...): with ONE of them replaced by B's -
  refused every time.
The routes are found from the application itself: a new route is checked without touching this test. What it cannot
check (an object it cannot give, a form it cannot fill) is printed, so a gap never goes unnoticed.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    Activity, AiConversation, Booking, CashMovement, CashMovementReason, CashSession, CompanyBankAccount,
    ConsumptionReasonCatalog, Customer, CustomerBankAccountLink, DocumentSeries, Establishment, FiscalPeriod,
    FiscalYear, GoodsMovement, Invoice, KitchenOrder, OpenAccount, OpenAccountLine, PharmaceuticalForm,
    PointOfSale, Product, ProductCategory, ProductSaleUnit, PurchaseInvoice, Resource, ResourceTypeCatalog,
    Service, ServiceType, StockInventory, StockLot, StockMovementDocument, Supplier, SupplierPayment, User, Warehouse,
    WarehouseLocation,
)
from app.models.ai_pending_action import AiPendingAction
from app.models.bank import Bank
from app.models.cash_movement import CashMovementType
from app.models.company import Company
from app.models.company_module import CompanyModule
from app.models.company_payment_method_preference import CompanyPaymentMethodPreference
from app.models.currency import Currency
from app.models.denomination import Denomination, DenominationType
from app.models.document_type import DocumentType
from app.models.legal_vat_rate import LegalVatRate
from app.models.movement_type import MovementDirection, MovementType
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.payment_term import PaymentTerm
from app.models.product import ProductType
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.user import UserRole
from app.models.vat import VAT
from app.services.booking_service import create_booking
from app.services.cash_movement_service import create_cash_movement
from app.services.cash_session_service import open_session
from app.services.customer_service import create_customer
from app.services.establishment_service import create_establishment
from app.services.goods_movement_service import create_goods_movement
from app.services.invoice_service import create_invoice
from app.services.open_account_service import add_line, open_account
from app.services.permission_service import seed_permission_catalog
from app.services.purchase_invoice_service import register_purchase_invoice
from app.services.resource_service import create_resource
from app.services.stock_inventory_service import create_inventory
from app.services.stock_service import receive_stock
from app.services.supplier_payment_service import create_supplier_payment
from app.services.supplier_service import create_supplier

# Platform routes (SUPER_ADMIN, no company) and routes without company data
SKIPPED_PREFIXES = ("/api/v1/admin", "/api/v1/catalogs", "/api/v1/channels", "/api/v1/help", "/api/v1/auth/tenant",
                    "/api/v1/auth/domain-check", "/api/v1/auth/login", "/api/v1/auth/refresh")

# Which object goes in each id - of an address (parameter, part of the path) or of a form (field, "") -> model
OBJECTS = {
    ("pos_id", ""): PointOfSale, ("activity_id", ""): Activity, ("conversation_id", ""): AiConversation,
    ("user_id", ""): User, ("booking_id", ""): Booking, ("account_id", "bank-accounts"): CompanyBankAccount,
    ("account_id", "open-accounts"): OpenAccount, ("reason_id", "consumption-reasons"): ConsumptionReasonCatalog,
    ("reason_id", "tesouraria"): CashMovementReason, ("customer_id", ""): Customer,
    ("link_id", ""): CustomerBankAccountLink, ("series_id", ""): DocumentSeries,
    ("establishment_id", ""): Establishment, ("period_id", ""): FiscalPeriod, ("fiscal_year_id", ""): FiscalYear,
    ("guia_id", ""): GoodsMovement, ("item_id", "pro-forma"): Invoice, ("invoice_id", "/invoices/"): Invoice,
    ("invoice_id", "/purchases/"): PurchaseInvoice, ("line_id", ""): OpenAccountLine, ("order_id", ""): KitchenOrder,
    ("document_id", ""): StockMovementDocument, ("form_id", ""): PharmaceuticalForm, ("lot_id", ""): StockLot,
    ("session_id", ""): CashSession, ("category_id", ""): ProductCategory, ("product_id", ""): Product,
    ("unit_id", ""): ProductSaleUnit, ("resource_type_id", ""): ResourceTypeCatalog, ("resource_id", ""): Resource,
    ("service_type_id", ""): ServiceType, ("service_id", ""): Service, ("inventory_id", ""): StockInventory,
    ("location_id", ""): WarehouseLocation, ("warehouse_id", ""): Warehouse, ("supplier_id", ""): Supplier,
    ("payment_id", ""): SupplierPayment, ("movement_id", ""): CashMovement, ("action_id", ""): AiPendingAction,
    # form fields with another name
    ("origin_warehouse_id", ""): Warehouse, ("destination_warehouse_id", ""): Warehouse,
    ("source_pos_id", ""): PointOfSale, ("destination_pos_id", ""): PointOfSale,
    ("purchase_invoice_id", ""): PurchaseInvoice, ("company_bank_account_id", ""): CompanyBankAccount,
    ("bank_account_id", ""): CompanyBankAccount, ("sale_unit_id", ""): ProductSaleUnit, ("vat_id", ""): VAT,
    ("cash_session_id", ""): CashSession, ("reference_invoice_id", ""): PurchaseInvoice,
    ("pharmaceutical_form_id", ""): PharmaceuticalForm, ("consumption_reason_id", ""): ConsumptionReasonCatalog,
    ("ingredient_id", ""): Product, ("target_account_id", ""): OpenAccount, ("origin_invoice_id", ""): Invoice,
    ("invoice_id", ""): Invoice, ("finished_product_id", ""): Product, ("refund_pos_id", ""): PointOfSale,
    ("cash_pos_id", ""): PointOfSale, ("reference_invoice_id", "/invoices"): Invoice,
    ("reason_id", "internal-consumption"): ConsumptionReasonCatalog,
}
# Two warehouses where a form needs two different ones
WAREHOUSE_PAIRS = {"from_warehouse_id": "central_warehouse", "to_warehouse_id": "activity_warehouse",
                   "origin_warehouse_id": "central_warehouse", "warehouse_id": "central_warehouse"}
# Plain fields that need a value the application accepts
# (a list: the first one the field accepts; a function: a new value each time, for a field that must be unique)
STRINGS = {"loss_category": "QUEBRA", "reason": "Ajuste de teste", "movement_type": ["GR", "ENTRADA_EXTERNA"],
           "count_type": "FECHO", "credit_note_reason": "ANL", "credit_note_cause": "Teste de isolamento",
           "supplier_document": lambda: "FT T/" + uuid.uuid4().hex[:6], "code": lambda: "T" + uuid.uuid4().hex[:6],
           "name": lambda: "Teste " + uuid.uuid4().hex[:6],
           "document_date": date.today().isoformat(), "label": "Teste", "unload_address": "Rua de teste"}


def _plain(name: str, accepted: list | None = None):
    value = STRINGS[name]
    if callable(value):
        return value()
    options = value if isinstance(value, list) else [value]
    if accepted is None:
        return options[0]
    return next((o for o in options if o in accepted), accepted[0])
# Words in an address, not ids
WORDS = {"decision": "confirm", "action": "start", "channel": "TELEGRAM"}
# Ids of the platform's shared catalogs: each company keeps its own preference about them - not a company's data
SHARED = {"document_type_id", "payment_method_id"}
CATALOG_FIELDS = {"bank_id": Bank, "currency_id": Currency, "payment_method_id": PaymentMethodCatalog,
                  "unit_of_measure_id": UnitOfMeasureCatalog, "document_type_id": DocumentType,
                  "payment_term_id": PaymentTerm, "denomination_id": Denomination, "movement_type_id": MovementType}


async def _company_b(db, ctx) -> dict:
    """Company B, set up like company A (the shared fixture): its activity, till, warehouses, period, gestor."""
    a = ctx["company"]
    company = Company(name="Empresa B Lda", nif="5417888001", email="b@b.ao", phone_number="+244923888001",
                      fiscal_regime_id=a.fiscal_regime_id, subdomain="empresa-b")
    db.add(company)
    await db.flush()
    vat_nor = VAT(company_id=company.id, name="Taxa normal", rate=14, tax_category="NOR")
    central = Warehouse(company_id=company.id, name="Armazem Principal B")
    shop = Warehouse(company_id=company.id, name="Loja B")
    db.add_all([vat_nor, central, shop,
                CompanyPaymentMethodPreference(company_id=company.id, payment_method_id=ctx["pm_numerario"].id),
                CompanyPaymentMethodPreference(company_id=company.id, payment_method_id=ctx["pm_mb"].id),
                CompanyModule(company_id=company.id, module_id=ctx["activity"].module_id, is_enabled=True)])
    await db.flush()
    activity = Activity(company_id=company.id, module_id=ctx["activity"].module_id, warehouse_id=shop.id, name="Loja B")
    db.add(activity)
    await db.flush()
    pos = PointOfSale(company_id=company.id, activity_id=activity.id, name="Caixa B", is_default=True)
    gestor = User(company_id=company.id, full_name="Gestor B", phone_number="+244923888002",
                  password_hash=hash_password("Teste@2026"), role=UserRole.GESTOR)
    year = FiscalYear(company_id=company.id, year=date.today().year, status="ABERTO")
    db.add_all([pos, gestor, year])
    await db.flush()
    db.add(FiscalPeriod(company_id=company.id, fiscal_year_id=year.id, month=date.today().month, status="ABERTO"))
    await db.commit()
    return {**ctx, "company": company, "gestor": gestor, "activity": activity, "pos": pos, "vat_nor": vat_nor,
            "central_warehouse": central, "activity_warehouse": shop}


async def _fill(db, ctx, tag: str) -> None:
    """A bit of everything in one company (tag: A or B, to keep names and codes apart)."""
    c, gestor, activity, pos = ctx["company"].id, ctx["gestor"], ctx["activity"], ctx["pos"]
    n = "1" if tag == "A" else "2"
    customer = await create_customer(db, c, f"Cliente {tag}", "541799900" + n)
    supplier = await create_supplier(db, c, f"Fornecedor {tag}", nif="541799901" + n)
    category = ProductCategory(company_id=c, name=f"Categoria {tag}")
    db.add(category)
    await db.flush()
    product = Product(company_id=c, code=f"P{tag}1", name=f"Produto {tag}", vat_id=ctx["vat_nor"].id, price=1000,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                      category_id=category.id)
    service = Service(company_id=c, code=f"S{tag}1", name=f"Serviço {tag}", price=500, vat_id=ctx["vat_nor"].id)
    box = UnitOfMeasureCatalog(code=f"CX{tag}", name=f"Caixa {tag}")
    db.add_all([product, service, box])
    await db.commit()
    db.add_all([
        ProductSaleUnit(company_id=c, product_id=product.id, unit_of_measure_id=box.id, factor=6, price=5500),
        ServiceType(company_id=c, name=f"Tipo {tag}"), ConsumptionReasonCatalog(company_id=c, name=f"Limpeza {tag}"),
        CashMovementReason(company_id=c, name=f"Despesa {tag}", direction=MovementDirection.SAIDA),
        PharmaceuticalForm(company_id=c, name=f"Comprimido {tag}"),
        WarehouseLocation(company_id=c, warehouse_id=ctx["central_warehouse"].id, code="A1", description=f"Prateleira {tag}"),
        AiConversation(company_id=c, user_id=gestor.id, title=f"Conversa {tag}", channel="APP"),
    ])
    await db.commit()
    await receive_stock(db, c, product.id, 50, warehouse_id=ctx["activity_warehouse"].id)
    await receive_stock(db, c, product.id, 50, warehouse_id=ctx["central_warehouse"].id)

    await create_invoice(db, c, activity.id, customer_id=customer.id, invoice_type="FACTURA",
                         lines_input=[{"product_id": product.id, "quantity": 1}])
    await open_session(db, c, pos.id, gestor, 1000)
    await create_establishment(db, c, f"SEDE{tag}", f"Sede {tag}")
    room_type = ResourceTypeCatalog(company_id=c, name=f"Quarto {tag}")
    db.add(room_type)
    await db.commit()
    room = await create_resource(db, c, activity.id, room_type.id, f"Quarto {tag}1")
    start = datetime.now(timezone.utc) + timedelta(days=2)
    await create_booking(db, c, room.id, gestor.id, start, start + timedelta(days=1), customer_id=customer.id)
    account = await open_account(db, c, activity.id, pos.id, gestor.id, f"Mesa {tag}")
    await add_line(db, c, account.id, gestor.id, 1, product_id=product.id)
    nor = (await db.execute(select(LegalVatRate).where(LegalVatRate.tax_category == "NOR"))).scalars().first()
    purchase = await register_purchase_invoice(
        db, c, gestor.id, supplier.id, f"FT {tag}/1", date.today(),
        [{"product_id": product.id, "description": "Compra", "quantity": 1, "unit_price": 100, "legal_vat_rate_id": nor.id}],
        stock_entry=True, warehouse_id=ctx["central_warehouse"].id)  # with its stock entry document
    await create_supplier_payment(db, c, gestor, supplier.id, [{"purchase_invoice_id": purchase.id, "amount": 50}],
                                  ctx["pm_mb"].id)
    income = CashMovementReason(company_id=c, name=f"Entrada {tag}", direction=MovementDirection.ENTRADA)
    db.add(income)
    await db.commit()
    await create_cash_movement(db, c, CashMovementType.ENTRADA_EXTERNA, gestor, 100, destination_pos_id=pos.id,
                               reason_id=income.id)
    bank, currency = Bank(acronym=f"B{tag}", full_name=f"Banco {tag}"), Currency(code=f"C{tag}X", name=f"Moeda {tag}")
    db.add_all([bank, currency])
    await db.flush()
    bank_account = CompanyBankAccount(company_id=c, bank_id=bank.id, account_number="123", iban="AO06000", currency_id=currency.id)
    db.add(bank_account)
    await db.flush()
    db.add(CustomerBankAccountLink(customer_id=customer.id, company_bank_account_id=bank_account.id))
    db.add(AiPendingAction(company_id=c, user_id=gestor.id, kind="ISSUE_DOCUMENT", payload={}, summary={},
                           expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)))
    await db.commit()
    await create_goods_movement(db, c, gestor.id, "GR", ctx["central_warehouse"].id,
                                [{"product_id": product.id, "quantity": 1}], customer_id=customer.id,
                                unload_address=f"Rua do Cliente {tag}")
    await create_inventory(db, c, ctx["central_warehouse"].id, gestor.id)


async def _objects(db, company_id) -> tuple[set[str], dict]:
    """Every id of a company's rows (tables with a company_id), and one object of it per model of OBJECTS."""
    every: set[str] = {str(company_id)}
    for table in Base.metadata.sorted_tables:
        if "company_id" in table.c and "id" in table.c:
            every |= {str(i) for i in (await db.execute(select(table.c.id).where(table.c.company_id == company_id))).scalars()}
    one = {}
    for model in set(OBJECTS.values()):
        query = select(model.id)
        if hasattr(model, "company_id"):
            query = query.where(model.company_id == company_id)
        elif model is CustomerBankAccountLink:
            query = query.join(Customer, Customer.id == model.customer_id).where(Customer.company_id == company_id)
        elif model is OpenAccountLine:
            query = query.join(OpenAccount, OpenAccount.id == model.account_id).where(OpenAccount.company_id == company_id)
        one[model] = (await db.execute(query.limit(1))).scalar_one_or_none()
    return every, one


def _object_for(name: str, path: str, objects: dict):
    for (field, part), model in OBJECTS.items():
        if field == name and part in path:
            return objects.get(model)
    return None


def _example(schema: dict, defs: dict, name: str, values: dict):
    """A plausible value for a JSON-schema field: the company's own object for an id field, a catalog row for a
    catalog field, a simple value otherwise."""
    if "$ref" in schema:
        return _example(defs[schema["$ref"].split("/")[-1]], defs, name, values)
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        return _example(options[0], defs, name, values) if options else None
    if "enum" in schema:
        return _plain(name, schema["enum"]) if name in STRINGS else schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        props, required = schema.get("properties", {}), set(schema.get("required", []))
        made = {k: _example(v, defs, k, values) for k, v in props.items()
                if k in required or k in values or k in STRINGS}
        if made.get("product_id") and made.get("service_id"):  # a line is a product OR a service
            made.pop("product_id" if values.get("_prefer") == "service_id" else "service_id")
        return made
    if kind == "array":
        item = _example(schema.get("items", {}), defs, name[:-1] if name.endswith("s") else name, values)
        return [item] if item is not None else []
    if kind == "string" and name in STRINGS:
        return _plain(name)
    if kind == "string":
        if schema.get("format") == "uuid":
            return str(values.get(name) or uuid.uuid4())
        if schema.get("format") == "date":
            return date.today().isoformat()
        if schema.get("format") == "date-time":  # an end always after its start (a clock may give twice the same instant)
            hours = {"starts_at": 24 * 30, "ends_at": 24 * 30 + 2}.get(name, 0)
            return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        return "x"
    if kind in ("integer", "number"):
        return 1
    return False if kind == "boolean" else None


def _schema(route: APIRoute):
    model = route.body_field.type_ if route.body_field is not None else None
    if model is None or not hasattr(model, "model_json_schema"):
        return None
    schema = model.model_json_schema()
    return schema, schema.get("$defs", {})


def _id_fields(schema: dict, defs: dict, values: dict) -> list[str]:
    """The id fields of a form (top level and its lines) that name a company object."""
    found: list[str] = []

    def walk(s, depth=0):
        if depth > 6:
            return
        if "$ref" in s:
            return walk(defs[s["$ref"].split("/")[-1]], depth + 1)
        for option in s.get("anyOf", []):
            walk(option, depth + 1)
        if s.get("type") == "array":
            walk(s.get("items", {}), depth + 1)
        for k, v in s.get("properties", {}).items():
            if k in values and k not in found:
                found.append(k)
            walk(v, depth + 1)
    walk(schema)
    return found


@pytest.mark.asyncio
async def test_company_a_never_reaches_company_b(db, company_with_essentials, legal_vat_rates, monkeypatch):
    # the same rules in both modes; local mode here so the address plays no part (the .env of a machine may say saas)
    monkeypatch.setattr(get_settings(), "DEPLOYMENT_MODE", "local")
    ctx_a = company_with_essentials
    await seed_permission_catalog(db)
    currency = Currency(code="AOA", name="Kwanza")
    db.add(currency)
    await db.flush()
    db.add_all([MovementType(code="EM", name="Entrada manual", direction=MovementDirection.ENTRADA, is_auto=False),
                PaymentTerm(name="30 dias", days=30),
                Denomination(currency_id=currency.id, value=1000, denomination_type=DenominationType.NOTA)])
    await db.commit()
    db.add_all([MovementType(code="EAP", name="Entrada automática", direction=MovementDirection.ENTRADA, is_auto=True),
                DocumentType(code="GR", name="Guia de Remessa", area="FACTURACAO", is_fiscal=True, saft_section="MOVEMENTS")])
    await db.commit()
    ctx_b = await _company_b(db, ctx_a)
    await _fill(db, ctx_a, "A")
    await _fill(db, ctx_b, "B")
    company_a, company_b = ctx_a["company"].id, ctx_b["company"].id
    token = create_access_token(subject=str(ctx_a["gestor"].id), company_id=str(company_a), role="GESTOR")
    _, objects_a = await _objects(db, company_a)
    b_ids, objects_b = await _objects(db, company_b)
    assert all(objects_b[m] and objects_a[m] for m in (Invoice, Customer, OpenAccount, PurchaseInvoice, Booking, Product))

    # plain ids: a refused request rolls the session back and expires the loaded objects
    ids_a, ids_b = ({key: ctx[key].id for key in ("company", "vat_nor", *WAREHOUSE_PAIRS.values())} for ctx in (ctx_a, ctx_b))
    catalogs = {field: (await db.execute(select(model.id).order_by(model.id).limit(1) if model is not MovementType else
                                         select(model.id).where(model.is_auto.is_(False)).limit(1))).scalar_one_or_none()
                for field, model in CATALOG_FIELDS.items()}
    nor = (await db.execute(select(LegalVatRate.id).where(LegalVatRate.tax_category == "NOR"))).scalars().first()

    def values_of(objects, ctx, path: str) -> dict:
        """The form values of one company for a route: its objects (the path's own meaning first), its NOR rate,
        two different warehouses, the shared catalogs."""
        values = {field: objects.get(model) for (field, part), model in OBJECTS.items() if part == ""}
        values.update({field: objects.get(model) for (field, part), model in OBJECTS.items() if part and part in path})
        values.update({field: ctx[key] for field, key in WAREHOUSE_PAIRS.items()})
        values.update(vat_id=ctx["vat_nor"], legal_vat_rate_id=nor, company_id=ctx["company"], **catalogs)
        return {k: v for k, v in values.items() if v is not None}

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                               headers={"Authorization": "Bearer " + token})
    leaks, uncovered, crashes, untested_forms = [], [], [], []
    checked = accepted = 0

    async def references(model, value) -> int:
        """How many rows of the application refer to this object (by a foreign key to its table)."""
        total = 0
        for table in Base.metadata.sorted_tables:
            for column in table.c:
                if any(fk.column.table.name == model.__tablename__ for fk in column.foreign_keys):
                    total += (await db.execute(select(func.count()).select_from(table).where(column == value))).scalar_one()
        return total

    async def call(method, path, body, label):
        nonlocal checked, accepted
        try:
            response = await client.request(method, path, json=body if method != "GET" else None)
        except Exception as e:  # noqa: BLE001 - a crash is reported, never hides the other routes
            await db.rollback()
            crashes.append(f"{label}: {type(e).__name__}")
            return None
        checked += 1
        if 200 <= response.status_code < 300:
            accepted += 1
        return response

    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/v1")
              and not r.path.startswith(SKIPPED_PREFIXES)]
    # reads first (on untouched data), then the changes
    for reading in (True, False):
        for route in routes:
            for method in sorted(route.methods):
                if (method == "GET") != reading:
                    continue
                label = f"{method} {route.path}"
                path, missing, foreign = route.path, [], False
                for param in route.param_convertors:
                    if param in WORDS:
                        value = WORDS[param]
                    elif param in SHARED:
                        value = catalogs.get(param)
                    elif param == "company_id":
                        value = company_b
                    else:
                        value = _object_for(param, route.path, objects_b)
                    if value is None:
                        missing.append(param)
                        continue
                    foreign = foreign or (param not in WORDS and param not in SHARED)
                    path = path.replace("{" + param + "}", str(value))
                if missing:
                    uncovered.append(f"{label} ({', '.join(missing)})")
                    continue
                form = _schema(route) if method != "GET" else None
                values_a, values_b = values_of(objects_a, ids_a, route.path), values_of(objects_b, ids_b, route.path)
                values_b = {k: v for k, v in values_b.items() if k not in CATALOG_FIELDS and k != "legal_vat_rate_id"}
                body = _example(form[0], form[1], "", values_a) if form else ({} if method != "GET" else None)

                if foreign or method == "GET":
                    response = await call(method, path, body, label)
                    if response is None or not 200 <= response.status_code < 300:
                        continue
                    if method != "GET":
                        leaks.append(f"{label}: alterou um objeto da empresa B ({response.status_code})")
                    elif "json" not in response.headers.get("content-type", ""):
                        if foreign:
                            leaks.append(f"{label}: devolveu um ficheiro da empresa B")
                    elif any(i in response.text for i in b_ids):
                        leaks.append(f"{label}: mostra dados da empresa B")
                    continue

                # a change on A's own data: its form refers to A's objects - one of them replaced by B's must fail
                fields = _id_fields(form[0], form[1], values_b) if form else []
                for field in fields:
                    model = _object_for(field, route.path, {m: m for m in OBJECTS.values()}) or (
                        Warehouse if field in WAREHOUSE_PAIRS else VAT if field == "vat_id" else None)
                    if model is None:
                        continue
                    before = await references(model, values_b[field])
                    swapped = _example(form[0], form[1], "", {**values_a, field: values_b[field], "_prefer": field})
                    response = await call(method, path, swapped, f"{label} [{field} da B]")
                    # accepted AND kept: a row of the application now refers to B's object (a field ignored is fine)
                    if response is not None and 200 <= response.status_code < 300 \
                            and await references(model, values_b[field]) > before:
                        leaks.append(f"{label}: guardou {field} da empresa B ({response.status_code})")
                if fields:  # is the form valid at all with A's own objects? if not, the swap proved nothing
                    baseline = await call(method, path, body, label)
                    if baseline is None or not 200 <= baseline.status_code < 300:
                        untested_forms.append(f"{label} ({baseline.status_code if baseline is not None else 'erro'}) {baseline.text[:300] if baseline is not None else ''}")
    await client.aclose()
    app.dependency_overrides.pop(get_db, None)

    print(f"\n{checked} pedidos verificados")
    print(f"sem objeto para o endereço: {len(uncovered)}")
    for line in uncovered:
        print("  -", line)
    print(f"erros 500 (recusados, mas sem mensagem): {len(crashes)}")
    for line in crashes:
        print("  -", line)
    print(f"formulários que nem com os dados da própria empresa passam (a troca não prova nada): {len(untested_forms)}")
    for line in untested_forms:
        print("  -", line)
    print(f"aceites (a própria empresa A): {accepted}")
    assert checked > 300
    assert accepted > 80, "quase tudo recusado - o teste não prova nada (sessão recusada?)"
    assert not leaks, "Fugas entre empresas:\n" + "\n".join(leaks)
