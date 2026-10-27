"""The public API's routes (v1). Field names in English, messages in PT-PT; the documentation (PT) is at
/api/public/v1/docs."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public_v1 import schemas
from app.api.public_v1.deps import ApiContext, api_key
from app.core.database import get_db
from app.models.company import Company
from app.services import api_key_service as keys
from app.services import public_api_service as public

PREFIX = "/api/public/v1"
router = APIRouter(prefix=PREFIX, tags=["API pública"])

DESCRIPTION = """
API pública do RM SOFT, para ligar outros programas da empresa (site, loja online, motor de reservas, relatórios).

**Autenticação:** cada pedido leva a chave de acesso criada pelo gestor em *Configurações → Integração API*:
`Authorization: Bearer rmk_...` (ou `X-API-Key: rmk_...`). A chave só é mostrada uma vez, quando é criada.

**Permissões:** cada chave tem as suas (Catálogo, Clientes, Documentos, Reservas). Sem a permissão: 403.

**Limite:** 60 pedidos por minuto por chave (acima: 429, aguarde um minuto).

**Listas:** paginadas (`page`, `page_size` até 200) e com `total`. Para sincronizar, peça só o que mudou desde a
última vez com `updated_since`.

**Preços:** `price` é o preço sem IVA, `price_with_vat` o que o cliente paga (IVA de 0, 5 ou 14 %).

**Erros:** a resposta traz `{"detail": "mensagem"}` em português (um dado inválido: 422, com a lista dos campos).
"""


@router.get("/ping", summary="Testar a chave", tags=["Chave"])
async def ping(ctx: ApiContext = Depends(api_key()), db: AsyncSession = Depends(get_db)):
    """Confirma que a chave funciona: a empresa, o nome da chave e as suas permissões."""
    company = await db.get(Company, ctx.company_id)
    return {"company": company.short_name or company.name, "nif": company.nif, "key": ctx.key.name,
            "scopes": list(ctx.key.scopes or [])}


NOT_FOUND = {404: {"description": "Não encontrado (ou de outra empresa)"}}


def _not_found(e: LookupError):
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ------------------------------------------------------------------------------------------------------- catalogue

@router.get("/catalog/products", response_model=schemas.ProductPage, summary="Produtos", tags=["Catálogo"])
async def products(search: str | None = Query(None, description="Nome, código ou marca"),
                   category: str | None = Query(None, description="Nome da categoria"),
                   barcode: str | None = Query(None, description="Código de barras (também o das unidades de venda)"),
                   updated_since: datetime | None = Query(None, description="Só os alterados desde (ISO 8601)"),
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=public.MAX_PAGE_SIZE),
                   ctx: ApiContext = Depends(api_key("catalog")), db: AsyncSession = Depends(get_db)):
    """Os produtos à venda, com preço, IVA e stock. Os de uso interno, sem preço ou inativos não aparecem."""
    return await public.list_products(db, ctx.company_id, search, category, barcode, updated_since, page, page_size)


@router.get("/catalog/products/{product_id}", response_model=schemas.Product, summary="Um produto",
            tags=["Catálogo"], responses=NOT_FOUND)
async def product(product_id: uuid.UUID, ctx: ApiContext = Depends(api_key("catalog")),
                  db: AsyncSession = Depends(get_db)):
    """O produto, com o stock de cada armazém."""
    try:
        return await public.get_product(db, ctx.company_id, product_id)
    except LookupError as e:
        raise _not_found(e)


@router.get("/catalog/categories", response_model=list[schemas.Category], summary="Categorias", tags=["Catálogo"])
async def categories(ctx: ApiContext = Depends(api_key("catalog")), db: AsyncSession = Depends(get_db)):
    return await public.list_categories(db, ctx.company_id)


@router.get("/catalog/services", response_model=schemas.ServicePage, summary="Serviços", tags=["Catálogo"])
async def services(search: str | None = Query(None, description="Nome ou código"),
                   updated_since: datetime | None = Query(None, description="Só os alterados desde (ISO 8601)"),
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=public.MAX_PAGE_SIZE),
                   ctx: ApiContext = Depends(api_key("catalog")), db: AsyncSession = Depends(get_db)):
    """Os serviços à venda (quartos, lavandaria, consultas...), com preço e IVA."""
    return await public.list_services(db, ctx.company_id, search, updated_since, page, page_size)


@router.get("/catalog/services/{service_id}", response_model=schemas.Service, summary="Um serviço",
            tags=["Catálogo"], responses=NOT_FOUND)
async def service(service_id: uuid.UUID, ctx: ApiContext = Depends(api_key("catalog")),
                  db: AsyncSession = Depends(get_db)):
    try:
        return await public.get_service(db, ctx.company_id, service_id)
    except LookupError as e:
        raise _not_found(e)


# ------------------------------------------------------------------------------------------------------- customers

@router.get("/customers", response_model=schemas.CustomerPage, summary="Clientes", tags=["Clientes"])
async def customers(search: str | None = Query(None, description="Nome, código ou email"),
                    nif: str | None = Query(None, description="Procurar pelo NIF exato"),
                    email: str | None = Query(None), phone: str | None = Query(None, description="Ex.: +244923456789"),
                    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=public.MAX_PAGE_SIZE),
                    ctx: ApiContext = Depends(api_key("customers")), db: AsyncSession = Depends(get_db)):
    """Os clientes ativos. Antes de criar um cliente, procure-o pelo NIF."""
    return await public.list_customers(db, ctx.company_id, search, nif, email, phone, page, page_size)


@router.get("/customers/{customer_id}", response_model=schemas.Customer, summary="Um cliente", tags=["Clientes"],
            responses=NOT_FOUND)
async def customer(customer_id: uuid.UUID, ctx: ApiContext = Depends(api_key("customers")),
                   db: AsyncSession = Depends(get_db)):
    try:
        return await public.get_customer(db, ctx.company_id, customer_id)
    except LookupError as e:
        raise _not_found(e)


@router.post("/customers", response_model=schemas.Customer, status_code=status.HTTP_201_CREATED,
             summary="Criar um cliente", tags=["Clientes"],
             responses={409: {"model": schemas.AlreadyExists, "description": "Já existe um cliente com este NIF"}})
async def create_customer(payload: schemas.CustomerCreate, ctx: ApiContext = Depends(api_key("customers")),
                          db: AsyncSession = Depends(get_db)):
    """Cria o cliente. Se o NIF já existir, responde 409 com o `id` do cliente existente: use esse."""
    try:
        return await public.create_customer(db, ctx.company_id, payload.model_dump(), ctx.key.name)
    except public.AlreadyExistsError as e:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(e), "id": str(e.existing_id)})
    except public.PublicApiError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


# ------------------------------------------------------------------------------------------- the documentation (PT)
docs_router = APIRouter(prefix=PREFIX, include_in_schema=False)


@docs_router.get("/openapi.json")
async def public_openapi():
    return get_openapi(title="RM SOFT - API pública", version="1.0", description=DESCRIPTION, routes=router.routes)


@docs_router.get("/docs", response_class=HTMLResponse)
async def public_docs():
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="RM SOFT - API pública")
