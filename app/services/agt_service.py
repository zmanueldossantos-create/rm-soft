"""
A document's way to the AGT (Faturação Eletrónica), one step at a time - called by the queue (app.services.agt_queue,
the server's loop or the Celery task) whenever the document is due (Invoice.agt_next_attempt_at):

  PENDENTE  → registarFactura → ENVIADA (the AGT's requestID kept) → obterEstado → VALIDADA (V) / VALIDADA_P (P) / ERRO (I)

What decides what happens next:
- the AGT not reached, or not answering (no internet, time out, 5xx, 429): tried again later, waiting longer each time
  (up to 5 minutes) - NEVER ERRO, nothing is wrong with the document;
- the sending blocked by the set-up (no access, software not certified, a signature refused, the NIF not adhered -
  CONFIG_ERRORS, or a missing setting): the document waits (PENDENTE, agt_last_error says why), tried again every 10
  minutes - the same for every document, it is not this one's fault;
- the AGT refusing THIS document (its data: E01-E46 on the document, or «I» at the validation): ERRO, with the AGT's
  reasons (agt_errors). Such a document is never sent again under the same number (E46): it is corrected by a new one;
- «already registered» (E09) with the first requestID: taken as sent, its validation is read.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.invoice import Invoice, InvoiceStatus
from app.services import agt_client
from app.services.agt_document_service import build_document, document_no, type_code

log = logging.getLogger(__name__)

NETWORK_RETRY = (5, 10, 20, 40, 80, 160, 300)  # seconds, then every 5 minutes
CHECK_DELAYS = (5, 10, 20, 40, 60, 120, 300)   # obterEstado: the AGT validates in batches
BLOCKED_RETRY = 600
CONFIG_ERRORS = {"E05", "E06", "E07", "E08", "E28", "E30", "E39", "E40", "E94", "E95", "E98"}
LATE = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _later(invoice: Invoice, delays: tuple[int, ...]) -> None:
    invoice.agt_attempts = (invoice.agt_attempts or 0) + 1
    invoice.agt_next_attempt_at = _now() + timedelta(seconds=delays[min(invoice.agt_attempts - 1, len(delays) - 1)])


def _blocked(invoice: Invoice, message: str) -> None:
    """The set-up stops every sending: the document waits, the reason shown."""
    if invoice.status == InvoiceStatus.POR_ENVIAR:
        invoice.status = InvoiceStatus.PENDENTE
    invoice.agt_last_error = message[:300]
    invoice.agt_attempts = (invoice.agt_attempts or 0) + 1
    invoice.agt_next_attempt_at = _now() + timedelta(seconds=BLOCKED_RETRY)


def _unreachable(invoice: Invoice, message: str, delays=NETWORK_RETRY) -> None:
    if invoice.status == InvoiceStatus.POR_ENVIAR:
        invoice.status = InvoiceStatus.PENDENTE
    invoice.agt_last_error = message[:300]
    _later(invoice, delays)


def _codes(errors: list[dict]) -> set[str]:
    return {str(e.get("idError") or e.get("errorCode") or "").strip() for e in errors} - {""}


def _refused(invoice: Invoice, errors: list[dict], status_code: int | None) -> None:
    """The AGT said no: the set-up (every document) or this document's data (ERRO)."""
    message = agt_client.describe(errors) or f"Recusado pela AGT ({status_code})"
    codes = _codes(errors)
    if status_code in (401, 403) or (codes and codes <= CONFIG_ERRORS) or not codes:
        _blocked(invoice, message)
        return
    invoice.status, invoice.agt_errors = InvoiceStatus.ERRO, errors
    invoice.agt_last_error, invoice.agt_next_attempt_at = message[:300], None


def _accepted(invoice: Invoice, request_id: str) -> None:
    invoice.status, invoice.agt_request_id = InvoiceStatus.ENVIADA, str(request_id)[:20]
    invoice.agt_sent_at, invoice.agt_last_error, invoice.agt_errors = _now(), None, None
    invoice.agt_attempts = 0
    invoice.agt_next_attempt_at = _now() + timedelta(seconds=CHECK_DELAYS[0])


async def _send(db: AsyncSession, invoice: Invoice, ctx: agt_client.AgtContext) -> None:
    invoice.status = InvoiceStatus.POR_ENVIAR
    await db.commit()
    try:
        document = await build_document(db, invoice, ctx.nif, ctx.private_key)
    except Exception as e:  # noqa: BLE001 - a document that cannot be prepared waits, the others go on
        log.exception("AGT: document %s could not be prepared", invoice.id)
        _blocked(invoice, f"Documento por preparar: {type(e).__name__}")
        return
    try:
        answer = await agt_client.registar_factura(ctx, [document])
    except agt_client.AgtUnavailable as e:
        _unreachable(invoice, str(e))
        return
    except agt_client.AgtRefused as e:
        request_id = e.body.get("requestID") if isinstance(e.body, dict) else None
        if request_id and "E09" in _codes(e.errors):
            _accepted(invoice, request_id)
        else:
            _refused(invoice, e.errors, e.status_code)
        return
    errors = agt_client.error_list(answer)
    request_id = answer.get("requestID") if isinstance(answer, dict) else None
    if errors and not (request_id and "E09" in _codes(errors)):
        _refused(invoice, errors, 200)
    elif request_id:
        _accepted(invoice, request_id)
    else:
        _blocked(invoice, "A AGT não devolveu o número do pedido (requestID)")


async def _check(db: AsyncSession, invoice: Invoice, ctx: agt_client.AgtContext) -> None:
    try:
        answer = await agt_client.obter_estado(ctx, invoice.agt_request_id)
    except agt_client.AgtUnavailable as e:
        _unreachable(invoice, str(e), CHECK_DELAYS)
        return
    except agt_client.AgtRefused as e:
        if _codes(e.errors) & {"E96", "E97"}:  # still being processed / asked too early
            _later(invoice, CHECK_DELAYS)
        else:
            _blocked(invoice, str(e))
        return
    result = str((answer or {}).get("resultCode", "")).strip() if isinstance(answer, dict) else ""
    if result in ("7", "8", ""):
        _later(invoice, CHECK_DELAYS)
        return
    if result == "9":  # the AGT cancelled the processing: sent again
        invoice.status, invoice.agt_request_id = InvoiceStatus.PENDENTE, None
        invoice.agt_attempts, invoice.agt_next_attempt_at = 0, _now()
        return
    number = document_no(await type_code(db, invoice), invoice)
    mine = next((d for d in answer.get("documentStatusList") or []
                 if isinstance(d, dict) and str(d.get("documentNo", "")).strip() == number), None)
    if mine is None:
        _later(invoice, CHECK_DELAYS)
        return
    state = str(mine.get("documentStatus", "")).strip().upper()
    if state == "I":
        errors = agt_client.error_list(mine) or [{"idError": "", "descriptionError": "Documento inválido"}]
        invoice.status, invoice.agt_errors = InvoiceStatus.ERRO, errors
        invoice.agt_last_error, invoice.agt_next_attempt_at = agt_client.describe(errors)[:300], None
        return
    if state in ("V", "P"):
        invoice.status = InvoiceStatus.VALIDADA_P if state == "P" else InvoiceStatus.VALIDADA
        if state == "V" and invoice.agt_sent_at and invoice.created_at and invoice.agt_sent_at - invoice.created_at > LATE:
            # sent more than 24 h after it was issued: the AGT may have validated it with a penalty
            try:
                detail = await agt_client.consultar_factura(ctx, number)
                if isinstance(detail, dict) and str(detail.get("validationStatus", "")).upper() == "P":
                    invoice.status = InvoiceStatus.VALIDADA_P
            except agt_client.AgtError:
                pass
        invoice.agt_validated_at, invoice.agt_last_error, invoice.agt_next_attempt_at = _now(), None, None
        return
    _later(invoice, CHECK_DELAYS)


async def process(db: AsyncSession, invoice: Invoice) -> None:
    """One step of this document's way to the AGT (the caller commits)."""
    if invoice.status in (InvoiceStatus.VALIDADA, InvoiceStatus.VALIDADA_P, InvoiceStatus.ERRO):
        invoice.agt_next_attempt_at = None
        return
    company = await db.get(Company, invoice.company_id)
    try:
        ctx = await agt_client.context_for(db, company)
    except agt_client.AgtConfigError as e:
        _blocked(invoice, str(e))
        return
    if invoice.status == InvoiceStatus.ENVIADA and invoice.agt_request_id:
        await _check(db, invoice, ctx)
    else:
        await _send(db, invoice, ctx)
