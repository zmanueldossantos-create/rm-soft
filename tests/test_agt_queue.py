"""
The AGT queue kept in the database (AGT_QUEUE=base, the Windows installation without Redis): a fiscal document is
queued when issued, sent by the server's loop, retried after 5 s, 10 s, 20 s, then ERRO; «Reenviar» queues it again.
With AGT_QUEUE=celery nothing changes: the Celery task is fired.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.models.invoice import InvoiceStatus
from app.services import agt_queue
from app.services.agt_service import AgtSendError
from app.services.invoice_service import create_invoice
from app.workers.agt_worker import submit_invoice_to_agt


async def _service(db, ctx):
    from app.models.service import Service
    service = Service(company_id=ctx["company"].id, code="SRV-Q", name="Serviço fila", price=1000,
                      vat_id=ctx["vat_nor"].id, unit_of_measure_id=ctx["unit_un"].id)
    db.add(service)
    await db.commit()
    return service.id


async def _invoice(db, ctx):
    lines = [{"service_id": await _service(db, ctx), "quantity": 1}]
    return await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                                lines_input=lines)


async def test_celery_mode_fires_the_task(db, company_with_essentials, monkeypatch):
    sent = []
    monkeypatch.setattr(submit_invoice_to_agt, "delay", lambda invoice_id: sent.append(invoice_id))
    monkeypatch.setattr(agt_queue, "sent_to_agt", lambda invoice: True)  # as issued in Faturação Eletrónica
    monkeypatch.setattr(get_settings(), "AGT_QUEUE", "celery")  # whatever this PC's .env says
    invoice = await _invoice(db, company_with_essentials)
    assert sent == [str(invoice.id)] and invoice.agt_next_attempt_at is None


async def test_a_manual_document_is_never_sent(db, company_with_essentials, monkeypatch):
    """MANUAL mode: the document is declared by the SAF-T file - not queued, «Reenviar» refused."""
    import httpx
    from app.core.database import get_db
    from app.core.security import create_access_token
    from app.main import app
    from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
    ctx = company_with_essentials
    lines = [{"service_id": await _service(db, ctx), "quantity": 1}]
    for mode in ("celery", "base"):
        monkeypatch.setattr(get_settings(), "AGT_QUEUE", mode)
        monkeypatch.setattr(submit_invoice_to_agt, "delay", lambda invoice_id: pytest.fail("a MANUAL document is not sent"))
        invoice = await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None,
                                       invoice_type="FACTURA", lines_input=lines)
        assert invoice.issuance_mode == "MANUAL" and invoice.agt_next_attempt_at is None
    assert await agt_queue.send_due(db, sender=lambda _: pytest.fail("not sent"), now=datetime.now(timezone.utc)) == 0

    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, ctx["company"].id)
    await db.commit()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        token = create_access_token(subject=str(ctx["gestor"].id), company_id=str(ctx["company"].id), role="GESTOR")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            refused = await client.post(f"/api/v1/invoices/{invoice.id}/resubmit",
                                        headers={"Authorization": "Bearer " + token})
        assert refused.status_code == 422 and "modo manual" in refused.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_database_mode_sends_retries_then_erro(db, company_with_essentials, monkeypatch, mark_electronic):
    monkeypatch.setattr(get_settings(), "AGT_QUEUE", "base")
    monkeypatch.setattr(submit_invoice_to_agt, "delay", lambda invoice_id: pytest.fail("Celery must not be used"))
    invoice = await _invoice(db, company_with_essentials)
    invoice_id = invoice.id
    await mark_electronic()  # issued in Faturação Eletrónica: queued
    await db.refresh(invoice)
    await agt_queue.queue_for_agt(db, invoice)
    assert invoice.agt_next_attempt_at is not None and invoice.status == InvoiceStatus.PENDENTE

    async def ok(_):
        return None

    async def down(_):
        raise AgtSendError("sem rede")

    assert await agt_queue.send_due(db, sender=down) == 1
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.POR_ENVIAR and invoice.agt_attempts == 1
    first_retry = invoice.agt_next_attempt_at
    assert await agt_queue.send_due(db, sender=down) == 0  # not due yet (5 s later)
    for expected_attempts in (2, 3, 4):
        assert await agt_queue.send_due(db, sender=down, now=datetime.now(timezone.utc) + timedelta(minutes=5)) == 1
        await db.refresh(invoice)
        assert invoice.agt_attempts == expected_attempts
    assert invoice.status == InvoiceStatus.ERRO and invoice.agt_next_attempt_at is None
    assert first_retry is not None

    # «Reenviar»: queued again, then sent
    await agt_queue.queue_for_agt(db, invoice)
    assert await agt_queue.send_due(db, sender=ok) == 1
    await db.refresh(invoice)
    assert invoice.id == invoice_id and invoice.status == InvoiceStatus.ENVIADA and invoice.agt_next_attempt_at is None
    assert await agt_queue.send_due(db, sender=ok) == 0
