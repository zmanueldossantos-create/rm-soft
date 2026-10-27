"""
The AGT queue: every fiscal document is sent to the AGT right after it is issued (section 4.2), retried on failure.

Two ways, chosen by AGT_QUEUE (app.core.config):
  celery - Celery + Redis (Docker, SaaS): queue_for_agt fires the task (app/workers/agt_worker.py).
  base   - the database IS the queue (Windows installation, no Redis): queue_for_agt marks the document due
           (agt_next_attempt_at); agt_queue_loop, started with the server, sends what is due, one document after
           another, retrying after 5 s, 10 s, 20 s - then ERRO (the «Reenviar» button queues it again). Nothing is lost
           when the PC stops: a document still due is sent when the server starts again.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.invoice import Invoice, InvoiceStatus

log = logging.getLogger(__name__)
MAX_RETRIES = 3            # as the Celery task: 3 retries after the first attempt
RETRY_BASE_SECONDS = 5     # 5 s, 10 s, 20 s
POLL_SECONDS = 5
_wake = asyncio.Event()    # a new document: the loop looks at once instead of waiting its 5 seconds


def _database_queue() -> bool:
    return get_settings().AGT_QUEUE == "base"


def sent_to_agt(invoice: Invoice) -> bool:
    """Only a document issued in Faturação Eletrónica is sent to the AGT, in real time. A document issued in MANUAL
    mode is declared through the SAF-T file: never sent, its AGT state does not apply."""
    mode = invoice.issuance_mode
    return (mode.value if hasattr(mode, "value") else mode) == "ELETRONICA"


async def queue_for_agt(db: AsyncSession, invoice: Invoice) -> None:
    """Called once the document is committed: it will be sent to the AGT (now, by Celery or by the loop) - when it
    was issued in Faturação Eletrónica (sent_to_agt)."""
    if not sent_to_agt(invoice):
        return
    if not _database_queue():
        from app.workers.agt_worker import submit_invoice_to_agt
        submit_invoice_to_agt.delay(str(invoice.id))
        return
    invoice.agt_next_attempt_at = datetime.now(timezone.utc)
    invoice.agt_attempts = 0
    await db.commit()
    await db.refresh(invoice)  # the caller returns it: loaded again, never read lazily after the commit
    _wake.set()


async def send_due(db: AsyncSession, sender=None, now: datetime | None = None) -> int:
    """Sends every document due now, one after another; returns how many were tried. sender: the AGT call
    (app.services.agt_service.send_document - replaced in the tests)."""
    from app.services.agt_service import AgtSendError, send_document
    sender = sender or send_document
    now = now or datetime.now(timezone.utc)
    ids = (await db.execute(select(Invoice.id).where(Invoice.agt_next_attempt_at.is_not(None),
                                                     Invoice.agt_next_attempt_at <= now,
                                                     Invoice.issuance_mode == "ELETRONICA")
                            .order_by(Invoice.agt_next_attempt_at).limit(50))).scalars().all()
    for invoice_id in ids:
        invoice = await db.get(Invoice, invoice_id)
        invoice.status = InvoiceStatus.POR_ENVIAR
        await db.commit()
        try:
            await sender(str(invoice_id))
        except AgtSendError as e:
            invoice.agt_attempts += 1
            if invoice.agt_attempts > MAX_RETRIES:
                invoice.status, invoice.agt_next_attempt_at = InvoiceStatus.ERRO, None
                log.warning("AGT: %s em ERRO após %s tentativas (%s)", invoice_id, invoice.agt_attempts, e)
            else:
                delay = RETRY_BASE_SECONDS * 2 ** (invoice.agt_attempts - 1)
                invoice.agt_next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        else:
            invoice.status, invoice.agt_next_attempt_at = InvoiceStatus.ENVIADA, None
        await db.commit()
    return len(ids)


async def agt_queue_loop() -> None:
    """Started with the server when AGT_QUEUE=base: every 5 seconds (or at once after a new document), what is due."""
    from app.core.database import AsyncSessionLocal
    while True:
        _wake.clear()
        try:
            async with AsyncSessionLocal() as db:
                await send_due(db)
        except Exception:  # noqa: BLE001 - the loop never stops on one failure
            log.exception("AGT queue loop failed")
        try:
            await asyncio.wait_for(_wake.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass

