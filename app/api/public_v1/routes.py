"""The public API's routes (v1). Field names in English, messages in PT-PT; the documentation (PT) is at
/api/public/v1/docs."""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.exc import IntegrityError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public_v1 import schemas
from app.api.public_v1.deps import ApiContext, api_key
from app.core.database import get_db
from app.models.company import Company
from app.services import api_key_service as keys
from app.services import public_api_service as public
from app.services import invoice_service as inv
from app.services import public_bookings_service as bookings
from app.services import public_documents_service as documents
from app.services.fiscal_period_service import PeriodClosedError
from app.services.pharmacy_service import MedicineError

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

**Documentos:** cada emissão leva o cabeçalho `Idempotency-Key` (um identificador único por pedido, ex. um UUID ou
o n.º da encomenda). Se o mesmo pedido for enviado de novo com a mesma chave (falha de rede...), a resposta é a mesma
e nada é emitido duas vezes.

**Segurança:** a chave nunca vai no código de uma página web (o visitante via-a): o pedido parte do servidor do site.

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


# ------------------------------------------------------------------------------------------------------ activities

@router.get("/activities", response_model=list[schemas.Activity], summary="Atividades", tags=["Documentos"])
async def activities(ctx: ApiContext = Depends(api_key()), db: AsyncSession = Depends(get_db)):
    """As atividades da empresa (Hotel, Restaurante...). Só é preciso indicar uma ao emitir quando há várias."""
    return await documents.list_activities(db, ctx.company_id)


# ------------------------------------------------------------------------------------------------------- documents

# the refusals of the invoicing services, answered with their message (never a 500)
_ISSUE_ERRORS = (LookupError, public.PublicApiError, PeriodClosedError, MedicineError, inv.ProductNotFoundError,
                 inv.CustomerNotFoundError, inv.ActivityNotFoundError, inv.EmptyInvoiceError, inv.StockUnavailableError,
                 inv.DocumentTypeNotConfiguredError, inv.SeriesNotConfiguredError, inv.PaymentAmountMismatchError,
                 inv.PaymentMethodNotAllowedError, inv.MissingExemptionReasonError, inv.CashPointRequiredError)


def _issue_error(e: Exception) -> HTTPException:
    if isinstance(e, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, (PeriodClosedError, inv.StockUnavailableError, inv.SeriesNotConfiguredError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


def _replayed(row) -> JSONResponse:
    return JSONResponse(status_code=row.status_code, content=row.response, headers={"Idempotent-Replayed": "true"})


@router.post("/documents", response_model=schemas.Document, status_code=status.HTTP_201_CREATED,
             summary="Emitir um documento", tags=["Documentos"],
             responses={404: {"description": "Cliente ou atividade não encontrados"},
                        409: {"description": "Período fechado, stock insuficiente ou série em falta"},
                        423: {"description": "Empresa só de leitura (contrato terminado)"}})
async def create_document(payload: schemas.DocumentCreate, request: Request,
                          idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100,
                                                        description="Único por pedido (ex.: um UUID)"),
                          ctx: ApiContext = Depends(api_key("documents")), db: AsyncSession = Depends(get_db)):
    """Emite uma FT, FR ou FP com os preços do catálogo (o pedido só escolhe artigos, quantidades e descontos).
    As faturas (FT, FR) seguem logo para a AGT: o estado vem em `agt` (consulte depois GET /documents/{id})."""
    from app.services.agt_queue import queue_for_agt

    path, body_hash = request.url.path, public.request_hash(payload.model_dump(mode="json"))
    try:
        replay = await public.find_replay(db, ctx.company_id, idempotency_key, path, body_hash)
    except public.IdempotencyConflictError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if replay is not None:
        return _replayed(replay)
    try:
        invoice = await documents.create_document(db, ctx.company_id, payload.model_dump())
        view = await documents.document_view(db, invoice)
        public.remember(db, ctx.company_id, ctx.key.id, idempotency_key, path, body_hash, 201, view, invoice.id)
        await db.commit()
    except IntegrityError:
        # the same key arrived twice at the same moment: the first one won - its answer
        await db.rollback()
        replay = await public.find_replay(db, ctx.company_id, idempotency_key, path, body_hash)
        if replay is None:
            raise
        return _replayed(replay)
    except _ISSUE_ERRORS as e:
        await db.rollback()
        raise _issue_error(e)
    if invoice.invoice_type.value in documents.FISCAL:
        await queue_for_agt(db, invoice)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=view)


@router.get("/documents", response_model=schemas.DocumentPage, summary="Documentos", tags=["Documentos"])
async def list_documents(type: str | None = Query(None, description="FT, FR, FP, NC, ND, RC ou OR"),
                         date_from: date | None = Query(None, description="Desde (AAAA-MM-DD)"),
                         date_to: date | None = Query(None, description="Até (AAAA-MM-DD)"),
                         customer_id: uuid.UUID | None = None,
                         document_reference: str | None = Query(None, description="A sua referência (encomenda)"),
                         updated_since: datetime | None = Query(None, description="Só os alterados desde (estado AGT...)"),
                         page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=public.MAX_PAGE_SIZE),
                         ctx: ApiContext = Depends(api_key("documents")), db: AsyncSession = Depends(get_db)):
    """Todos os documentos da empresa (os emitidos nos ecrãs também), do mais recente ao mais antigo, sem linhas."""
    try:
        return await documents.list_documents(db, ctx.company_id, type, date_from, date_to, customer_id,
                                              document_reference, updated_since, page, page_size)
    except public.PublicApiError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/documents/{document_id}", response_model=schemas.Document, summary="Um documento",
            tags=["Documentos"], responses=NOT_FOUND)
async def get_document(document_id: uuid.UUID, ctx: ApiContext = Depends(api_key("documents")),
                       db: AsyncSession = Depends(get_db)):
    """O documento com as suas linhas e o estado na AGT."""
    try:
        return await documents.document_view(db, await documents.get_document(db, ctx.company_id, document_id))
    except LookupError as e:
        raise _not_found(e)


@router.get("/documents/{document_id}/pdf", summary="PDF de um documento", tags=["Documentos"],
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}, **NOT_FOUND})
async def document_pdf(document_id: uuid.UUID,
                       format: str = Query("a4", pattern="^(a4|thermal)$", description="a4 ou thermal (talão 80 mm)"),
                       ctx: ApiContext = Depends(api_key("documents")), db: AsyncSession = Depends(get_db)):
    """O PDF do documento, igual ao impresso no RM SOFT (com QR code e ATCUD)."""
    from app.services.invoice_pdf_service import render_invoice_pdf
    from app.services.invoice_service import InvoiceNotFoundError
    try:
        pdf_bytes, filename = await render_invoice_pdf(db, ctx.company_id, document_id, format)
    except InvoiceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


# -------------------------------------------------------------------------------------------------------- bookings

def _booking_error(e: Exception) -> HTTPException:
    from app.services.booking_service import BookingOverlapError
    if isinstance(e, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, (bookings.NoResourceFreeError, BookingOverlapError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


def _booking_errors() -> tuple:
    from app.services import booking_service as bs
    return (LookupError, public.PublicApiError, bookings.NoResourceFreeError, bs.BookingOverlapError,
            bs.InvalidBookingRangeError, bs.ServiceRequiredError, bs.IncompatibleServiceError)


@router.get("/bookings/availability", response_model=list[schemas.Availability], summary="Disponibilidade",
            tags=["Reservas"])
async def booking_availability(check_in: date | None = Query(None, description="Dia de chegada (hotel)"),
                               check_out: date | None = Query(None, description="Dia de partida (hotel)"),
                               starts_at: datetime | None = Query(None, description="...ou início exato"),
                               ends_at: datetime | None = Query(None, description="...e fim exato"),
                               resource_type_id: uuid.UUID | None = Query(None, description="Só este tipo"),
                               party_size: int | None = Query(None, ge=1, description="Pessoas (capacidade)"),
                               ctx: ApiContext = Depends(api_key("bookings")), db: AsyncSession = Depends(get_db)):
    """Por tipo de recurso (Quarto duplo, Suite...): quantos estão livres em todo o período, e as tarifas com o total
    da estadia. Um hotel pede por dias: as horas de entrada e saída são as do tipo (ex.: 14:00 -> 12:00)."""
    try:
        return await bookings.availability(db, ctx.company_id, check_in, check_out, starts_at, ends_at,
                                           resource_type_id, party_size)
    except _booking_errors() as e:
        raise _booking_error(e)


@router.post("/bookings", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED,
             summary="Criar uma reserva", tags=["Reservas"],
             responses={409: {"description": "Já não há recurso livre neste período"},
                        423: {"description": "Empresa só de leitura (contrato terminado)"}})
async def create_booking(payload: schemas.BookingCreate, request: Request,
                         idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100,
                                                       description="Único por pedido (ex.: o n.º da reserva no site)"),
                         ctx: ApiContext = Depends(api_key("bookings")), db: AsyncSession = Depends(get_db)):
    """A reserva chega PENDENTE: a receção confirma-a (consulte depois GET /bookings/{id}). Peça um tipo
    (resource_type_id): o RM SOFT escolhe um recurso livre."""
    from app.services.notification_service import notify_online_booking

    path, body_hash = request.url.path, public.request_hash(payload.model_dump(mode="json"))
    try:
        replay = await public.find_replay(db, ctx.company_id, idempotency_key, path, body_hash)
    except public.IdempotencyConflictError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if replay is not None:
        return _replayed(replay)
    key_name = ctx.key.name
    try:
        booking = await bookings.create_booking(db, ctx.company_id, ctx.key, payload.model_dump())
        view = await bookings.booking_view(db, booking)
        public.remember(db, ctx.company_id, ctx.key.id, idempotency_key, path, body_hash, 201, view, booking.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replay = await public.find_replay(db, ctx.company_id, idempotency_key, path, body_hash)
        if replay is None:
            raise
        return _replayed(replay)
    except _booking_errors() as e:
        await db.rollback()
        raise _booking_error(e)
    await notify_online_booking(db, booking, key_name)  # the reception is told (Telegram, email)
    await db.commit()
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=view)


@router.get("/bookings", response_model=schemas.BookingPage, summary="Reservas", tags=["Reservas"])
async def list_bookings(external_reference: str | None = Query(None, description="O n.º da reserva no site"),
                        status_: str | None = Query(None, alias="status", description="PENDENTE, CONFIRMADA..."),
                        date_from: date | None = Query(None, description="Estadias desde (AAAA-MM-DD)"),
                        date_to: date | None = Query(None, description="Estadias até (AAAA-MM-DD)"),
                        updated_since: datetime | None = Query(None, description="Só as alteradas desde"),
                        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=public.MAX_PAGE_SIZE),
                        ctx: ApiContext = Depends(api_key("bookings")), db: AsyncSession = Depends(get_db)):
    """As reservas feitas pela API (as do balcão não aparecem). Para seguir as confirmações: updated_since."""
    try:
        return await bookings.list_bookings(db, ctx.company_id, external_reference, status_, date_from, date_to,
                                            updated_since, page, page_size)
    except public.PublicApiError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/bookings/{booking_id}", response_model=schemas.BookingOut, summary="Uma reserva", tags=["Reservas"],
            responses=NOT_FOUND)
async def get_booking(booking_id: uuid.UUID, ctx: ApiContext = Depends(api_key("bookings")),
                      db: AsyncSession = Depends(get_db)):
    try:
        return await bookings.booking_view(db, await bookings.get_booking(db, ctx.company_id, booking_id))
    except LookupError as e:
        raise _not_found(e)


@router.post("/bookings/{booking_id}/cancel", response_model=schemas.BookingOut, summary="Cancelar uma reserva",
             tags=["Reservas"], responses=NOT_FOUND)
async def cancel_booking(booking_id: uuid.UUID, ctx: ApiContext = Depends(api_key("bookings")),
                         db: AsyncSession = Depends(get_db)):
    """Só antes do check-in. Cancelar de novo uma reserva cancelada não muda nada."""
    try:
        return await bookings.booking_view(db, await bookings.cancel_booking(db, ctx.company_id, booking_id))
    except (LookupError, public.PublicApiError) as e:
        raise _booking_error(e)


# ------------------------------------------------------------------------------------------- the documentation (PT)
docs_router = APIRouter(prefix=PREFIX, include_in_schema=False)


_spec: dict | None = None


def public_spec() -> dict:
    global _spec
    if _spec is None:
        _spec = get_openapi(title="RM SOFT - API pública", version="1.0", description=DESCRIPTION, routes=router.routes)
    return _spec


@docs_router.get("/openapi.json")
async def public_openapi():
    return public_spec()


@docs_router.get("/docs", response_class=HTMLResponse)
async def public_docs():
    """The documentation in Portuguese - one self-contained page (it opens without internet)."""
    from app.api.public_v1.docs_page import render
    return render(public_spec())


@docs_router.get("/docs/experimentar", response_class=HTMLResponse)
async def public_docs_try():
    """The interactive page (Swagger: «Authorize», «Try it out») - its files come from the internet."""
    return get_swagger_ui_html(openapi_url=PREFIX + "/openapi.json", title="RM SOFT - API pública (experimentar)")
