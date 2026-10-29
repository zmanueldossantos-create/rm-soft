"""
The AGT queue: every document issued in Faturação Eletrónica is sent to the AGT right after it is issued, then its
validation is read (app.services.agt_service - one step at a time, the document's agt_next_attempt_at saying when the
next one is due). The database IS the queue: nothing is lost when the server stops, a document still due goes when it
starts again.

Two ways to run the steps, chosen by AGT_QUEUE (app.core.config):
  celery - Celery + Redis (Docker, SaaS): queue_for_agt fires the task (app/workers/agt_worker.py), which runs a step
           and schedules itself again when another one is due;
  base   - the server's own loop (Windows installation, no Redis): agt_queue_loop runs what is due every 5 seconds (at
           once after a new document).
A network failure never makes a document ERRO: only the AGT refusing it does («I», or its data refused).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.invoice import Invoice, InvoiceStatus

log = logging.getLogger(__name__)
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
    invoice.agt_next_attempt_at = datetime.now(timezone.utc)
    invoice.agt_attempts = 0
    await db.commit()
    await db.refresh(invoice)  # the caller returns it: loaded again, never read lazily after the commit
    if not _database_queue():
        from app.workers.agt_worker import submit_invoice_to_agt
        submit_invoice_to_agt.delay(str(invoice.id))
        return
    _wake.set()


async def send_due(db: AsyncSession, step=None, now: datetime | None = None) -> int:
    """Runs the step of every document due now, oldest first (the numbering's order); returns how many. step: the AGT
    step (app.services.agt_service.process - replaced in the tests)."""
    from app.services.agt_service import process
    step = step or process
    now = now or datetime.now(timezone.utc)
    ids = (await db.execute(select(Invoice.id).where(
        Invoice.agt_next_attempt_at.is_not(None), Invoice.agt_next_attempt_at <= now,
        Invoice.issuance_mode == "ELETRONICA",
        Invoice.status.in_((InvoiceStatus.PENDENTE, InvoiceStatus.POR_ENVIAR, InvoiceStatus.ENVIADA)))
        .order_by(Invoice.created_at, Invoice.number).limit(50))).scalars().all()
    for invoice_id in ids:
        invoice = await db.get(Invoice, invoice_id)
        try:
            await step(db, invoice)
        except Exception:  # noqa: BLE001 - one document never stops the others
            log.exception("AGT: step failed for %s", invoice_id)
            await db.rollback()
            invoice = await db.get(Invoice, invoice_id)
            if invoice.status == InvoiceStatus.POR_ENVIAR:
                invoice.status = InvoiceStatus.PENDENTE
            invoice.agt_next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=10)
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

