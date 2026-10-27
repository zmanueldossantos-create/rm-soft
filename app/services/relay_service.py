"""
The relay of the public API, on the RM SOFT platform (RELAY_SERVER=true) - see app.models.relay.

The agent of a client's server authenticates with its secret («rmr_...», given once when the link is activated);
it takes the waiting requests (pull, a long poll: the site's call is answered within a second when the server is on),
sends the answers back (results), its keys' hashes (keys) and its photo (snapshot).
"""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.relay import RelayLink, RelayRequest

log = logging.getLogger(__name__)

SECRET_PREFIX = "rmr_"
ONLINE_SECONDS = 30          # the agent asked within this time: the server is on
WAIT_SECONDS = 10            # the site's call waits this long for the server's answer
PULL_WAIT_SECONDS = 20       # the agent's long poll
LEASE_SECONDS = 60           # a request taken and not answered: given again after this
POLL_SECONDS = 0.3
KEEP_DONE_DAYS = 7           # an answered request is kept (the site reads its answer), then deleted
KEEP_WAITING_DAYS = 30       # a request never taken (server off for a month) is deleted
WEBHOOK_TRIES = 3

# its own sessions (the site's call waits outside any request session); replaced in the tests
relay_session = AsyncSessionLocal


class RelayError(Exception):
    """Refused - the message is shown as it is."""


def hash_secret(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def is_online(link: RelayLink, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return link.last_seen_at is not None and now - link.last_seen_at < timedelta(seconds=ONLINE_SECONDS)


# ------------------------------------------------------------------------------------------- the link (SUPER_ADMIN)

async def link_view(db: AsyncSession, company_id: uuid.UUID) -> dict | None:
    link = (await db.execute(select(RelayLink).where(RelayLink.company_id == company_id))).scalar_one_or_none()
    if link is None:
        return None
    waiting = (await db.execute(select(RelayRequest.id).where(
        RelayRequest.company_id == company_id, RelayRequest.status != "FEITO"))).all()
    return {"is_active": link.is_active, "secret_prefix": link.secret_prefix, "online": is_online(link),
            "last_seen_at": link.last_seen_at, "snapshot_at": link.snapshot_at, "keys": len(link.keys or []),
            "waiting": len(waiting), "created_at": link.created_at}


async def activate(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """A new secret for the company's agent (the previous one stops working): returned once, with «secret»."""
    from app.services.plan_service import current_contract
    contract = await current_contract(db, company_id)
    if contract is None or contract.deployment_mode != "LOCAL":
        raise RelayError("O relé é para as empresas instaladas em local (o contrato desta empresa não é LOCAL)")
    plain = SECRET_PREFIX + secrets.token_urlsafe(32)[:40]
    link = (await db.execute(select(RelayLink).where(RelayLink.company_id == company_id))).scalar_one_or_none()
    if link is None:
        link = RelayLink(company_id=company_id, secret_hash="", secret_prefix="")
        db.add(link)
    link.secret_hash, link.secret_prefix, link.is_active = hash_secret(plain), plain[:12], True
    await db.commit()
    return {**(await link_view(db, company_id)), "secret": plain}


async def deactivate(db: AsyncSession, company_id: uuid.UUID) -> dict | None:
    link = (await db.execute(select(RelayLink).where(RelayLink.company_id == company_id))).scalar_one_or_none()
    if link is not None:
        link.is_active = False
        await db.commit()
    return await link_view(db, company_id)


# --------------------------------------------------------------------------------------------------------- the agent

async def agent_link(db: AsyncSession, plain: str) -> RelayLink | None:
    if not plain or not plain.startswith(SECRET_PREFIX):
        return None
    return (await db.execute(select(RelayLink).where(RelayLink.secret_hash == hash_secret(plain),
                                                     RelayLink.is_active.is_(True)))).scalar_one_or_none()


async def set_keys(db: AsyncSession, link: RelayLink, keys: list[dict]) -> int:
    """The company's ACTIVE keys - only their hashes, names and rights (a revoked key disappears from here)."""
    link.keys = [{"id": str(k["id"]), "name": str(k["name"])[:100], "hash": str(k["hash"]),
                  "scopes": [str(s) for s in k.get("scopes") or []]} for k in keys]
    link.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    return len(link.keys)


async def set_snapshot(db: AsyncSession, link: RelayLink, snapshot: dict) -> None:
    link.snapshot, link.snapshot_at = snapshot, datetime.now(timezone.utc)
    link.last_seen_at = link.snapshot_at
    await db.commit()


async def take(db: AsyncSession, link: RelayLink, limit: int = 20) -> list[dict]:
    """The waiting requests, oldest first (and those taken but never answered); the agent is seen now."""
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(RelayRequest).where(
        RelayRequest.company_id == link.company_id,
        or_(RelayRequest.status == "PENDENTE",
            (RelayRequest.status == "EM_CURSO") & (RelayRequest.picked_at < now - timedelta(seconds=LEASE_SECONDS))))
        .order_by(RelayRequest.created_at).limit(limit).with_for_update(skip_locked=True))).scalars().all()
    for row in rows:
        row.status, row.picked_at, row.attempts = "EM_CURSO", now, row.attempts + 1
    link.last_seen_at = now
    await db.commit()
    return [{"id": str(r.id), "method": r.method, "path": r.path, "query": r.query, "body": r.body,
             "key_hash": r.key_hash, "idempotency_key": r.idempotency_key} for r in rows]


async def pull(link_id: uuid.UUID, wait_seconds: float = PULL_WAIT_SECONDS) -> list[dict]:
    """The agent's long poll: what is waiting now, or what arrives within wait_seconds."""
    deadline = asyncio.get_event_loop().time() + wait_seconds
    while True:
        async with relay_session() as db:
            link = await db.get(RelayLink, link_id)
            if link is None or not link.is_active:
                return []
            taken = await take(db, link)
        if taken or asyncio.get_event_loop().time() >= deadline:
            return taken
        await asyncio.sleep(POLL_SECONDS)


async def save_results(db: AsyncSession, link: RelayLink, results: list[dict]) -> list[RelayRequest]:
    """The answers of the server: [{"id", "status_code", "body"}]. Returns the requests answered now."""
    done = []
    now = datetime.now(timezone.utc)
    for item in results:
        try:
            request_id = uuid.UUID(str(item["id"]))
        except (KeyError, ValueError):
            continue
        row = await db.get(RelayRequest, request_id)
        if row is None or row.company_id != link.company_id or row.status == "FEITO":
            continue
        row.status, row.done_at = "FEITO", now
        row.response_status, row.response_body = int(item.get("status_code") or 500), item.get("body")
        done.append(row)
    link.last_seen_at = now
    # the clean-up: answered requests after KEEP_DONE_DAYS, never-taken ones after KEEP_WAITING_DAYS
    await db.execute(delete(RelayRequest).where(RelayRequest.company_id == link.company_id, or_(
        (RelayRequest.status == "FEITO") & (RelayRequest.done_at < now - timedelta(days=KEEP_DONE_DAYS)),
        RelayRequest.created_at < now - timedelta(days=KEEP_WAITING_DAYS))))
    await db.commit()
    return done


# ---------------------------------------------------------------------------------------------------------- the site

def request_view(row: RelayRequest) -> dict:
    return {"request_id": str(row.id), "status": "FEITO" if row.status == "FEITO" else "PENDENTE",
            "method": row.method, "path": row.path, "created_at": row.created_at.isoformat() if row.created_at else None,
            "done_at": row.done_at.isoformat() if row.done_at else None,
            "response": {"status_code": row.response_status, "body": row.response_body} if row.status == "FEITO" else None}


async def wait_done(request_id: uuid.UUID, seconds: float = WAIT_SECONDS) -> RelayRequest | None:
    deadline = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(POLL_SECONDS)
        async with relay_session() as db:
            row = await db.get(RelayRequest, request_id)
            if row is not None and row.status == "FEITO":
                return row
    return None


# ------------------------------------------------------------------------------------------------------- the webhook

def callback_allowed(url: str) -> bool:
    """https/http to a public address only: the platform never calls its own network (SSRF)."""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except OSError:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            return False
    return True


def signature(key_hash: str, body: bytes) -> str:
    """HMAC-SHA256 of the body, keyed with the SHA-256 (hex) of the site's own access key."""
    return hmac.new(key_hash.encode(), body, hashlib.sha256).hexdigest()


async def webhook_post(url: str, body: bytes, headers: dict) -> int:
    import httpx
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        return (await client.post(url, content=body, headers=headers)).status_code


async def send_webhook(row: RelayRequest) -> bool:
    """The answer, POSTed to the site's X-Callback-Url - X-RM-Signature: see signature()."""
    if not row.callback_url or not await asyncio.to_thread(callback_allowed, row.callback_url):
        return False
    body = json.dumps(request_view(row), ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json", "X-RM-Signature": signature(row.key_hash, body),
               "X-RM-Request-Id": str(row.id)}
    for attempt in range(WEBHOOK_TRIES):
        try:
            if await webhook_post(row.callback_url, body, headers) < 300:
                return True
        except Exception as e:  # noqa: BLE001 - the site's server may be down: tried again
            log.info("relay webhook %s: %s", row.id, e)
        await asyncio.sleep(2 * (attempt + 1))
    return False
