"""
API pública, step 2: the catalogue (products, services, categories: only what is on sale, prices with and without
VAT, stock) and the customers (read, look up by NIF, create without duplicates). Always the key's company only.
"""
import contextlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.database import get_db
from app.main import app
from app.models.company import Company
from app.models.customer import FINAL_CONSUMER_NIF, Customer
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.product_sale_unit import ProductSaleUnit
from app.models.service import ProductServiceStatus, Service
from app.models.stock import Stock
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services import api_key_service as keys

API = "/api/public/v1"


@pytest.fixture
async def api(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    keys._calls.clear()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session

    @contextlib.asynccontextmanager
    async def journal_session():
        yield db
    monkeypatch.setattr(keys, "journal_session", journal_session)

    async def key_with(*scopes):
        plain = (await keys.create_key(db, company_id, ctx["gestor"].id, "Site", list(scopes)))["key"]
        return {"X-API-Key": plain}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {**ctx, "client": client, "key_with": key_with}
    app.dependency_overrides.pop(get_db, None)


async def _catalogue(db, ctx):
    company_id = ctx["company"].id
    bread = ProductCategory(company_id=company_id, name="Pão")
    closed = ProductCategory(company_id=company_id, name="Matérias", not_available_sales=True)
    db.add_all([bread, closed])
    await db.flush()
    unit_un = (await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.code == "UN"))).scalar_one()
    box = UnitOfMeasureCatalog(code="CX" + uuid.uuid4().hex[:3], name="Caixa")
    db.add(box)
    await db.flush()
    p = dict(company_id=company_id, vat_id=ctx["vat_nor"].id, unit_of_measure_id=unit_un.id)
    baguete = Product(code="BAG", name="Baguete", price=100, category_id=bread.id, barcode="5601", **p)
    rice = Product(code="ARZ", name="Arroz 1kg", price=1000, vat_id=ctx["vat_red"].id,
                   **{k: v for k, v in p.items() if k != "vat_id"})
    hidden = [Product(code="INT", name="Detergente interno", price=500, internal_use_only=True, **p),
              Product(code="AWT", name="Sem preço", price=0, awaiting_price=True, **p),
              Product(code="OFF", name="Inativo", price=10, is_active=False, **p),
              Product(code="BLK", name="Bloqueado", price=10, status=ProductServiceStatus.BLOQUEADO, **p),
              Product(code="FAR", name="Farinha", price=300, category_id=closed.id, **p)]
    no_stock_control = Product(code="SAC", name="Saco", price=20, managed_by_stock=False, **p)
    db.add_all([baguete, rice, no_stock_control, *hidden])
    await db.flush()
    db.add_all([Stock(company_id=company_id, product_id=baguete.id, warehouse_id=ctx["central_warehouse"].id, quantity=40),
                Stock(company_id=company_id, product_id=baguete.id, warehouse_id=ctx["activity_warehouse"].id, quantity=2.5),
                ProductSaleUnit(company_id=company_id, product_id=rice.id, unit_of_measure_id=box.id, factor=10,
                                price=9500, barcode="5609")])
    room = Service(company_id=company_id, code="QDUP", name="Quarto duplo", price=25000, vat_id=ctx["vat_nor"].id,
                   duration_minutes=1440)
    db.add_all([room, Service(company_id=company_id, code="SP", name="Sem preço", price=None, vat_id=ctx["vat_nor"].id)])
    await db.commit()
    return {"baguete": baguete, "rice": rice, "room": room, "hidden": hidden}


async def test_products_only_what_is_on_sale_with_vat_and_stock(api, db):
    data = await _catalogue(db, api)
    client, h = api["client"], await api["key_with"]("catalog")
    page = (await client.get(API + "/catalog/products", headers=h)).json()
    assert [p["code"] for p in page["items"]] == ["ARZ", "BAG", "SAC"] and page["total"] == 3
    baguete = next(p for p in page["items"] if p["code"] == "BAG")
    assert baguete["price"] == 100 and baguete["vat_rate"] == 14 and baguete["price_with_vat"] == 114
    assert baguete["stock"] == 42.5 and baguete["category"] == "Pão" and baguete["unit"] == "UN"
    rice = next(p for p in page["items"] if p["code"] == "ARZ")
    assert rice["price_with_vat"] == 1050 and rice["stock"] == 0
    assert rice["sale_units"][0]["factor"] == 10 and rice["sale_units"][0]["price"] == 9500
    assert next(p for p in page["items"] if p["code"] == "SAC")["stock"] is None  # no stock control

    one = (await client.get(f"{API}/catalog/products/{data['baguete'].id}", headers=h)).json()
    assert sorted(w["quantity"] for w in one["stock_by_warehouse"]) == [2.5, 40]
    for hidden in data["hidden"]:
        assert (await client.get(f"{API}/catalog/products/{hidden.id}", headers=h)).status_code == 404

    # filters: search, category, barcode (also a sale unit's), paging
    assert [p["code"] for p in (await client.get(API + "/catalog/products?search=arroz", headers=h)).json()["items"]] == ["ARZ"]
    assert [p["code"] for p in (await client.get(API + "/catalog/products?category=pão", headers=h)).json()["items"]] == ["BAG"]
    assert [p["code"] for p in (await client.get(API + "/catalog/products?barcode=5609", headers=h)).json()["items"]] == ["ARZ"]
    second = (await client.get(API + "/catalog/products?page=2&page_size=2", headers=h)).json()
    assert [p["code"] for p in second["items"]] == ["SAC"] and second["total"] == 3
    later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert (await client.get(API + "/catalog/products", params={"updated_since": later}, headers=h)).json()["total"] == 0
    assert (await client.get(API + "/catalog/products?page_size=500", headers=h)).status_code == 422

    categories = (await client.get(API + "/catalog/categories", headers=h)).json()
    assert [c["name"] for c in categories] == ["Pão"]  # the one closed to sales is not shown


async def test_services(api, db):
    data = await _catalogue(db, api)
    client, h = api["client"], await api["key_with"]("catalog")
    page = (await client.get(API + "/catalog/services", headers=h)).json()
    assert [s["code"] for s in page["items"]] == ["QDUP"]  # without a price: not on sale
    assert page["items"][0]["price_with_vat"] == 28500 and page["items"][0]["duration_minutes"] == 1440
    assert (await client.get(f"{API}/catalog/services/{data['room'].id}", headers=h)).json()["name"] == "Quarto duplo"


async def test_the_catalogue_needs_its_right_and_stays_in_its_company(api, db):
    await _catalogue(db, api)
    client = api["client"]
    only_customers = await api["key_with"]("customers")
    refused = await client.get(API + "/catalog/products", headers=only_customers)
    assert refused.status_code == 403 and "Catálogo" in refused.json()["detail"]
    # another company's key sees none of these
    other = Company(name="Outra Lda", nif="5000999779", email="o3@empresa.ao", phone_number="+244923000997")
    db.add(other)
    await db.flush()
    plain = (await keys.create_key(db, other.id, None, "Deles", ["catalog"]))["key"]
    assert (await client.get(API + "/catalog/products", headers={"X-API-Key": plain})).json()["total"] == 0
    baguete = (await db.execute(select(Product).where(Product.code == "BAG"))).scalar_one()
    assert (await client.get(f"{API}/catalog/products/{baguete.id}", headers={"X-API-Key": plain})).status_code == 404


async def test_customers_create_find_and_no_duplicate(api, db):
    client, h = api["client"], await api["key_with"]("customers")
    created = await client.post(API + "/customers", headers=h, json={
        "name": "  Maria   Domingos ", "nif": "004567890la041", "phone": "+244923456789", "email": "Maria@Mail.ao"})
    assert created.status_code == 201, created.text
    maria = created.json()
    assert maria["name"] == "Maria Domingos" and maria["nif"] == "004567890LA041" and maria["email"] == "maria@mail.ao"
    assert maria["person_type"] == "FISICA" and maria["code"]
    stored = await db.get(Customer, uuid.UUID(maria["id"]))
    assert stored.company_id == api["company"].id and "Site" in stored.description

    again = await client.post(API + "/customers", headers=h, json={"name": "Maria D.", "nif": "004567890LA041"})
    assert again.status_code == 409 and again.json()["id"] == maria["id"]
    generic = await client.post(API + "/customers", headers=h, json={"name": "X", "nif": FINAL_CONSUMER_NIF})
    assert generic.status_code == 422
    bad = await client.post(API + "/customers", headers=h, json={"name": "X", "nif": "12", "phone": "abc"})
    assert bad.status_code == 422 and {e["loc"][-1] for e in bad.json()["detail"]} == {"nif", "phone"}

    found = (await client.get(API + "/customers", params={"nif": "004567890la041"}, headers=h)).json()
    assert found["total"] == 1 and found["items"][0]["id"] == maria["id"]
    assert (await client.get(API + "/customers?email=MARIA@mail.ao", headers=h)).json()["total"] == 1
    assert (await client.get(f"{API}/customers/{maria['id']}", headers=h)).json()["phone"] == "+244923456789"
    assert (await client.get(f"{API}/customers/{uuid.uuid4()}", headers=h)).status_code == 404

    catalog_only = await api["key_with"]("catalog")
    assert (await client.post(API + "/customers", headers=catalog_only, json={"name": "Y", "nif": "123456789"})).status_code == 403


async def test_a_revoked_key_is_written_in_the_journal(api, db):
    client = api["client"]
    created = await keys.create_key(db, api["company"].id, api["gestor"].id, "Site antigo", ["catalog"])
    await keys.revoke_key(db, api["company"].id, uuid.UUID(created["id"]))
    refused = await client.get(API + "/catalog/products", headers={"X-API-Key": created["key"]})
    assert refused.status_code == 401
    journal = await keys.read_journal(db, api["company"].id)
    assert journal[0]["key_name"] == "Site antigo (revogada)" and journal[0]["status_code"] == 401
