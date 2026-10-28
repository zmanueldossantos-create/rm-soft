"""
The calls to the AGT's Faturação Eletrónica (REST, Schema 2.0): https://<ambiente>/sigt/fe/v1/<serviço>, Basic Auth
with the producer's access, every body carrying softwareInfo (the software's identity and signature) and, signed with
the taxpayer's key, the jwsSignature of the call.

What can go wrong is told apart, because it decides what the queue does with a document:
- AgtUnavailable: the AGT was not reached or could not answer (no internet, time out, 5xx, 429 «too many») - nothing is
  wrong with the document: tried again later, never ERRO;
- AgtRefused: the AGT answered and refused the call (4xx, with its error list) - the reason is shown as it came;
- AgtConfigError: something is missing here (access, signature, key) - no call is made.

Every call is written in the journal (app.models.agt_call), in its own session: kept even when the caller rolls back.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.secret_box import decrypt_secret
from app.models.agt_call import AgtCall
from app.models.company import Company
from app.services import agt_signing
from app.services.agt_settings_service import ENVIRONMENTS, issuer, missing_parts, software_detail
from app.services.platform_settings_service import get_or_create_platform_settings

log = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0"
PATH = "/sigt/fe/v1/"
TIMEOUT = httpx.Timeout(30, connect=10)
KEEP_DAYS = 90

agt_transport = None              # replaced in the tests: the AGT simulated
agt_session = AsyncSessionLocal   # the journal's own sessions; replaced in the tests


class AgtError(Exception):
    """Base of the AGT's failures - the message is shown as it is."""


class AgtConfigError(AgtError):
    def __init__(self, missing: list[str]):
        super().__init__("Faturação Eletrónica por configurar: " + "; ".join(missing))
        self.missing = missing


class AgtUnavailable(AgtError):
    """Not reached, or no answer that says anything about the call: tried again later."""


class AgtRefused(AgtError):
    def __init__(self, status_code: int, body, message: str):
        super().__init__(message)
        self.status_code, self.body = status_code, body

    @property
    def errors(self) -> list[dict]:
        return error_list(self.body)


@dataclass
class AgtContext:
    """Everything one call needs: where, with which access, as which software, for which taxpayer."""
    environment: str
    base_url: str
    username: str
    password: str
    software_info: dict
    nif: str
    private_key: str
    company_id: uuid.UUID | None = None
    extra: dict = field(default_factory=dict)


async def context_for(db: AsyncSession, company: Company, private_key: str | None = None) -> AgtContext:
    """In Homologação, a company that picked a test NIF sends as that NIF with its key (agt_settings_service.issuer).
    private_key: another key than the company's (the test tool, with a key file)."""
    platform = await get_or_create_platform_settings(db)
    if private_key:
        nif, key = company.nif.strip(), private_key
    else:
        nif, key, _ = await issuer(db, platform, company)
    missing = missing_parts(platform, key, check_key=True)
    if missing:
        raise AgtConfigError(missing)
    return AgtContext(
        environment=platform.agt_environment,
        base_url=(get_settings().AGT_BASE_URL or ENVIRONMENTS[platform.agt_environment]).rstrip("/"),
        username=platform.agt_username, password=decrypt_secret(platform.agt_password_encrypted),
        software_info={"softwareInfoDetail": software_detail(platform),
                       "jwsSoftwareSignature": platform.agt_software_signature},
        nif=nif, private_key=key, company_id=company.id)


# ----------------------------------------------------------------------------------------------------------- the call

def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def error_list(body) -> list[dict]:
    """The AGT's errors, whatever the service calls them (errorList, requestErrorList, a single errorEntry...)."""
    if isinstance(body, list):
        return [e for e in body if isinstance(e, dict)]
    if not isinstance(body, dict):
        return []
    found = []
    for name in ("errorList", "requestErrorList"):
        found += [e for e in body.get(name) or [] if isinstance(e, dict)]
    if not found and any(k in body for k in ("idError", "errorCode")):
        found.append(body)
    return found


def describe(errors: list[dict]) -> str:
    parts = []
    for e in errors:
        code = e.get("idError") or e.get("errorCode") or ""
        text = e.get("descriptionError") or e.get("errorDescription") or ""
        parts.append((code + " - " + text).strip(" -") if code or text else str(e))
    return "; ".join(p for p in parts if p)


async def _journal(ctx: AgtContext, service: str, body: dict, status_code: int | None, answer, error: str | None,
                   started: float) -> None:
    try:
        async with agt_session() as db:
            db.add(AgtCall(company_id=ctx.company_id, service=service, environment=ctx.environment, request_body=body,
                           status_code=status_code, response_body=answer if isinstance(answer, (dict, list)) else
                           ({"text": str(answer)[:2000]} if answer else None), error=(error or None) and error[:300],
                           duration_ms=int((time.monotonic() - started) * 1000)))
            if ctx.company_id is not None:
                await db.execute(delete(AgtCall).where(
                    AgtCall.company_id == ctx.company_id,
                    AgtCall.created_at < datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)))
            await db.commit()
    except Exception:  # noqa: BLE001 - the journal never stops a call
        log.exception("agt journal")


async def call(ctx: AgtContext, service: str, body: dict):
    """POST the body to the service: the AGT's answer (JSON), or AgtUnavailable / AgtRefused."""
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(base_url=ctx.base_url, transport=agt_transport, timeout=TIMEOUT,
                                     auth=(ctx.username, ctx.password)) as client:
            response = await client.post(PATH + service, json=body, headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        message = f"AGT inacessível ({type(e).__name__}) - será tentado de novo"
        await _journal(ctx, service, body, None, None, message, started)
        raise AgtUnavailable(message)
    try:
        answer = response.json()
    except ValueError:
        answer = response.text or None
    code = response.status_code
    if code >= 500 or code == 429:
        message = f"A AGT não respondeu ({code}) - será tentado de novo"
        await _journal(ctx, service, body, code, answer, message, started)
        raise AgtUnavailable(message)
    if code in (401, 403):
        message = "A AGT recusou o acesso - verifique o utilizador e a palavra-passe da AGT (plataforma RM SOFT)"
        await _journal(ctx, service, body, code, answer, message, started)
        raise AgtRefused(code, answer, message)
    if code >= 400:
        message = describe(error_list(answer)) or f"Pedido recusado pela AGT ({code})"
        await _journal(ctx, service, body, code, answer, message, started)
        raise AgtRefused(code, answer, message)
    # an HTTP 200 may still carry the AGT's errors (errorList): journaled as such, the caller decides
    await _journal(ctx, service, body, code, answer, describe(error_list(answer)) or None, started)
    return answer


def envelope(ctx: AgtContext, signed: dict, with_uuid: bool = True) -> dict:
    """The common part of a body: schema, (submission UUID), NIF, time, software, and the call's signature."""
    body = {"schemaVersion": SCHEMA_VERSION}
    if with_uuid:
        body["submissionUUID"] = str(uuid.uuid4())
    body.update({"taxRegistrationNumber": ctx.nif, "submissionTimeStamp": timestamp(),
                 "softwareInfo": ctx.software_info, "jwsSignature": agt_signing.sign(signed, ctx.private_key)})
    return body


# ------------------------------------------------------------------------------------------------------- the services

async def solicitar_serie(ctx: AgtContext, year: int, document_type: str, establishment: str,
                          contingency: str = "N") -> dict:
    """A new numbering series (N normal, C contingência) - seriesFEResult: seriesCode, firstDocumentNo..."""
    signed = {"taxRegistrationNumber": ctx.nif, "seriesYear": str(year), "documentType": document_type,
              "establishmentNumber": establishment, "seriesContingencyIndicator": contingency}
    body = envelope(ctx, signed)
    body.update({"seriesYear": str(year), "documentType": document_type, "establishmentNumber": establishment,
                 "seriesContingencyIndicator": contingency})
    return await call(ctx, "solicitarSerie", body)


async def listar_series(ctx: AgtContext, **filters) -> dict:
    """The taxpayer's series (filters: seriesCode, seriesYear, seriesStatus, documentType, establishmentNumber)."""
    body = envelope(ctx, {"taxRegistrationNumber": ctx.nif}, with_uuid=False)
    body.update({k: v for k, v in filters.items() if v not in (None, "")})
    return await call(ctx, "listarSeries", body)


async def obter_estado(ctx: AgtContext, request_id: str) -> dict:
    """The validation of the documents sent with registarFactura (resultCode, documentStatusList)."""
    body = envelope(ctx, {"taxRegistrationNumber": ctx.nif, "requestID": request_id})
    body["requestID"] = request_id
    return await call(ctx, "obterEstado", body)


async def consultar_factura(ctx: AgtContext, document_no: str) -> dict:
    body = envelope(ctx, {"taxRegistrationNumber": ctx.nif, "documentNo": document_no})
    body["documentNo"] = document_no
    return await call(ctx, "consultarFactura", body)


async def listar_facturas(ctx: AgtContext, start: str, end: str, kind: str = "EMITIDAS") -> dict:
    body = envelope(ctx, {"taxRegistrationNumber": ctx.nif, "queryStartDate": start, "queryEndDate": end})
    body.update({"queryStartDate": start, "queryEndDate": end, "tipoListagem": kind})
    return await call(ctx, "listarFacturas", body)


async def test_connection(db: AsyncSession, company: Company) -> dict:
    """«Testar ligação à AGT»: listarSeries for this company - the access, the signatures and the key all checked."""
    from sqlalchemy import select
    from app.models.establishment import Establishment
    started = time.monotonic()
    ctx = await context_for(db, company)
    code = (await db.execute(select(Establishment.code).where(
        Establishment.company_id == company.id, Establishment.is_active.is_(True)).order_by(Establishment.created_at)
        .limit(1))).scalar_one_or_none()
    try:
        # a test NIF has none of this company's establishments: «SEDE», as the AGT allows in the sandbox
        establishment = (code or "SEDE") if ctx.nif == company.nif.strip() else "SEDE"
        answer = await listar_series(ctx, establishmentNumber=establishment)
        seconds = round(time.monotonic() - started, 2)
        errors = error_list(answer)
        if errors:  # reached and answered (HTTP 200), but the AGT refused something: shown as a refusal
            return {"ok": False, "status_code": 200, "seconds": seconds, "answer": answer,
                    "message": "A AGT respondeu com erros: " + describe(errors)}
        return {"ok": True, "status_code": 200, "seconds": seconds, "answer": answer,
                "message": "Ligação à AGT estabelecida"}
    except AgtRefused as e:
        return {"ok": False, "status_code": e.status_code, "seconds": round(time.monotonic() - started, 2),
                "answer": e.body, "message": str(e)}
    except AgtUnavailable as e:
        return {"ok": False, "status_code": None, "seconds": round(time.monotonic() - started, 2), "answer": None,
                "message": str(e)}
