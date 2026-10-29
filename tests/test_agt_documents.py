"""
Faturação Eletrónica, step C: the real documents. A document issued in ELETRONICA is built as the AGT receives it
(numbered lines, taxes, totals = sums of the lines, signed), sent (registarFactura → ENVIADA with the requestID), and
its validation read (obterEstado → VALIDADA / VALIDADA_P / ERRO). No internet never makes it ERRO; a set-up problem
(E07: software not certified) makes it wait; only the AGT refusing THIS document does - and such a document is not
sent again under its number. The AGT is simulated.
"""
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.core.config import get_settings
from app.models.customer import Customer
from app.models.document_series import ContingencyIndicator, DocumentSeries
from app.models.document_type import DocumentType
from app.models.establishment import Establishment
from app.models.invoice import Invoice, InvoiceStatus
from app.models.platform_settings import PlatformSettings
from app.models.service import Service
from app.services import agt_client, agt_document_service, agt_queue, agt_settings_service, agt_signing
from app.services.invoice_service import create_credit_note, create_invoice

YEAR = date.today().year
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption()).decode()
PUBLIC = agt_signing.public_pem(PEM)


class FakeAgt:
    """registarFactura → a requestID (or .register_answer); obterEstado → .states[requestID] or «8» (processing)."""

    def __init__(self):
        self.received, self.down, self.register_answer, self.states, self.counter = [], False, None, {}, 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("no route")
        body = json.loads(request.content)
        service = request.url.path.rsplit("/", 1)[-1]
        self.received.append((service, body))
        if service == "registarFactura":
            if self.register_answer is not None:
                code, answer = self.register_answer
                return httpx.Response(code, json=answer)
            self.counter += 1
            return httpx.Response(200, json={"requestID": f"2026{self.counter:011d}", "errorList": []})
        if service == "obterEstado":
            return httpx.Response(200, json=self.states.get(body["requestID"], {"resultCode": "8"}))
        return httpx.Response(200, json={})


@pytest.fixture
async def agt(db, company_with_essentials, monkeypatch, test_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    ctx = company_with_essentials
    company = ctx["company"]
    company.issuance_mode, company.auto_series_year = "ELETRONICA", False
    sede = Establishment(company_id=company.id, code="SEDE", name="Sede")
    db.add(sede)
    await db.flush()
    types = {t.code: t for t in (await db.execute(select(DocumentType))).scalars().all()}
    for code in ("FT", "FR", "NC", "RC"):
        db.add(DocumentSeries(company_id=company.id, establishment_id=sede.id, document_type_id=types[code].id, year=YEAR,
                              issuance_mode="ELETRONICA", series_code=f"{code}{str(YEAR)[2:]}SEDEN",
                              date_start=date(YEAR, 1, 1), date_end=date(YEAR, 12, 31), agt_status="A",
                              contingency_indicator=ContingencyIndicator.NORMAL, number_start=1, number_end=999999999,
                              current_number=0))
    detail = {"productId": "RMSOFT", "productVersion": "1.0.0", "softwareValidationNumber": "C_134"}
    db.add(PlatformSettings(product_version="1.0.0", software_validation_number="C_134"))
    service = Service(company_id=company.id, code="QUARTO", name="Diária quarto duplo", price=1000,
                      vat_id=ctx["vat_nor"].id, unit_of_measure_id=ctx["unit_un"].id)
    customer = Customer(company_id=company.id, name="Cliente Lda", nif="5000413178")
    db.add_all([service, customer])
    await db.commit()
    await agt_settings_service.save_platform(db, "HOMOLOGACAO", "ws.hml.rmsoft", "segredo", "RMSOFT", None, None,
                                             agt_signing.sign(detail, PEM))
    await agt_settings_service.save_company_key(db, company, PEM)
    fake = FakeAgt()
    monkeypatch.setattr(agt_client, "agt_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(agt_client, "agt_session", async_sessionmaker(bind=test_engine, class_=AsyncSession,
                                                                      expire_on_commit=False))
    monkeypatch.setattr(get_settings(), "AGT_QUEUE", "base")
    return {**ctx, "fake": fake, "service": service, "customer": customer, "types": types}


async def _issue(db, agt, lines=None, **kw) -> Invoice:
    lines = lines or [{"service_id": agt["service"].id, "quantity": 2, "discount_percent": 10},
                      {"service_id": agt["service"].id, "quantity": 1}]
    return await create_invoice(db, agt["company"].id, agt["activity"].id, customer_id=agt["customer"].id,
                                invoice_type="FACTURA", lines_input=lines, **kw)


async def _run(db, minutes: float = 0) -> int:
    return await agt_queue.send_due(db, now=datetime.now(timezone.utc) + timedelta(minutes=minutes))


async def test_the_document_as_the_agt_receives_it(db, agt):
    invoice = await _issue(db, agt)
    document = await agt_document_service.build_document(db, invoice, "5000000000", PEM)
    number = f"FT FT{str(YEAR)[2:]}SEDEN/1"
    assert document["documentNo"] == number and document["documentType"] == "FT" and document["documentStatus"] == "N"
    assert (document["customerTaxID"], document["customerCountry"], document["companyName"]) == ("5000413178", "AO", "Cliente Lda")
    lines = document["lines"]
    assert [l["lineNumber"] for l in lines] == [1, 2]
    first = lines[0]
    assert first["operationType"] == "SG" and first["productCode"] == "QUARTO" and first["unitOfMeasure"] == "UN"
    assert (first["unitPriceBase"], first["unitPrice"], first["creditAmount"], first["settlementAmount"]) == (1000, 900, 1800, 200)
    assert first["taxes"] == [{"taxType": "IVA", "taxCountryRegion": "AO", "taxCode": "NOR", "taxPercentage": 14.0,
                               "taxContribution": 252.0}]
    assert document["documentTotals"] == {"taxPayable": 392.0, "netTotal": 2800.0, "grossTotal": 3192.0}
    assert float(invoice.total) == 3192.0
    signed = agt_signing.payload_of(document["jwsDocumentSignature"])
    assert signed == {"documentNo": number, "taxRegistrationNumber": "5000000000", "documentType": "FT",
                      "documentDate": invoice.business_date.isoformat(), "customerTaxID": "5000413178",
                      "customerCountry": "AO", "companyName": "Cliente Lda", "documentTotals": document["documentTotals"]}
    assert agt_signing.verify(document["jwsDocumentSignature"], PUBLIC)
    assert agt_document_service.qr_url("5000000000", number) == (
        f"https://portaldocontribuinte.minfin.gov.ao/consultar-fe?FT%20FT{str(YEAR)[2:]}SEDEN%2F1")
    assert agt_document_service.qr_url(  # the AGT's specification's address, set in Configurações
        "5000000000", number, "https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?emissor={nif}"
        "&document={documento}") == ("https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?"
                                     f"emissor=5000000000&document=FT%20FT{str(YEAR)[2:]}SEDEN%2F1")
    assert agt_document_service.tax_up(23.144) == 23.15 and agt_document_service.tax_up(5.9999999) == 6.0


async def test_a_credit_note_refers_to_its_invoice(db, agt):
    invoice = await _issue(db, agt)
    lines = (await db.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    from app.models.invoice_line import InvoiceLine
    first_line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
                                   .order_by(InvoiceLine.line_number))).scalars().first()
    note = await create_credit_note(db, agt["company"].id, agt["activity"].id, invoice.id, "RTF", "Desconto não aplicado",
                                    lines_input=[{"invoice_line_id": first_line.id, "quantity": 1}])
    document = await agt_document_service.build_document(db, note, "5000000000", PEM)
    assert document["documentType"] == "NC" and "debitAmount" in document["lines"][0]
    assert document["lines"][0]["referenceInfo"] == {"reference": f"FT FT{str(YEAR)[2:]}SEDEN/1",
                                                     "reason": "Desconto não aplicado"}
    assert lines.id == invoice.id


async def test_sent_then_validated(db, agt):
    invoice = await _issue(db, agt)
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PENDENTE and invoice.agt_next_attempt_at is not None
    assert await _run(db) == 1
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.ENVIADA and invoice.agt_request_id == "202600000000001"
    service, body = agt["fake"].received[-1]
    assert service == "registarFactura" and body["numberOfEntries"] == 1
    assert body["documents"][0]["documentNo"] == f"FT FT{str(YEAR)[2:]}SEDEN/1"

    assert await _run(db, minutes=1) == 1  # still processing (8): read again later
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.ENVIADA and invoice.agt_next_attempt_at is not None
    agt["fake"].states["202600000000001"] = {"requestID": "202600000000001", "resultCode": "0", "documentStatusList": [
        {"documentNo": f"FT FT{str(YEAR)[2:]}SEDEN/1", "documentStatus": "V", "errorList": []}]}
    assert await _run(db, minutes=5) == 1
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.VALIDADA and invoice.agt_next_attempt_at is None
    assert invoice.agt_validated_at is not None and await _run(db, minutes=60) == 0


async def test_no_internet_never_makes_it_erro(db, agt):
    invoice = await _issue(db, agt)
    agt["fake"].down = True
    for minutes in (0, 1, 2, 5, 10, 20, 40, 80, 160):
        await _run(db, minutes=minutes)
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PENDENTE and invoice.agt_attempts >= 7
    assert "inacessível" in invoice.agt_last_error and invoice.agt_next_attempt_at is not None
    agt["fake"].down = False
    assert await _run(db, minutes=300) == 1
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.ENVIADA and invoice.agt_last_error is None


async def test_a_set_up_problem_makes_it_wait_not_erro(db, agt):
    invoice = await _issue(db, agt)
    agt["fake"].register_answer = (200, {"requestID": "", "errorList": [
        {"idError": "E07", "descriptionError": "Software não certificado"}]})
    await _run(db)
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PENDENTE and invoice.agt_last_error == "E07 - Software não certificado"
    assert invoice.agt_errors is None and invoice.agt_next_attempt_at > datetime.now(timezone.utc) + timedelta(minutes=9)


async def test_the_agt_refusing_the_document_is_erro_and_it_is_not_sent_again(db, agt):
    refused = await _issue(db, agt)
    agt["fake"].register_answer = (400, {"requestID": "", "errorList": [
        {"idError": "E12", "descriptionError": "Número de linha repetido", "documentNo": "FT ..."}]})
    await _run(db)
    await db.refresh(refused)
    assert refused.status == InvoiceStatus.ERRO and refused.agt_errors[0]["idError"] == "E12"
    assert refused.agt_next_attempt_at is None

    # invalid at the validation («I»)
    agt["fake"].register_answer = None
    invalid = await _issue(db, agt)
    await _run(db)
    await db.refresh(invalid)
    number = f"FT FT{str(YEAR)[2:]}SEDEN/2"
    agt["fake"].states[invalid.agt_request_id] = {"resultCode": "2", "documentStatusList": [
        {"documentNo": number, "documentStatus": "I", "errorList": [{"errorCode": "E22", "errorDescription": "Totais"}]}]}
    await _run(db, minutes=5)
    await db.refresh(invalid)
    assert invalid.status == InvoiceStatus.ERRO and invalid.agt_last_error == "E22 - Totais"

    # «Reenviar» refused: the same number is never accepted again
    import httpx as _httpx
    from app.core.database import get_db
    from app.core.security import create_access_token
    from app.main import app
    from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, agt["company"].id)
    await db.commit()

    async def same():
        yield db
    app.dependency_overrides[get_db] = same
    try:
        token = create_access_token(subject=str(agt["gestor"].id), company_id=str(agt["company"].id), role="GESTOR")
        async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url="http://t") as client:
            answer = await client.post(f"/api/v1/invoices/{invalid.id}/resubmit", headers={"Authorization": "Bearer " + token})
        assert answer.status_code == 422 and "nota de crédito" in answer.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_already_registered_and_penalty(db, agt):
    invoice = await _issue(db, agt)
    agt["fake"].register_answer = (400, {"requestID": "202500000000777", "errorList": [
        {"idError": "E09", "descriptionError": "Já consta no repositório"}]})
    await _run(db)
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.ENVIADA and invoice.agt_request_id == "202500000000777"
    agt["fake"].states["202500000000777"] = {"resultCode": "0", "documentStatusList": [
        {"documentNo": f"FT FT{str(YEAR)[2:]}SEDEN/1", "documentStatus": "P"}]}
    await _run(db, minutes=5)
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.VALIDADA_P


async def test_a_set_up_missing_waits(db, agt):
    invoice = await _issue(db, agt)
    platform = (await db.execute(select(PlatformSettings))).scalar_one()
    platform.agt_username = None
    await db.commit()
    await _run(db)
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PENDENTE and "Credenciais" in invoice.agt_last_error
    assert agt["fake"].received == []


def test_a_pessoa_singular_issues_with_the_nif_of_its_bi():
    from pydantic import ValidationError
    from app.schemas.admin import CompanyUpdateRequest
    base = {"name": "Joana Manuel", "email": "joana@exemplo.ao", "phone_number": "+244923456789"}
    person = CompanyUpdateRequest(**base, nif=" 000415195la035 ", legal_person_type="FISICA")
    assert person.nif == "000415195LA035"
    with pytest.raises(ValidationError, match="pessoa singular"):
        CompanyUpdateRequest(**base, nif="000415195LA035", legal_person_type="JURIDICA")
    with pytest.raises(ValidationError, match="NIF inválido"):
        CompanyUpdateRequest(**base, nif="12AB", legal_person_type="FISICA")
    assert CompanyUpdateRequest(**base, nif="5000457256", legal_person_type="JURIDICA").nif == "5000457256"


def test_the_qr_of_an_electronic_document_carries_the_agt_logo():
    from PIL import Image
    from app.utils.pdf_generator import _make_qr_image
    url = agt_document_service.qr_url("5000000000", "FT FT26SEDEN/1")
    plain, with_logo = Image.open(_make_qr_image(url)), Image.open(_make_qr_image(url, agt_logo=True))
    assert plain.size == with_logo.size and plain.convert("RGB").tobytes() != with_logo.convert("RGB").tobytes()
