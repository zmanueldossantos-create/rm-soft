"""
The public API's guard: the access key (Authorization: Bearer rmk_..., or X-API-Key), the plan's option, the limit
of calls, the key's rights, and the contract (a read-only company still reads, writes nothing).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.request_context import current_user_id
from app.models.api_key import ApiKey
from app.services import api_key_service as keys
from app.services.plan_service import has_option, is_read_only, read_only_message


@dataclass
class ApiContext:
    key: ApiKey
    company_id: uuid.UUID


# Declared as security schemes, so the documentation shows its «Authorize» button (where the key is pasted)
_bearer = HTTPBearer(auto_error=False, scheme_name="Chave (Bearer)",
                     description="Authorization: Bearer rmk_... (cole só a chave)")
_header = APIKeyHeader(name="X-API-Key", auto_error=False, scheme_name="Chave (X-API-Key)",
                       description="Em alternativa: o cabeçalho X-API-Key")


def api_key(scope: str | None = None):
    """Depends(api_key("documents")): the call's company and key, once every check passed."""
    async def api_key_checker(request: Request, db: AsyncSession = Depends(get_db),
                              bearer: HTTPAuthorizationCredentials | None = Security(_bearer),
                              header_key: str | None = Security(_header)) -> ApiContext:
        plain = (bearer.credentials if bearer else "") or (header_key or "")
        key = await keys.find_key(db, plain.strip())
        if key is not None:
            # the journal (app.main's middleware) writes the call under this key, whatever its answer
            request.state.api_key = {"id": key.id, "company_id": key.company_id,
                                     "name": key.name if key.is_active else key.name + " (revogada)"}
        if key is None or not key.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave de acesso inválida ou revogada",
                                headers={"WWW-Authenticate": "Bearer"})
        if not await has_option(db, key.company_id, keys.OPTION):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="A Integração API não está incluída no plano desta empresa")
        if not keys.within_rate(key.id):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": "60"},
                                detail=f"Limite de {keys.RATE_PER_MINUTE} pedidos por minuto atingido - aguarde um minuto")
        if scope is not None and scope not in (key.scopes or []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Esta chave não tem a permissão «{keys.SCOPES[scope]}»")
        if request.method not in ("GET", "HEAD", "OPTIONS") and await is_read_only(db, key.company_id):
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=read_only_message())
        key.last_used_at = datetime.now(timezone.utc)
        await db.commit()
        current_user_id.set(key.created_by_user_id)  # the documents it creates: in the name of the key's gestor
        return ApiContext(key=key, company_id=key.company_id)

    return api_key_checker
