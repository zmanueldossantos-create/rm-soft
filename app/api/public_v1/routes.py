"""The public API's routes (v1). Field names in English, messages in PT-PT; the documentation (PT) is at
/api/public/v1/docs."""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public_v1.deps import ApiContext, api_key
from app.core.database import get_db
from app.models.company import Company
from app.services import api_key_service as keys

PREFIX = "/api/public/v1"
router = APIRouter(prefix=PREFIX, tags=["API pública"])

DESCRIPTION = """
API pública do RM SOFT, para ligar outros programas da empresa (site, loja online, motor de reservas, relatórios).

**Autenticação:** cada pedido leva a chave de acesso criada pelo gestor em *Configurações → Integração API*:
`Authorization: Bearer rmk_...` (ou `X-API-Key: rmk_...`). A chave só é mostrada uma vez, quando é criada.

**Permissões:** cada chave tem as suas (Catálogo, Clientes, Documentos, Reservas). Sem a permissão: 403.

**Limite:** 60 pedidos por minuto por chave (acima: 429, aguarde um minuto).

**Erros:** a resposta traz `{"detail": "mensagem"}` em português.
"""


@router.get("/ping", summary="Testar a chave")
async def ping(ctx: ApiContext = Depends(api_key()), db: AsyncSession = Depends(get_db)):
    """Confirma que a chave funciona: a empresa, o nome da chave e as suas permissões."""
    company = await db.get(Company, ctx.company_id)
    return {"company": company.short_name or company.name, "nif": company.nif, "key": ctx.key.name,
            "scopes": list(ctx.key.scopes or [])}


# ------------------------------------------------------------------------------------------- the documentation (PT)
docs_router = APIRouter(prefix=PREFIX, include_in_schema=False)


@docs_router.get("/openapi.json")
async def public_openapi():
    return get_openapi(title="RM SOFT - API pública", version="1.0", description=DESCRIPTION, routes=router.routes)


@docs_router.get("/docs", response_class=HTMLResponse)
async def public_docs():
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="RM SOFT - API pública")
