"""
AGT submission worker.
See specification v6/v7, section 4.2: each invoice is submitted to a "Mock
AGT" server within 30 seconds via an asynchronous Celery task, triggered
immediately after invoice creation. Status flow: PENDENTE -> POR_ENVIAR -> ENVIADA/ERRO.

No real AGT endpoint exists yet (homologation pending, Decision 2, section
4.4) - this simulates the round trip locally with a realistic delay, and a
small simulated failure rate so retry/error handling can be tested for
real, not just assumed to work.

Retry policy: automatic retry up to 3 times with exponential backoff
(5s, 10s, 20s). After all retries are exhausted, the invoice is marked
ERRO and can be manually re-sent from the app (see resubmit_invoice_to_agt
route in invoices/routes.py - the "Reenviar" button).
"""
import asyncio
import random
import time
import uuid

from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal, engine
from app.models.invoice import Invoice, InvoiceStatus

# Simulated network failure rate - lets us exercise the retry/ERRO path
# without a real AGT endpoint. Remove once a real integration exists.
SIMULATED_FAILURE_RATE = 0.2


class SimulatedAgtError(Exception):
    """Raised to simulate a transient AGT network/server failure."""
    pass


async def _mark_status(invoice_id: str, status: InvoiceStatus) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
        invoice = result.scalar_one_or_none()
        if invoice is None:
            return
        invoice.status = status
        await db.commit()


async def _submit_invoice_async(invoice_id: str) -> None:
    try:
        await _mark_status(invoice_id, InvoiceStatus.POR_ENVIAR)

        # Simulated network round trip to the Mock AGT server
        await asyncio.sleep(3)

        if random.random() < SIMULATED_FAILURE_RATE:
            raise SimulatedAgtError("Falha simulada na comunicacao com o servidor da AGT")

        await _mark_status(invoice_id, InvoiceStatus.ENVIADA)
    finally:
        # Celery (--pool=solo) calls asyncio.run() once per task, creating
        # and destroying a fresh event loop each time. The shared engine's
        # connection pool (designed for FastAPI's single persistent loop)
        # otherwise leaves a connection bound to this now-dying loop, which
        # crashes the NEXT task with "Event loop is closed". Disposing here,
        # inside the still-live loop, prevents that stale handoff.
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="agt.submit_invoice",
    autoretry_for=(SimulatedAgtError,),
    retry_backoff=5,      # 5s, 10s, 20s
    retry_backoff_max=60,
    max_retries=3,
)
def submit_invoice_to_agt(self, invoice_id: str) -> str:
    """
    Celery entry point (sync) - Celery does not natively run async functions,
    so this bridges into the async DB session via asyncio.run(). Retries
    automatically on simulated failure; marks ERRO once retries are exhausted.
    """
    try:
        asyncio.run(_submit_invoice_async(invoice_id))
        return f"Invoice {invoice_id} submitted"
    except SimulatedAgtError as e:
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            asyncio.run(_mark_status(invoice_id, InvoiceStatus.ERRO))
            return f"Invoice {invoice_id} failed after retries - marked ERRO"
