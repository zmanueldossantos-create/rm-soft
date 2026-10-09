"""Every document records who created it: the authenticated user of the request (current_user_id), whatever path
creates it; outside a request it stays empty."""
import pytest

from app.core.request_context import current_user_id
from app.models.service import Service
from app.services.invoice_service import create_invoice


async def _issue(db, ctx, code):
    service = Service(company_id=ctx["company"].id, code=code, name="Servico autor", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    return await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                                lines_input=[{"service_id": service.id, "quantity": 1}])


@pytest.mark.asyncio
async def test_a_document_records_the_user_of_the_request(db, company_with_essentials):
    ctx = company_with_essentials
    token = current_user_id.set(ctx["gestor"].id)
    try:
        invoice = await _issue(db, ctx, "SRV-AUT1")
    finally:
        current_user_id.reset(token)
    assert invoice.created_by_user_id == ctx["gestor"].id


@pytest.mark.asyncio
async def test_outside_a_request_no_user_is_recorded(db, company_with_essentials):
    invoice = await _issue(db, company_with_essentials, "SRV-AUT2")
    assert invoice.created_by_user_id is None
