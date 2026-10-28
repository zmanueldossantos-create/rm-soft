"""
Faturação Eletrónica, step A: the JWS signatures (RS256), the platform's AGT settings (access, software identity and
signature - the producer's key never leaves the platform), the taxpayer's key (encrypted, never sent back), the calls
to the AGT (Basic Auth, envelope, the call's signature) and how their failures are told apart: not reached / 5xx / 429
→ AgtUnavailable (tried again, never ERRO), 4xx → AgtRefused with the AGT's errors. The AGT is simulated.
"""
import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.agt_call import AgtCall
from app.models.company import Company
from app.models.platform_settings import PlatformSettings
from app.services import agt_client, agt_settings_service, agt_signing
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog


def _pem(bits: int = 2048) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


TAXPAYER_KEY = _pem()


# ------------------------------------------------------------------------------------------------------ signatures

def test_a_jws_signs_the_canonical_object_and_is_verified_with_the_public_key():
    payload = {"taxRegistrationNumber": "5000413178", "requestID": "202500000010689", "nome": "Padaria São João"}
    token = agt_signing.sign(payload, TAXPAYER_KEY)
    header, body, signature = token.split(".")
    assert "=" not in token and "+" not in token and "/" not in token  # Base64URL without padding
    assert json.loads(base64.urlsafe_b64decode(header + "==")) == {"alg": "RS256", "typ": "JWT"}
    raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    assert raw == '{"taxRegistrationNumber":"5000413178","requestID":"202500000010689","nome":"Padaria São João"}'.encode()
    assert agt_signing.payload_of(token) == payload
    public = agt_signing.public_pem(TAXPAYER_KEY)
    assert agt_signing.verify(token, public)
    assert not agt_signing.verify(header + "." + agt_signing.b64url(b'{"requestID":"x"}') + "." + signature, public)
    assert agt_signing.sign(payload, TAXPAYER_KEY) == token  # RS256 (PKCS#1 v1.5): the same text every time


def test_keys_are_checked_and_the_agt_file_format_is_accepted():
    as_in_the_agt_file = '"""' + TAXPAYER_KEY.strip().replace("\n", "\\n") + '"""'
    assert agt_signing.key_info(as_in_the_agt_file) == agt_signing.key_info(TAXPAYER_KEY)
    assert agt_signing.key_info(TAXPAYER_KEY)["bits"] == 2048
    with pytest.raises(agt_signing.AgtKeyError, match="inválida"):
        agt_signing.load_private_key("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----")
    with pytest.raises(agt_signing.AgtKeyError, match="curta"):
        agt_signing.load_private_key(_pem(1024))
    assert agt_signing.payload_of("not a jws") is None


# ------------------------------------------------------------------------------------------------------ settings

async def _platform(db, **values) -> PlatformSettings:
    platform = PlatformSettings(product_version="1.0.0", software_validation_number="C_134", **values)
    db.add(platform)
    await db.commit()
    return platform


async def test_on_the_platform_the_producer_key_signs_the_software_identity(db):
    await _platform(db)
    view = await agt_settings_service.save_platform(db, "HOMOLOGACAO", " ws.hml.rmsoft ", "segredo-123", "RMSOFT",
                                                    None, None, None)
    assert view["signature_status"] == "EM_FALTA" and view["has_password"] and "segredo" not in str(view)
    view = await agt_settings_service.generate_software_key(db)
    detail = {"productId": "RMSOFT", "productVersion": "1.0.0", "softwareValidationNumber": "C_134"}
    assert view["signature_status"] == "OK" and view["signed_detail"] == detail
    assert agt_signing.payload_of(view["software_signature"]) == detail
    assert agt_signing.verify(view["software_signature"], view["software_public_key"])
    assert "PRIVATE" not in str(view)
    with pytest.raises(agt_settings_service.AgtSettingsError, match="Já existe"):
        await agt_settings_service.generate_software_key(db)

    # a new version (the SAF-T card): signed again at once; the signature version is signed too
    from app.services.platform_settings_service import update_platform_settings
    await update_platform_settings(db, "C_134", "5000457256", "RMSOFT/RockMayika", "1.1.0")
    view = await agt_settings_service.save_platform(db, "PRODUCAO", "ws.rmsoft", None, "RMSOFT", 2, None, None)
    assert view["has_password"]  # None: kept
    assert agt_signing.payload_of(view["software_signature"]) == {**detail, "productVersion": "1.1.0", "signatureVersion": 2}
    stored = (await db.execute(select(PlatformSettings))).scalar_one()
    assert "PRIVATE" not in stored.agt_software_key_encrypted and "segredo" not in stored.agt_password_encrypted


async def test_on_a_client_server_the_signature_is_pasted_and_checked(db):
    platform = await _platform(db, agt_product_id="RMSOFT")
    signature = agt_signing.sign({"productId": "RMSOFT", "productVersion": "1.0.0", "softwareValidationNumber": "C_134"},
                                 _pem())
    with pytest.raises(agt_settings_service.AgtSettingsError, match="três partes"):
        await agt_settings_service.save_platform(db, "HOMOLOGACAO", "u", "p", "RMSOFT", None, None, "abc")
    view = await agt_settings_service.save_platform(db, "HOMOLOGACAO", "u", "p", "RMSOFT", None, None, signature)
    assert view["signature_status"] == "OK" and not view["has_software_key"]
    platform.product_version = "2.0.0"  # the software was updated: that signature is for another version
    await db.commit()
    assert agt_settings_service.signature_status(platform) == "DESATUALIZADA"
    assert any("desatualizada" in m for m in agt_settings_service.missing_parts(platform, None))


# ------------------------------------------------------------------------------------------------------ the calls

class FakeAgt:
    """The AGT simulated: answers what the test says, and keeps what it received."""

    def __init__(self):
        self.received, self.answer = [], (200, {"resultCode": "1", "seriesResultCount": "0", "seriesInfo": []})

    def handler(self, request: httpx.Request) -> httpx.Response:
        if isinstance(self.answer, Exception):
            raise self.answer
        self.received.append(request)
        code, body = self.answer
        return httpx.Response(code, json=body)


@pytest.fixture
async def agt(db, company_with_essentials, test_engine, monkeypatch):
    ctx = company_with_essentials
    company = ctx["company"]
    signature = agt_signing.sign({"productId": "RMSOFT", "productVersion": "1.0.0", "softwareValidationNumber": "C_134"},
                                 _pem())
    await _platform(db, agt_product_id="RMSOFT")
    await agt_settings_service.save_platform(db, "HOMOLOGACAO", "ws.hml.rmsoft", "segredo-123", "RMSOFT", None, None,
                                             signature)
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
    h = {"Authorization": "Bearer " + create_access_token(subject=str(ctx["gestor"].id), company_id=str(company.id),
                                                          role="GESTOR")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {**ctx, "fake": fake, "client": client, "h": h, "sessions": sessions, "company_id": company.id,
               "nif": company.nif}
    app.dependency_overrides.pop(get_db, None)


async def test_the_taxpayer_key_is_kept_encrypted_and_never_sent_back(agt):
    client, h = agt["client"], agt["h"]
    view = (await client.get("/api/v1/company/me/agt", headers=h)).json()
    assert not view["has_key"] and "Chave privada do contribuinte (portal da AGT)" in view["missing"]
    bad = await client.put("/api/v1/company/me/agt/key", headers=h, json={"private_key": "abc"})
    assert bad.status_code == 422 and "inválida" in bad.json()["detail"]
    saved = await client.put("/api/v1/company/me/agt/key", headers=h, json={"private_key": TAXPAYER_KEY})
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert view["has_key"] and view["missing"] == [] and view["key"] == agt_signing.key_info(TAXPAYER_KEY)
    assert "PRIVATE" not in saved.text
    async with agt["sessions"]() as session:
        stored = await session.get(Company, agt["company_id"])
        assert "PRIVATE" not in stored.agt_private_key_encrypted
    removed = await client.put("/api/v1/company/me/agt/key", headers=h, json={"private_key": ""})
    assert removed.json()["has_key"] is False


async def test_the_connection_test_sends_a_signed_call_and_journals_it(agt):
    client, h, fake = agt["client"], agt["h"], agt["fake"]
    not_ready = await client.post("/api/v1/company/me/agt/test", headers=h)
    assert not_ready.status_code == 422 and "Chave privada do contribuinte" in not_ready.json()["detail"]
    await client.put("/api/v1/company/me/agt/key", headers=h, json={"private_key": TAXPAYER_KEY})

    tested = (await client.post("/api/v1/company/me/agt/test", headers=h)).json()
    assert tested["ok"] and tested["answer"]["seriesResultCount"] == "0"
    request = fake.received[-1]
    assert str(request.url) == "https://sifphml.minfin.gov.ao/sigt/fe/v1/listarSeries"
    assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"ws.hml.rmsoft:segredo-123").decode()
    body = json.loads(request.content)
    assert body["schemaVersion"] == "2.0" and body["taxRegistrationNumber"] == agt["nif"]
    assert body["softwareInfo"]["softwareInfoDetail"]["productId"] == "RMSOFT"
    assert agt_signing.payload_of(body["jwsSignature"]) == {"taxRegistrationNumber": agt["nif"]}
    assert agt_signing.verify(body["jwsSignature"], agt_signing.public_pem(TAXPAYER_KEY))

    calls = (await client.get("/api/v1/company/me/agt/calls", headers=h)).json()
    assert calls[0]["service"] == "listarSeries" and calls[0]["status_code"] == 200
    assert calls[0]["request"]["jwsSignature"] == body["jwsSignature"] and "segredo" not in json.dumps(calls)


async def test_failures_are_told_apart(agt, db):
    company = await db.get(Company, agt["company_id"])
    await agt_settings_service.save_company_key(db, company, TAXPAYER_KEY)
    ctx = await agt_client.context_for(db, company)
    fake = agt["fake"]

    fake.answer = httpx.ConnectError("no route")
    with pytest.raises(agt_client.AgtUnavailable):
        await agt_client.obter_estado(ctx, "202500000010689")
    for code in (500, 503, 429):
        fake.answer = (code, {"message": "ocupado"})
        with pytest.raises(agt_client.AgtUnavailable):
            await agt_client.obter_estado(ctx, "202500000010689")
    fake.answer = (401, {})
    with pytest.raises(agt_client.AgtRefused, match="recusou o acesso"):
        await agt_client.listar_series(ctx)
    fake.answer = (400, {"requestID": "1", "errorList": [{"idError": "E40", "descriptionError": "assinatura"}]})
    with pytest.raises(agt_client.AgtRefused) as refused:
        await agt_client.solicitar_serie(ctx, 2026, "FT", "SEDE", "C")
    assert str(refused.value) == "E40 - assinatura" and refused.value.errors[0]["idError"] == "E40"
    body = json.loads(fake.received[-1].content)
    assert (body["seriesContingencyIndicator"], body["establishmentNumber"], body["seriesYear"]) == ("C", "SEDE", "2026")
    assert agt_signing.payload_of(body["jwsSignature"]) == {
        "taxRegistrationNumber": agt["nif"], "seriesYear": "2026", "documentType": "FT", "establishmentNumber": "SEDE",
        "seriesContingencyIndicator": "C"}

    # HTTP 200 with the AGT's errors (E07: software not certified): journaled with the error, the test says it
    fake.answer = (200, {"resultCode": "0", "errorList": [{"idError": "E07", "descriptionError": "não certificado"}]})
    tested = await agt_client.test_connection(db, company)
    assert not tested["ok"] and tested["status_code"] == 200 and "E07 - não certificado" in tested["message"]

    fake.answer = (200, {"requestID": "202500000010689", "resultCode": "8"})
    assert (await agt_client.obter_estado(ctx, "202500000010689"))["resultCode"] == "8"
    async with agt["sessions"]() as session:
        journal = (await session.execute(select(AgtCall).order_by(AgtCall.created_at))).scalars().all()
    assert [c.status_code for c in journal] == [None, 500, 503, 429, 401, 400, 200, 200]
    assert "inacessível" in journal[0].error and journal[-1].error is None and "E07" in journal[-2].error


async def test_nothing_is_called_while_the_settings_are_incomplete(db, company_with_essentials):
    db.add(PlatformSettings())
    await db.commit()
    with pytest.raises(agt_client.AgtConfigError) as missing:
        await agt_client.context_for(db, company_with_essentials["company"])
    assert len(missing.value.missing) == 3 and "Credenciais" in str(missing.value)


# ------------------------------------------------------------------------------------------------------ test NIFs

def _agt_test_file(entries: list[tuple[str, str, str]]) -> str:
    """The AGT's TEST_NIF format: NIF <tab> name <tab> \"\"\"private key\"\"\" <tab> \"\"\"public key\"\"\"."""
    lines = []
    for nif, name, pem in entries:
        lines.append(f'{nif}\t{name}\t"""{pem.strip()}"""\t"""{agt_signing.public_pem(pem).strip()}"""')
    return "\n\n".join(lines)


async def test_the_test_nifs_are_imported_and_a_company_sends_as_one_in_homologation(agt, db):
    client, h, fake = agt["client"], agt["h"], agt["fake"]
    test_key, other_key = _pem(), _pem()
    imported = await agt_settings_service.import_test_taxpayers(db, _agt_test_file(
        [("5000413178", "NIF TESTE PROJECTO SIGT", test_key), ("5001441337", "NIF DE TESTE IIRS - NAO RESIDENTE", other_key)]))
    assert imported["imported"] == 2 and [t["nif"] for t in imported["items"]] == ["5000413178", "5001441337"]
    assert imported["items"][0]["name"] == "NIF TESTE PROJECTO SIGT" and "PRIVATE" not in str(imported)
    with pytest.raises(agt_settings_service.AgtSettingsError, match="Nenhum NIF"):
        await agt_settings_service.import_test_taxpayers(db, "nada aqui")

    view = (await client.get("/api/v1/company/me/agt", headers=h)).json()
    assert [t["nif"] for t in view["test_nifs"]] == ["5000413178", "5001441337"] and view["sending_as"] == agt["nif"]
    unknown = await client.put("/api/v1/company/me/agt/test-nif", headers=h, json={"nif": "123"})
    assert unknown.status_code == 422
    view = (await client.put("/api/v1/company/me/agt/test-nif", headers=h, json={"nif": "5000413178"})).json()
    assert view["sending_as"] == "5000413178" and view["sending_as_test"] and view["missing"] == []  # its key is the test NIF's

    tested = (await client.post("/api/v1/company/me/agt/test", headers=h)).json()
    assert tested["ok"]
    body = json.loads(fake.received[-1].content)
    assert body["taxRegistrationNumber"] == "5000413178"
    assert agt_signing.verify(body["jwsSignature"], agt_signing.public_pem(test_key))

    # in Produção a test NIF is never used: the company is itself again (and needs its own key)
    platform = (await db.execute(select(PlatformSettings))).scalar_one()
    platform.agt_environment = "PRODUCAO"
    await db.commit()
    view = (await client.get("/api/v1/company/me/agt", headers=h)).json()
    assert view["sending_as"] == agt["nif"] and not view["sending_as_test"] and view["test_nifs"] == []
    assert "Chave privada do contribuinte (portal da AGT)" in view["missing"]
