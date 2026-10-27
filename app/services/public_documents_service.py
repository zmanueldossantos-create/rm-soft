"""
The public API's documents (app.api.public_v1, scope «documents»): another program of the company issues a Fatura
(FT), a Fatura/Recibo (FR) or a Fatura Pro-forma (FP), and reads every document - its lines, its PDF, its state at the
AGT.

The same invoicing services as the screens issue them (invoice_service): the same series and numbers, the same VAT,
stock and period rules, the same AGT queue. What the program cannot choose: the prices (always the catalogue's - only
a discount per line), the cash (an FR is paid by a non-cash method: no cash point online), the date (today).
Every write is idempotent (Idempotency-Key, see public_api_service): sent twice, issued once.
"""
import uuid
from datetime import date, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceType
from app.models.invoice_line import InvoiceLine
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.product import Product
from app.models.service import Service
from app.services.public_api_service import MAX_PAGE_SIZE, PublicApiError, _money, _page, _sellable_products, \
    _sellable_services

# what the program may issue, and the code of every document it may read
ISSUABLE = {"FT": "FACTURA", "FR": "FACTURA_RECIBO", "FP": "PRO_FORMA"}
CODES = {"FACTURA": "FT", "FACTURA_RECIBO": "FR", "NOTA_CREDITO": "NC", "NOTA_DEBITO": "ND", "RECIBO": "RC",
         "PRO_FORMA": "FP", "ORCAMENTO": "OR"}
FISCAL = {"FACTURA", "FACTURA_RECIBO", "NOTA_CREDITO", "NOTA_DEBITO", "RECIBO"}  # sent to the AGT
AGT_STATES = {"PENDENTE": "À espera de envio", "POR_ENVIAR": "A enviar", "ENVIADA": "Aceite pela AGT",
              "ERRO": "Erro no envio - a empresa reenvia"}


# -------------------------------------------------------------------------------------------------------- activities

async def list_activities(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(select(Activity).where(Activity.company_id == company_id, Activity.is_active.is_(True))
                             .order_by(Activity.name))).scalars().all()
    return [{"id": str(a.id), "name": a.name} for a in rows]


async def resolve_activity(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None) -> uuid.UUID:
    """The activity a document is issued under (its series): the one given, or the company's only one."""
    activities = await list_activities(db, company_id)
    if activity_id is not None:
        if str(activity_id) not in {a["id"] for a in activities}:
            raise LookupError("Atividade não encontrada ou inativa")
        return activity_id
    if len(activities) == 1:
        return uuid.UUID(activities[0]["id"])
    if not activities:
        raise PublicApiError("A empresa não tem nenhuma atividade ativa")
    raise PublicApiError("A empresa tem várias atividades: indique activity_id (lista em GET /activities)")


# --------------------------------------------------------------------------------------------------------- issuing

async def _check_lines(db: AsyncSession, company_id: uuid.UUID, lines: list[dict]) -> list[dict]:
    """Every line sells something on sale (the catalogue's rules) - the price is never the program's."""
    product_ids = [l["product_id"] for l in lines if l.get("product_id")]
    service_ids = [l["service_id"] for l in lines if l.get("service_id")]
    on_sale_products = {r[0].id for r in (await db.execute(
        _sellable_products(company_id).where(Product.id.in_(product_ids)))).all()} if product_ids else set()
    on_sale_services = {r[0].id for r in (await db.execute(
        _sellable_services(company_id).where(Service.id.in_(service_ids)))).all()} if service_ids else set()
    out = []
    for n, line in enumerate(lines, start=1):
        if bool(line.get("product_id")) == bool(line.get("service_id")):
            raise PublicApiError(f"Linha {n}: indique product_id ou service_id (só um)")
        if line.get("product_id") and line["product_id"] not in on_sale_products:
            raise PublicApiError(f"Linha {n}: produto não encontrado ou não está à venda")
        if line.get("service_id") and line["service_id"] not in on_sale_services:
            raise PublicApiError(f"Linha {n}: serviço não encontrado ou não está à venda")
        out.append({"product_id": line.get("product_id"), "service_id": line.get("service_id"),
                    "quantity": float(line["quantity"]), "sale_unit_id": line.get("sale_unit_id"),
                    "discount_percent": float(line.get("discount_percent") or 0)})
    return out


async def _payment_method(db: AsyncSession, code: str | None) -> uuid.UUID | None:
    if not code:
        return None
    method = (await db.execute(select(PaymentMethodCatalog).where(
        PaymentMethodCatalog.code == code.strip().upper(), PaymentMethodCatalog.is_active.is_(True)))).scalar_one_or_none()
    if method is None:
        raise PublicApiError(f"Meio de pagamento «{code}» desconhecido (ex.: MB, TB, CC, CD, DE)")
    if not method.allows_receipt:
        raise PublicApiError(f"O meio de pagamento {method.name} não pode ser usado para recebimentos")
    if method.is_cash:
        raise PublicApiError("Numerário só é recebido na caixa: use outro meio de pagamento (ex.: MB, TB, CC)")
    return method.id


async def create_document(db: AsyncSession, company_id: uuid.UUID, data: dict) -> Invoice:
    """data: the validated request (type, activity_id, customer_id, lines, payment_method, due_date,
    document_reference, observations). Only flushed: the caller commits it with its idempotency record, then queues
    the fiscal ones for the AGT."""
    from app.services.invoice_service import create_invoice, create_pro_forma

    invoice_type = ISSUABLE[data["type"]]
    activity_id = await resolve_activity(db, company_id, data.get("activity_id"))
    if data.get("customer_id") is not None:
        customer = (await db.execute(select(Customer.id).where(
            Customer.id == data["customer_id"], Customer.company_id == company_id))).scalar_one_or_none()
        if customer is None:
            raise LookupError("Cliente não encontrado")
    lines = await _check_lines(db, company_id, data["lines"])
    method_id = await _payment_method(db, data.get("payment_method"))
    if invoice_type == "FACTURA_RECIBO" and method_id is None:
        raise PublicApiError("Uma Fatura/Recibo é paga ao emitir: indique payment_method (ex.: MB, TB, CC)")

    if invoice_type == "PRO_FORMA":
        return await create_pro_forma(
            db, company_id=company_id, activity_id=activity_id, customer_id=data.get("customer_id"), lines_input=lines,
            document_reference=data.get("document_reference"), observations=data.get("observations"), commit=False)
    return await create_invoice(
        db, company_id=company_id, activity_id=activity_id, customer_id=data.get("customer_id"),
        invoice_type=invoice_type, lines_input=lines, business_date=date.today(), payment_method_id=method_id,
        due_date=data.get("due_date") if invoice_type == "FACTURA" else None,
        document_reference=data.get("document_reference"), observations=data.get("observations"), commit=False)


# --------------------------------------------------------------------------------------------------------- reading

async def document_view(db: AsyncSession, invoice: Invoice, with_lines: bool = True) -> dict:
    """The document as the program sees it - plain JSON (kept as it is with the idempotency record)."""
    from app.services.invoice_service import attach_amount_due

    code = CODES[invoice.invoice_type.value]
    customer = await db.get(Customer, invoice.customer_id) if invoice.customer_id else None
    from app.services.agt_queue import sent_to_agt
    fiscal = invoice.invoice_type.value in FISCAL and sent_to_agt(invoice)  # MANUAL mode: declared by the SAF-T
    await attach_amount_due(db, [invoice])
    view = {
        "id": str(invoice.id), "type": code, "number": f"{code} {invoice.series}/{invoice.number}",
        "date": invoice.business_date, "activity_id": str(invoice.activity_id),
        "customer": {"id": str(customer.id), "name": customer.name, "nif": customer.nif} if customer else None,
        "document_reference": invoice.document_reference, "observations": invoice.observations,
        "subtotal": _money(invoice.subtotal), "vat_total": _money(invoice.vat_total),
        "retention_total": _money(invoice.retention_total), "total": _money(invoice.total),
        "amount_due": _money(getattr(invoice, "amount_due", 0)) if invoice.invoice_type == InvoiceType.FACTURA else 0.0,
        "due_date": invoice.due_date,
        "status": invoice.document_status.value,
        "converted_to_invoice_id": str(invoice.converted_to_invoice_id) if invoice.converted_to_invoice_id else None,
        "agt": {"status": invoice.status.value, "label": AGT_STATES.get(invoice.status.value, invoice.status.value),
                "atcud": invoice.atcud} if fiscal else None,
        "pdf": f"/api/public/v1/documents/{invoice.id}/pdf",
        "created_at": invoice.created_at, "updated_at": invoice.updated_at,
    }
    if with_lines:
        lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
                                  .order_by(InvoiceLine.created_at, InvoiceLine.id))).scalars().all()
        view["lines"] = [{
            "product_id": str(l.product_id) if l.product_id else None,
            "service_id": str(l.service_id) if l.service_id else None,
            "name": l.product_name_snapshot, "quantity": float(l.quantity), "unit": l.unit_code_snapshot,
            "unit_price": _money(l.unit_price), "discount_percent": float(l.discount_percent or 0),
            "vat_rate": float(l.vat_rate_snapshot), "subtotal": _money(l.line_subtotal), "vat": _money(l.line_vat),
            "total": _money(l.line_total)} for l in lines]
    return jsonable_encoder(view)


async def get_document(db: AsyncSession, company_id: uuid.UUID, document_id: uuid.UUID) -> Invoice:
    invoice = (await db.execute(select(Invoice).where(Invoice.id == document_id, Invoice.company_id == company_id))
               ).scalar_one_or_none()
    if invoice is None:
        raise LookupError("Documento não encontrado")
    return invoice


async def list_documents(db: AsyncSession, company_id: uuid.UUID, doc_type: str | None = None,
                         date_from: date | None = None, date_to: date | None = None,
                         customer_id: uuid.UUID | None = None, document_reference: str | None = None,
                         updated_since: datetime | None = None, page: int = 1, page_size: int = 50) -> dict:
    page, page_size = _page(page, page_size)
    query = select(Invoice).where(Invoice.company_id == company_id)
    if doc_type:
        wanted = {v: k for k, v in CODES.items()}.get(doc_type.strip().upper())
        if wanted is None:
            raise PublicApiError(f"Tipo de documento «{doc_type}» desconhecido ({', '.join(CODES.values())})")
        query = query.where(Invoice.invoice_type == InvoiceType(wanted))
    if date_from:
        query = query.where(Invoice.business_date >= date_from)
    if date_to:
        query = query.where(Invoice.business_date <= date_to)
    if customer_id:
        query = query.where(Invoice.customer_id == customer_id)
    if document_reference:
        query = query.where(Invoice.document_reference == document_reference.strip())
    if updated_since:
        query = query.where(Invoice.updated_at >= updated_since)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Invoice.business_date.desc(), Invoice.created_at.desc(), Invoice.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [await document_view(db, i, with_lines=False) for i in rows],
            "page": page, "page_size": page_size, "total": total}

