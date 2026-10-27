"""
The site's side of the relay (RELAY_SERVER=true, the RM SOFT platform): a call to /api/public/v1/... made with the key
of a company installed locally is not run here - it is passed to that company's server (app.services.relay_service).

  server on    -> the call waits for the server's answer (a second or two) and gets it as it is: same as direct;
  server off   -> a write is kept: 202 + request_id (GET /api/public/v1/requests/{id}, or the X-Callback-Url webhook);
                  a read of the catalogue / availability is answered from the last photo (X-RM-Offline: true);
                  any other read: 503, try again later.

A key of a SaaS company of this platform, or an unknown key: the normal API runs (relay_or_none returns None).
"""
import base64
import json
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.api_key import ApiKey
from app.models.relay import RelayLink, RelayRequest
from app.services import api_key_service as keys
from app.services import relay_service as relay
from app.services.relay_snapshot import SnapshotRefusal, answer

PREFIX = "/api/public/v1"
SCOPE_OF = {"catalog": "catalog", "customers": "customers", "documents": "documents", "bookings": "bookings"}
NEEDS_IDEMPOTENCY = ("documents", "bookings")  # as the live API: an issue / a booking always carries its key
OFFLINE = "O servidor da empresa está desligado ou sem internet"


def _plain_key(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("x-api-key", "").strip()


def _error(status_code: int, detail: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


def _answered(row: RelayRequest, replayed: bool = False) -> Response:
    headers = {"X-RM-Relay": "true", "X-RM-Request-Id": str(row.id)}
    if replayed:
        headers["Idempotent-Replayed"] = "true"
    if row.response_status == 204 or row.response_body is None and row.response_status < 300:
        return Response(status_code=row.response_status, headers=headers)
    body = row.response_body
    if isinstance(body, dict) and body.get("__binary__"):  # a PDF sent by the agent inside the JSON
        if body.get("disposition"):
            headers["Content-Disposition"] = body["disposition"]
        return Response(content=base64.b64decode(body["base64"]), status_code=row.response_status,
                        media_type=body.get("content_type") or "application/octet-stream", headers=headers)
    return JSONResponse(status_code=row.response_status, content=row.response_body, headers=headers)


def _waiting(row: RelayRequest) -> JSONResponse:
    status_url = f"{PREFIX}/requests/{row.id}"
    return JSONResponse(status_code=202, headers={"Location": status_url, "X-RM-Relay": "true"}, content={
        "request_id": str(row.id), "status": "PENDENTE", "status_url": status_url,
        "detail": OFFLINE + ": o pedido foi guardado e será tratado logo que o servidor volte."})


def _from_photo(link: RelayLink, path: str, query: str | None) -> Response | None:
    if not link.snapshot:
        return None
    try:
        body = answer(link.snapshot, path, query)
    except SnapshotRefusal as e:
        return _error(e.status_code, str(e))
    if body is None:
        return None
    return JSONResponse(content=body, headers={"X-RM-Offline": "true", "X-RM-Relay": "true",
                                               "X-RM-Snapshot-At": link.snapshot_at.isoformat() if link.snapshot_at else ""})


async def platform_key(db, key_hash: str) -> bool:
    """A key of a company of this platform (SaaS): never relayed."""
    return (await db.execute(select(ApiKey.id).where(ApiKey.key_hash == key_hash))).first() is not None


async def relay_or_none(request: Request) -> Response | None:
    path = request.url.path
    if not path.startswith(PREFIX + "/") or path in (PREFIX + "/docs", PREFIX + "/openapi.json"):
        return None
    plain = _plain_key(request)
    if not plain.startswith(keys.KEY_PREFIX):
        return None
    key_hash = keys.hash_key(plain)
    rel = path[len(PREFIX):]
    method = request.method.upper()

    async with relay.relay_session() as db:
        if await platform_key(db, key_hash):
            return None  # a key of this platform: the API runs here
        link = (await db.execute(select(RelayLink).where(
            RelayLink.is_active.is_(True), RelayLink.keys.contains([{"hash": key_hash}])))).scalar_one_or_none()
        if link is None:
            return None  # unknown: the API answers 401
        key = next(k for k in link.keys if k["hash"] == key_hash)
        first = rel.strip("/").split("/")[0]

        # the request's state (relay only)
        if first == "requests":
            try:
                request_id = uuid.UUID(rel.strip("/").split("/")[1])
            except (IndexError, ValueError):
                return _error(404, "Pedido não encontrado")
            row = await db.get(RelayRequest, request_id)
            if row is None or row.company_id != link.company_id:
                return _error(404, "Pedido não encontrado")
            return JSONResponse(content=relay.request_view(row))

        scope = SCOPE_OF.get(first)
        if scope is not None and scope not in key["scopes"]:
            return _error(403, f"Esta chave não tem a permissão «{keys.SCOPES[scope]}»")
        if not keys.within_rate(key_hash):
            return _error(429, f"Limite de {keys.RATE_PER_MINUTE} pedidos por minuto atingido - aguarde um minuto",
                          {"Retry-After": "60"})

        body = None
        if method not in ("GET", "HEAD", "OPTIONS"):
            raw = await request.body()
            if raw:
                try:
                    body = json.loads(raw)
                except ValueError:
                    return _error(422, "O corpo do pedido não é JSON válido")
        idempotency_key = request.headers.get("idempotency-key") or None
        if method == "POST" and first in NEEDS_IDEMPOTENCY and not idempotency_key and not rel.endswith("/cancel"):
            return _error(422, "Falta o cabeçalho Idempotency-Key (único por pedido)")
        callback_url = request.headers.get("x-callback-url") or None
        if callback_url and (len(callback_url) > 500 or not callback_url.startswith(("https://", "http://"))):
            return _error(422, "X-Callback-Url inválido (https://...)")

        if idempotency_key:
            known = (await db.execute(select(RelayRequest).where(
                RelayRequest.company_id == link.company_id,
                RelayRequest.idempotency_key == idempotency_key))).scalar_one_or_none()
            if known is not None:
                if known.path != rel or known.body != body:
                    return _error(422, "Esta Idempotency-Key já foi usada noutro pedido - use uma chave nova por pedido")
                return _answered(known, replayed=True) if known.status == "FEITO" else _waiting(known)

        online = relay.is_online(link)
        if method == "GET" and not online:
            return _from_photo(link, rel, request.url.query) or _error(503, OFFLINE + " - tente mais tarde",
                                                                       {"Retry-After": "300"})
        row = RelayRequest(company_id=link.company_id, key_hash=key_hash, key_name=key["name"], method=method,
                           path=rel, query=request.url.query or None, body=body, idempotency_key=idempotency_key,
                           callback_url=callback_url)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:  # the same key sent twice at the same moment: the first one is kept
            await db.rollback()
            known = (await db.execute(select(RelayRequest).where(
                RelayRequest.company_id == link.company_id, RelayRequest.idempotency_key == idempotency_key))).scalar_one()
            return _waiting(known)
        row_id, link_snapshot = row.id, link

    done = await relay.wait_done(row_id) if online else None
    if done is not None:
        return _answered(done)
    if method == "GET":
        async with relay.relay_session() as db:  # not answered in time: the read is dropped, the photo answers
            row = await db.get(RelayRequest, row_id)
            if row is not None and row.status != "FEITO":
                await db.delete(row)
                await db.commit()
        return _from_photo(link_snapshot, rel, request.url.query) or _error(
            504, "O servidor da empresa não respondeu a tempo - tente de novo")
    async with relay.relay_session() as db:
        return _waiting(await db.get(RelayRequest, row_id))
