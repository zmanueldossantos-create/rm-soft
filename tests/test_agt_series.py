"""
Faturação Eletrónica, step B: the AGT's numbering series. A type sent to the AGT gets its code from solicitarSerie (per
establishment, N or C), a working document a local code; one N and one C side by side; the invoice takes the N series,
the C one in contingência (within its period); a series used up is refused; «Sincronizar com a AGT» (listarSeries)
updates the AGT's status, range and last number used, and adds the series the AGT knows that this server does not.
The AGT is simulated.
"""
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.document_series import ContingencyIndicator, DocumentSeries
from app.models.document_type import DocumentType
from app.models.establishment import Establishment
from app.models.platform_settings import PlatformSettings
from app.services import agt_client, agt_settings_service, agt_signing
from app.services.document_series_service import (SeriesAlreadyExistsError, SeriesNotFoundError, create_series,
                                                  get_next_number, get_or_create_current_series)
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog

BASE = "/api/v1/document-series"
YEAR = date.today().year


def _pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


class FakeAgt:
    """solicitarSerie gives «<type><yy><establishment><N|C>»; listarSeries returns what the test puts in .listed."""

    def __init__(self):
        self.received, self.listed, self.down, self.refuse = [], [], False, None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectTimeout("no route")
        body = json.loads(request.content)
        service = request.url.path.rsplit("/", 1)[-1]
        self.received.append((service, body))
        if self.refuse:
            return httpx.Response(200, json={"resultCode": "0", "errorList": [self.refuse]})
        if service == "solicitarSerie":
            code = f"{body['documentType']}{str(body['seriesYear'])[2:]}{body['establishmentNumber']}{body['seriesContingencyIndicator']}"
            return httpx.Response(200, json={"resultCode": 1, "errorList": [], "seriesFEResult": {
                "seriesCode": code, "authorizedQuantity": "999999999999", "firstDocumentNo": "1",
                "lastDocumentNo": "999999999999"}})
        return httpx.Response(200, json={"resultCode": "1", "seriesResultCount": str(len(self.listed)),
                                         "seriesInfo": self.listed})


@pytest.fixture
async def agt(db, company_with_essentials, test_engine, monkeypatch):
    ctx = company_with_essentials
    company = ctx["company"]
    company.issuance_mode = "ELETRONICA"
    company.auto_series_year = False
    sede = Establishment(company_id=company.id, code="SEDE", name="Sede")
    db.add(sede)
    detail = {"productId": "RMSOFT", "productVersion": "1.0.0", "softwareValidationNumber": "C_134"}
    db.add(PlatformSettings(product_version="1.0.0", software_validation_number="C_134"))
    await db.commit()
    await agt_settings_service.save_platform(db, "HOMOLOGACAO", "ws.hml.rmsoft", "segredo", "RMSOFT", None, None,
                                             agt_signing.sign(detail, _pem()))
    await agt_settings_service.save_company_key(db, company, _pem())
    fake = FakeAgt()
    monkeypatch.setattr(agt_client, "agt_transport", httpx.MockTransport(fake.handler))
    sessions = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(agt_client, "agt_session", sessions)
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company.id)

    async def own_session():
        async with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = own_session
    types = {t.code: t for t in (await db.execute(select(DocumentType))).scalars().all()}
    h = {"Authorization": "Bearer " + create_access_token(subject=str(ctx["gestor"].id), company_id=str(company.id),
                                                          role="GESTOR")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {**ctx, "fake": fake, "client": client, "h": h, "sessions": sessions, "sede": sede, "types": types,
               "company_id": company.id}
    app.dependency_overrides.pop(get_db, None)


async def _ask(agt, code: str, indicator: str = "NORMAL"):
    return await agt["client"].post(BASE, headers=agt["h"], json={
        "document_type_id": str(agt["types"][code].id), "year": YEAR, "establishment_id": str(agt["sede"].id),
        "contingency_indicator": indicator})


async def test_a_series_is_asked_to_the_agt_with_its_establishment_and_indicator(agt):
    created = await _ask(agt, "FT")
    assert created.status_code == 201, created.text
    series = created.json()[0]
    assert series["series_code"] == f"FT{str(YEAR)[2:]}SEDEN" and series["contingency_indicator"] == "NORMAL"
    assert (series["number_start"], series["number_end"], series["current_number"]) == (1, 2_147_483_647, 0)
    assert series["agt_status"] == "A"
    service, body = agt["fake"].received[-1]
    assert service == "solicitarSerie"
    assert (body["documentType"], body["establishmentNumber"], body["seriesYear"], body["seriesContingencyIndicator"]) \
        == ("FT", "SEDE", str(YEAR), "N")

    again = await _ask(agt, "FT")
    assert again.status_code == 409 and "normal" in again.json()["detail"]
    contingency = await _ask(agt, "FT", "CONTINGENCIA")  # a C series beside the N one
    assert contingency.status_code == 201 and contingency.json()[0]["series_code"].endswith("SEDEC")
    assert agt["fake"].received[-1][1]["seriesContingencyIndicator"] == "C"


async def test_failures_create_nothing(agt):
    agt["fake"].down = True
    down = await _ask(agt, "FR")
    assert down.status_code == 503 and "não respondeu" in down.json()["detail"]
    agt["fake"].down = False
    agt["fake"].refuse = {"idError": "E07", "descriptionError": "Software não certificado"}
    refused = await _ask(agt, "FR")
    assert refused.status_code == 422 and refused.json()["detail"] == "E07 - Software não certificado"
    async with agt["sessions"]() as session:
        codes = (await session.execute(select(DocumentSeries.series_code).where(
            DocumentSeries.company_id == agt["company_id"]))).scalars().all()
    assert codes == []


async def test_a_working_document_keeps_one_series_across_the_mode_switch(agt, db):
    """A pro-forma is never sent to the AGT: in ELETRONICA it is not asked for, it goes on with the series it had in
    MANUAL (a second «FP2026» would repeat its numbers) - or one is made at its first document."""
    calls = len(agt["fake"].received)
    refused = await _ask(agt, "FP")
    assert refused.status_code == 422 and "automaticamente" in refused.json()["detail"]
    company, fp = agt["company"], agt["types"]["FP"]
    await db.refresh(company)

    made = await get_or_create_current_series(db, company, fp.id)  # none yet: made at the first document
    assert made.series_code == f"FP{YEAR}" and made.agt_status is None and len(agt["fake"].received) == calls
    assert (await get_or_create_current_series(db, company, fp.id)).id == made.id

    # a MANUAL-era series already used is the one that goes on
    made.issuance_mode, made.current_number = "MANUAL", 2
    await db.commit()
    again = await get_or_create_current_series(db, company, fp.id)
    assert again.id == made.id and await get_next_number(db, again) == 3


async def test_the_invoice_takes_the_n_series_or_the_c_one_in_contingency(agt, db):
    await _ask(agt, "FT")
    await _ask(agt, "FT", "CONTINGENCIA")
    company, ft = agt["company"], agt["types"]["FT"]
    await db.refresh(company)
    normal = await get_or_create_current_series(db, company, ft.id, contingency=False)
    assert normal.contingency_indicator == ContingencyIndicator.NORMAL
    c = await get_or_create_current_series(db, company, ft.id, contingency=True)
    assert c.contingency_indicator == ContingencyIndicator.CONTINGENCIA

    # a C series outside the period the AGT gave it is not used
    c.series_start_ts = datetime.now(timezone.utc) - timedelta(days=3)
    c.series_end_ts = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()
    # no valid C series: the N one (a sale is never refused for it - the document waits in the queue all the same)
    assert (await get_or_create_current_series(db, company, ft.id, contingency=True)).id == normal.id

    # a series used up
    normal.number_end, normal.current_number = 2, 2
    await db.commit()
    with pytest.raises(SeriesNotFoundError, match="esgotada"):
        await get_next_number(db, normal)


async def test_sync_reads_the_agt_series_and_adds_the_unknown_ones(agt, db):
    created = (await _ask(agt, "FT")).json()[0]
    short = str(YEAR)[2:]
    agt["fake"].listed = [
        {"seriesCode": created["series_code"], "seriesYear": YEAR, "documentType": "FT", "seriesStatus": "U",
         "firstDocumentApproved": "1", "lastDocumentApproved": "5000", "lastDocumentCreated": f"FT {created['series_code']}/12",
         "seriesContingencyIndicator": "N"},
        {"seriesCode": f"NC{short}SEDEN", "seriesYear": str(YEAR), "documentType": "NC", "seriesStatus": "U",
         "firstDocumentApproved": "1", "lastDocumentApproved": "999999999999", "lastDocumentCreated": "7",
         "seriesContingencyIndicator": "N"},
        {"seriesCode": f"FR{short}SEDEC", "seriesYear": YEAR, "documentType": "FR", "seriesStatus": "A",
         "seriesContingencyIndicator": "C", "seriesStartTS": f"{YEAR}-01-01T00:00:00", "seriesEndTS": f"{YEAR}-12-31T23:59:59"},
        {"seriesCode": "XX99", "seriesYear": YEAR, "documentType": "ZZ"},
    ]
    synced = await agt["client"].post(BASE + "/sync-agt", headers=agt["h"])
    assert synced.status_code == 200, synced.text
    result = synced.json()
    assert (result["updated"], result["added"], result["unknown"]) == (1, 2, ["XX99"])
    by_code = {s["series_code"]: s for s in result["series"]}
    ft = by_code[created["series_code"]]
    assert (ft["agt_status"], ft["number_end"], ft["current_number"]) == ("U", 5000, 12)  # next FT number: 13
    nc = by_code[f"NC{short}SEDEN"]
    assert nc["current_number"] == 7 and nc["description"] == "Importada da AGT"
    fr = by_code[f"FR{short}SEDEC"]
    assert fr["contingency_indicator"] == "CONTINGENCIA"
    assert datetime.fromisoformat(fr["series_end_ts"]) == datetime(YEAR, 12, 31, 23, 59, 59,
                                                                  tzinfo=timezone(timedelta(hours=1)))
    assert agt["fake"].received[-1][0] == "listarSeries" and agt["fake"].received[-1][1]["establishmentNumber"] == "SEDE"


async def test_a_manual_company_keeps_one_series_per_type(db, company_with_essentials):
    company = company_with_essentials["company"]
    company.issuance_mode, company.auto_series_year = "MANUAL", True
    await db.commit()
    ft = (await db.execute(select(DocumentType).where(DocumentType.code == "FT"))).scalar_one()
    await create_series(db, company, ft.id, year=YEAR)
    with pytest.raises(SeriesAlreadyExistsError):
        await create_series(db, company, ft.id, year=YEAR)
