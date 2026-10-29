"""
The AGT queue run by Celery (AGT_QUEUE=celery - Docker, SaaS): one step of a document's way to the AGT
(app.services.agt_service.process: send, then read its validation), then the task schedules itself again when the
document's next step is due (Invoice.agt_next_attempt_at). The database keeps the queue: a step lost with a stopped
worker is found again by queue_for_agt («Reenviar») or by the next document's task (it runs every step due).
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal, engine
from app.models.invoice import Invoice


async def _step(invoice_id: str) -> float | None:
    """Runs what is due (this document first); returns in how many seconds this document's next step is due."""
    from app.services.agt_queue import send_due
    from app.services.agt_service import process
    try:
        async with AsyncSessionLocal() as db:
            invoice = await db.get(Invoice, uuid.UUID(invoice_id))
            if invoice is None:
                return None
            await process(db, invoice)
            await db.commit()
            await send_due(db)  # the others due meanwhile
            await db.refresh(invoice)
            if invoice.agt_next_attempt_at is None:
                return None
            return max((invoice.agt_next_attempt_at - datetime.now(timezone.utc)).total_seconds(), 1)
    finally:
        # Celery (--pool=solo) runs asyncio.run() once per task: the shared engine's pool must not keep a connection
        # bound to this loop, about to close ("Event loop is closed" in the next task).
        await engine.dispose()


@celery_app.task(name="agt.submit_invoice")
def submit_invoice_to_agt(invoice_id: str) -> str:
    delay = asyncio.run(_step(invoice_id))
    if delay is not None:
        submit_invoice_to_agt.apply_async(args=[invoice_id], countdown=delay)
        return f"Invoice {invoice_id}: next step in {int(delay)} s"
    return f"Invoice {invoice_id}: done"
