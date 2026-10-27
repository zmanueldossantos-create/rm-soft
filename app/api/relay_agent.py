"""
The agent's side of the relay (RELAY_SERVER=true, the RM SOFT platform): the client's server, authenticated by its
secret (Authorization: Bearer rmr_...), takes the waiting requests and answers them, and sends its keys and its photo.
Nothing here is reachable without RELAY_SERVER.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.relay import RelayLink
from app.services import relay_service as relay

router = APIRouter(prefix="/api/relay/v1/agent", tags=["relay"], include_in_schema=False)


async def agent(request: Request, db: AsyncSession = Depends(get_db)) -> RelayLink:
    if not get_settings().RELAY_SERVER:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    header = request.headers.get("authorization", "")
    link = await relay.agent_link(db, header[7:].strip() if header.lower().startswith("bearer ") else "")
    if link is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código do relé inválido ou desativado")
    return link


class KeyItem(BaseModel):
    id: str
    name: str
    hash: str
    scopes: list[str] = []


class ResultItem(BaseModel):
    id: str
    status_code: int
    body: dict | list | None = None


@router.post("/pull")
async def pull(wait: bool = True, link: RelayLink = Depends(agent)):
    """The waiting requests (a long poll: up to 20 s when there is none)."""
    return await relay.pull(link.id, relay.PULL_WAIT_SECONDS if wait else 0)


@router.post("/results")
async def results(items: list[ResultItem], link: RelayLink = Depends(agent), db: AsyncSession = Depends(get_db)):
    done = await relay.save_results(db, link, [i.model_dump() for i in items])
    for row in done:
        if row.callback_url:
            asyncio.create_task(relay.send_webhook(row))  # never makes the agent wait
    return {"saved": len(done)}


@router.put("/keys")
async def put_keys(items: list[KeyItem], link: RelayLink = Depends(agent), db: AsyncSession = Depends(get_db)):
    return {"keys": await relay.set_keys(db, link, [i.model_dump() for i in items])}


@router.put("/snapshot")
async def put_snapshot(snapshot: dict, link: RelayLink = Depends(agent), db: AsyncSession = Depends(get_db)):
    await relay.set_snapshot(db, link, snapshot)
    return {"saved": True}
