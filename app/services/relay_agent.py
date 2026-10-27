"""
The relay agent (P4 step 5b), on the client's server (local installation): it goes OUT to the RM SOFT platform - no
port is opened at the client's - takes the calls the company's web site made there, runs them on this server's own
public API (same rules, same journal) and sends the answers back. It also sends the hashes of the company's active
keys (every minute) and the photo (catalogue, availability - every 5 minutes) the platform answers from while this
server is off.

Set in Definições da Empresa → Integração API → Ligação ao relé (the platform's address and the relay's secret, given
by RM SOFT). Started with the server (RELAY_AGENT_LOOP); one loop per company with an active link.
"""
import asyncio
import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.secret_box import decrypt_secret, encrypt_secret, secret_hint
from app.models.api_key import ApiKey
from app.models.relay import RelayAgentSettings

log = logging.getLogger(__name__)

AGENT_PATH = "/api/relay/v1/agent"
KEYS_EVERY = timedelta(minutes=1)
SNAPSHOT_EVERY = timedelta(minutes=5)
RECHECK_EVERY = timedelta(seconds=30)  # the settings read again (switched off, another address...)
SUPERVISE_SECONDS = 30
BACKOFF = (5, 10, 20, 40, 60)

agent_session = AsyncSessionLocal  # replaced in the tests


class RelayAgentError(Exception):
    """Refused - the message is shown as it is."""


def make_client(url: str, secret: str, transport=None) -> httpx.AsyncClient:
    """The connection to the platform (a test gives its own transport)."""
    return httpx.AsyncClient(base_url=url.rstrip("/"), transport=transport, timeout=httpx.Timeout(40, connect=10),
                             headers={"Authorization": "Bearer " + secret})


relay_transport = None  # replaced in the tests: the platform simulated


# --------------------------------------------------------------------------------------------- the gestor's screen

def _when(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


async def view(db: AsyncSession, company_id: uuid.UUID) -> dict:
    row = await db.get(RelayAgentSettings, company_id)
    if row is None:
        return {"configured": False}
    connected = row.last_ok_at is not None and datetime.now(timezone.utc) - row.last_ok_at < timedelta(minutes=2) \
        and (row.last_error_at is None or row.last_error_at < row.last_ok_at)
    return {"configured": True, "relay_url": row.relay_url, "secret_hint": secret_hint(decrypt_secret(row.secret_encrypted)),
            "is_active": row.is_active, "connected": row.is_active and connected, "last_ok_at": _when(row.last_ok_at),
            "last_error": row.last_error, "last_error_at": _when(row.last_error_at),
            "last_snapshot_at": _when(row.last_snapshot_at), "requests_done": row.requests_done}


def _clean_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url.startswith(("https://", "http://")) or len(url) > 300 or " " in url:
        raise RelayAgentError("Endereço do relé inválido (ex.: https://admin.rmsystem.co.ao)")
    return url


async def save(db: AsyncSession, company_id: uuid.UUID, relay_url: str, secret: str | None, is_active: bool) -> dict:
    """secret empty: the one kept stays (it is never shown again)."""
    from app.services.relay_service import SECRET_PREFIX
    url = _clean_url(relay_url)
    secret = (secret or "").strip()
    if secret and (not secret.startswith(SECRET_PREFIX) or len(secret) < 20):
        raise RelayAgentError("Código do relé inválido - começa por «rmr_» (dado pela RM SOFT)")
    row = await db.get(RelayAgentSettings, company_id)
    if row is None:
        if not secret:
            raise RelayAgentError("Indique o código do relé (dado pela RM SOFT)")
        row = RelayAgentSettings(company_id=company_id, relay_url=url, secret_encrypted=encrypt_secret(secret))
        db.add(row)
    row.relay_url, row.is_active = url, bool(is_active)
    if secret:
        row.secret_encrypted = encrypt_secret(secret)
    row.last_error, row.last_error_at = None, None
    await db.commit()
    return await view(db, company_id)


async def remove(db: AsyncSession, company_id: uuid.UUID) -> dict:
    row = await db.get(RelayAgentSettings, company_id)
    if row is not None:
        await db.delete(row)
        await db.commit()
    return {"configured": False}


async def test_connection(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """Sends the keys now: the platform answers - the address and the secret are right."""
    row = await db.get(RelayAgentSettings, company_id)
    secret = decrypt_secret(row.secret_encrypted) if row else None
    if row is None or not secret:
        raise RelayAgentError("Guarde primeiro o endereço e o código do relé")
    async with make_client(row.relay_url, secret, relay_transport) as client:
        try:
            await push_keys(client, db, company_id)
        except RelayAgentError as e:
            await _failed(db, company_id, str(e))
            raise
    await _ok(db, company_id, 0)
    return await view(db, company_id)


# ------------------------------------------------------------------------------------------------- talking to the relay

def _refusal(response: httpx.Response) -> RelayAgentError:
    if response.status_code == 401:
        return RelayAgentError("Código do relé recusado pela plataforma (inválido ou desativado)")
    if response.status_code == 404:
        return RelayAgentError("Este endereço não é um relé RM SOFT")
    return RelayAgentError(f"A plataforma respondeu {response.status_code}")


async def _call(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> httpx.Response:
    try:
        response = await client.request(method, AGENT_PATH + path, **kwargs)
    except httpx.HTTPError as e:
        raise RelayAgentError(f"Sem ligação à plataforma ({type(e).__name__})")
    if response.status_code >= 300:
        raise _refusal(response)
    return response


async def active_keys(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(select(ApiKey).where(ApiKey.company_id == company_id, ApiKey.is_active.is_(True)))).scalars()
    return [{"id": str(k.id), "name": k.name, "hash": k.key_hash, "scopes": list(k.scopes or [])} for k in rows]


async def push_keys(client: httpx.AsyncClient, db: AsyncSession, company_id: uuid.UUID) -> None:
    await _call(client, "PUT", "/keys", json=await active_keys(db, company_id))


async def push_snapshot(client: httpx.AsyncClient, db: AsyncSession, company_id: uuid.UUID) -> None:
    from app.services.relay_snapshot import build_snapshot
    await _call(client, "PUT", "/snapshot", json=await build_snapshot(db, company_id))
    row = await db.get(RelayAgentSettings, company_id)
    if row is not None:
        row.last_snapshot_at = datetime.now(timezone.utc)
        await db.commit()


async def run_request(item: dict) -> dict:
    """One call of the site, run on this server's own API (in-process: the agent's token never leaves it)."""
    from app.main import app
    from app.services.api_key_service import AGENT_TOKEN
    headers = {"X-Relay-Agent": AGENT_TOKEN, "X-Relay-Key-Hash": item["key_hash"]}
    if item.get("idempotency_key"):
        headers["Idempotency-Key"] = item["idempotency_key"]
    url = "/api/public/v1" + item["path"] + ("?" + item["query"] if item.get("query") else "")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://relay.local") as local:
        response = await local.request(item["method"], url, headers=headers,
                                       json=item["body"] if item.get("body") is not None else None)
    content_type = response.headers.get("content-type", "")
    if not response.content:
        body = None
    elif "application/json" in content_type:
        body = response.json()
    else:  # a PDF: it travels in the JSON, the relay gives it back as a file
        body = {"__binary__": True, "content_type": content_type,
                "disposition": response.headers.get("content-disposition"),
                "base64": base64.b64encode(response.content).decode()}
    return {"id": item["id"], "status_code": response.status_code, "body": body}


async def cycle(client: httpx.AsyncClient, company_id: uuid.UUID, wait: bool = True) -> int:
    """One long poll: what the site asked, run here and answered. Returns how many."""
    taken = (await _call(client, "POST", "/pull", params={"wait": "true" if wait else "false"})).json()
    results = []
    for item in taken:
        try:
            results.append(await run_request(item))
        except Exception:  # noqa: BLE001 - one bad call never stops the others
            log.exception("relay request %s failed", item.get("id"))
            results.append({"id": item["id"], "status_code": 500,
                            "body": {"detail": "Erro no servidor da empresa ao tratar o pedido"}})
    if results:
        await _call(client, "POST", "/results", json=results)
    async with agent_session() as db:
        await _ok(db, company_id, len(results))
    return len(results)


async def _ok(db: AsyncSession, company_id: uuid.UUID, done: int) -> None:
    row = await db.get(RelayAgentSettings, company_id)
    if row is not None:
        row.last_ok_at, row.requests_done = datetime.now(timezone.utc), row.requests_done + done
        await db.commit()


async def _failed(db: AsyncSession, company_id: uuid.UUID, message: str) -> None:
    row = await db.get(RelayAgentSettings, company_id)
    if row is not None:
        row.last_error, row.last_error_at = message[:300], datetime.now(timezone.utc)
        await db.commit()


# ------------------------------------------------------------------------------------------------------- the loops

async def agent_loop(company_id: uuid.UUID) -> None:
    """While the company's link is active: keys every minute, photo every 5 minutes, and the long poll in between."""
    failures = 0
    # kept across the settings re-reads (every 30 s): the keys every minute, the photo every 5 minutes
    keys_at = snapshot_at = datetime.min.replace(tzinfo=timezone.utc)
    while True:
        async with agent_session() as db:
            row = await db.get(RelayAgentSettings, company_id)
            secret = decrypt_secret(row.secret_encrypted) if row else None
            if row is None or not row.is_active or not secret:
                return
            url = row.relay_url
        try:
            async with make_client(url, secret, relay_transport) as client:
                checked_at = datetime.now(timezone.utc)
                while datetime.now(timezone.utc) - checked_at < RECHECK_EVERY:
                    now = datetime.now(timezone.utc)
                    async with agent_session() as db:
                        if now - keys_at >= KEYS_EVERY:
                            await push_keys(client, db, company_id)
                            keys_at = now
                        if now - snapshot_at >= SNAPSHOT_EVERY:
                            await push_snapshot(client, db, company_id)
                            snapshot_at = now
                    await cycle(client, company_id)
                    failures = 0
        except Exception as e:  # noqa: BLE001 - no internet, platform down...: tried again, never stops
            message = str(e) if isinstance(e, RelayAgentError) else f"Erro: {type(e).__name__}"
            log.info("relay agent %s: %s", company_id, message)
            async with agent_session() as db:
                await _failed(db, company_id, message)
            keys_at = snapshot_at = datetime.min.replace(tzinfo=timezone.utc)  # back: everything sent again at once
            await asyncio.sleep(BACKOFF[min(failures, len(BACKOFF) - 1)])
            failures += 1


_running: dict[uuid.UUID, asyncio.Task] = {}


async def supervise_once() -> None:
    async with agent_session() as db:
        active = (await db.execute(select(RelayAgentSettings.company_id).where(
            RelayAgentSettings.is_active.is_(True)))).scalars().all()
    for company_id in active:
        task = _running.get(company_id)
        if task is None or task.done():
            _running[company_id] = asyncio.create_task(agent_loop(company_id))


async def supervisor_loop() -> None:
    """Started with the server: a loop for each company with an active link (a link switched on later: within 30 s)."""
    while True:
        try:
            await supervise_once()
        except Exception:  # noqa: BLE001
            log.exception("relay supervisor failed")
        await asyncio.sleep(SUPERVISE_SECONDS)
