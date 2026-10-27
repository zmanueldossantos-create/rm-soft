"""
API pública, step 3: documents. A program issues FT / FR / FP with the catalogue's prices (never its own), under the
company's series, VAT, stock and period rules; an FR is paid by a non-cash method; every issue is idempotent; the
fiscal ones go to the AGT queue; every document is read back with its lines, its AGT state and its PDF.
"""
import contextlib
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.core.database import get_db
from app.main import app
from app.models.activity import Activity
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.product import Product
from app.models.service import Service
from app.models.stock import Stock
from app.services import api_key_service as keys

API = "/api/public/v1"


@pytest.fixture
async def api(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    keys._calls.clear()
    # what is queued for the AGT - whatever the queue of this PC (AGT_QUEUE celery or base)
    sent = []
    from app.services import agt_queue

    async def record(db, invoice):
        if agt_queue.sent_to_agt(invoice):
            sent.append(str(invoice.id))
    monkeypatch.setattr(agt_queue, "queue_for_agt", record)
    monkeypatch.setattr(agt_queue, "sent_to_agt", lambda invoice: True)  # as issued in Faturação Eletrónica

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session

    @contextlib.asynccontextmanager
    async def journal_session():
        yield db
    monkeypatch.setattr(keys, "journal_session", journal_session)

    p = dict(company_id=company_id, vat_id=ctx["vat_nor"].id)
    bread = Product(code="BAG", name="Baguete", price=100, **p)
    internal = Product(code="INT", name="Interno", price=50, internal_use_only=True, **p)
    db.add_all([bread, internal])
    await db.flush()
    db.add(Stock(company_id=company_id, product_id=bread.id, warehouse_id=ctx["activity_warehouse"].id, quantity=10))
    room = Service(company_id=company_id, code="QD", name="Quarto duplo", price=20000, vat_id=ctx["vat_nor"].id)
    db.add(room)
    await db.commit()
    plain = (await keys.create_key(db, company_id, ctx["gestor"].id, "Loja online", ["documents"]))["key"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {**ctx, "client": client, "h": {"X-API-Key": plain}, "bread": bread, "internal": internal, "room": room,
               "sent": sent}
    app.dependency_overrides.pop(get_db, None)


def _with_key(api, key=None):
    return {**api["h"], "Idempotency-Key": key or str(uuid.uuid4())}


async def test_an_fr_with_the_catalogue_prices_goes_to_the_agt(api, db):
    client = api["client"]
    created = await client.post(API + "/documents", headers=_with_key(api), json={
        "type": "FR", "payment_method": "MB", "document_reference": "ENC-1001",
        "lines": [{"product_id": str(api["bread"].id), "quantity": 3, "discount_percent": 10},
                  {"service_id": str(api["room"].id), "quantity": 1}]})
    assert created.status_code == 201, created.text
    doc = created.json()
    assert doc["type"] == "FR" and doc["number"].startswith("FR ") and doc["document_reference"] == "ENC-1001"
    # the catalogue's prices: 3 x 100 - 10 % = 270, + 20 000; VAT 14 %
    assert doc["subtotal"] == 20270 and doc["vat_total"] == 2837.8 and doc["total"] == 23107.8
    lines = {l["name"]: l for l in doc["lines"]}
    assert lines["Baguete"]["unit_price"] == 100 and lines["Baguete"]["discount_percent"] == 10
    assert lines["Quarto duplo"]["unit_price"] == 20000
    assert doc["agt"]["status"] == "PENDENTE" and doc["customer"] is None
    assert api["sent"] == [doc["id"]]  # queued for the AGT
    invoice = await db.get(Invoice, uuid.UUID(doc["id"]))
    assert invoice.created_by_user_id == api["gestor"].id and invoice.cash_session_id is None
    paid = (await db.execute(select(Payment).where(Payment.invoice_id == invoice.id))).scalars().all()
    assert [float(p.amount) for p in paid] == [23107.8]
    stock = (await db.execute(select(Stock.quantity).where(Stock.product_id == api["bread"].id))).scalar_one()
    assert float(stock) == 7  # the goods left the activity's warehouse

    again = await client.get(f"{API}/documents/{doc['id']}", headers=api["h"])
    assert again.json()["number"] == doc["number"] and len(again.json()["lines"]) == 2
    pdf = await client.get(f"{API}/documents/{doc['id']}/pdf", headers=api["h"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_the_same_idempotency_key_issues_once(api, db):
    client, key = api["client"], str(uuid.uuid4())
    body = {"type": "FT", "lines": [{"product_id": str(api["bread"].id), "quantity": 1}]}
    first = await client.post(API + "/documents", headers=_with_key(api, key), json=body)
    second = await client.post(API + "/documents", headers=_with_key(api, key), json=body)
    assert first.status_code == second.status_code == 201
    assert second.json()["id"] == first.json()["id"] and second.headers["idempotent-replayed"] == "true"
    assert (await db.execute(select(func.count(Invoice.id)))).scalar_one() == 1
    other = await client.post(API + "/documents", headers=_with_key(api, key), json={**body, "type": "FP"})
    assert other.status_code == 422 and "Idempotency-Key" in other.json()["detail"]
    missing = await client.post(API + "/documents", headers=api["h"], json=body)
    assert missing.status_code == 422  # the header is required


async def test_ft_and_fp(api, db):
    client = api["client"]
    ft = (await client.post(API + "/documents", headers=_with_key(api), json={
        "type": "FT", "due_date": "2099-01-31", "lines": [{"product_id": str(api["bread"].id), "quantity": 2}]})).json()
    assert ft["type"] == "FT" and ft["amount_due"] == 228 and ft["due_date"] == "2099-01-31"
    fp = await client.post(API + "/documents", headers=_with_key(api), json={
        "type": "FP", "lines": [{"service_id": str(api["room"].id), "quantity": 2}]})
    assert fp.status_code == 201 and fp.json()["agt"] is None and fp.json()["total"] == 45600
    assert len(api["sent"]) == 1  # the FP is not fiscal: never sent

    listed = (await client.get(API + "/documents", headers=api["h"])).json()
    assert listed["total"] == 2 and "lines" not in listed["items"][0] or listed["items"][0]["lines"] is None
    only_fp = (await client.get(API + "/documents?type=fp", headers=api["h"])).json()
    assert [d["type"] for d in only_fp["items"]] == ["FP"]
    assert (await client.get(API + "/documents?type=XX", headers=api["h"])).status_code == 422


async def test_refusals(api, db):
    client = api["client"]

    async def post(body):
        return await client.post(API + "/documents", headers=_with_key(api), json=body)
    # ids read first: a refused issue rolls the shared test session back (its objects expire)
    bread, internal_id, room = str(api["bread"].id), str(api["internal"].id), str(api["room"].id)
    company_id, activity_id, module_id = api["company"].id, str(api["activity"].id), api["activity"].module_id
    no_method = await post({"type": "FR", "lines": [{"product_id": bread, "quantity": 1}]})
    assert no_method.status_code == 422 and "payment_method" in no_method.json()["detail"]
    cash = await post({"type": "FR", "payment_method": "NU", "lines": [{"product_id": bread, "quantity": 1}]})
    assert cash.status_code == 422 and "Numerário" in cash.json()["detail"]
    internal = await post({"type": "FT", "lines": [{"product_id": internal_id, "quantity": 1}]})
    assert internal.status_code == 422 and "não está à venda" in internal.json()["detail"]
    both = await post({"type": "FT", "lines": [{"product_id": bread, "service_id": room, "quantity": 1}]})
    assert both.status_code == 422
    too_many = await post({"type": "FT", "lines": [{"product_id": bread, "quantity": 50}]})
    assert too_many.status_code == 409  # 10 in stock
    stranger = await post({"type": "FT", "customer_id": str(uuid.uuid4()), "lines": [{"product_id": bread, "quantity": 1}]})
    assert stranger.status_code == 404
    # a second activity: then it must be named
    db.add(Activity(company_id=company_id, module_id=module_id, name="Bar"))
    await db.commit()
    which = await post({"type": "FT", "lines": [{"product_id": bread, "quantity": 1}]})
    assert which.status_code == 422 and "activity_id" in which.json()["detail"]
    named = await post({"type": "FT", "activity_id": activity_id, "lines": [{"product_id": bread, "quantity": 1}]})
    assert named.status_code == 201, named.text
    assert len((await client.get(API + "/activities", headers=api["h"])).json()) == 2
    assert (await db.execute(select(func.count(Invoice.id)))).scalar_one() == 1  # nothing else was issued


async def test_documents_need_their_right_and_stay_in_their_company(api, db):
    client = api["client"]
    catalog_only = (await keys.create_key(db, api["company"].id, None, "Catálogo", ["catalog"]))["key"]
    refused = await client.post(API + "/documents", headers={"X-API-Key": catalog_only, "Idempotency-Key": "x" * 10},
                                json={"type": "FT", "lines": [{"product_id": str(api["bread"].id), "quantity": 1}]})
    assert refused.status_code == 403
    doc = (await client.post(API + "/documents", headers=_with_key(api), json={
        "type": "FP", "lines": [{"product_id": str(api["bread"].id), "quantity": 1}]})).json()
    from app.models.company import Company
    other = Company(name="Outra Lda", nif="5000999780", email="o4@empresa.ao", phone_number="+244923000996")
    db.add(other)
    await db.flush()
    theirs = (await keys.create_key(db, other.id, None, "Deles", ["documents"]))["key"]
    assert (await client.get(f"{API}/documents/{doc['id']}", headers={"X-API-Key": theirs})).status_code == 404
    assert (await client.get(f"{API}/documents/{doc['id']}/pdf", headers={"X-API-Key": theirs})).status_code == 404
    assert (await client.get(API + "/documents", headers={"X-API-Key": theirs})).json()["total"] == 0


async def test_a_manual_document_has_no_agt_state(api, db, monkeypatch):
    """MANUAL mode: declared by the SAF-T - the API shows agt null and queues nothing."""
    from app.services import agt_queue
    monkeypatch.setattr(agt_queue, "sent_to_agt", lambda invoice: invoice.issuance_mode == "ELETRONICA")
    doc = (await api["client"].post(API + "/documents", headers=_with_key(api), json={
        "type": "FR", "payment_method": "MB", "lines": [{"product_id": str(api["bread"].id), "quantity": 1}]})).json()
    assert doc["type"] == "FR" and doc["agt"] is None and api["sent"] == []
