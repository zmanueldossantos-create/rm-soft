"""A receipt is only issued for a Factura: a Fatura/Recibo is paid when issued, a receipt on top would collect twice."""
import pytest

from app.models.service import Service
from app.services.invoice_service import ReferenceInvoiceTypeNotEligibleError, create_invoice, create_receipt


@pytest.mark.asyncio
async def test_receipt_is_refused_on_a_fatura_recibo_and_accepted_on_a_factura(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service = Service(company_id=company_id, code="SRV-RF", name="Servico RF", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id

    fr = await create_invoice(
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=[{"service_id": service_id, "quantity": 1}],
    )
    fr_id = fr.id
    with pytest.raises(ReferenceInvoiceTypeNotEligibleError):
        await create_receipt(db, company_id, activity_id, reference_invoice_id=fr_id, amount=100.0)

    ft = await create_invoice(
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 1}],
    )
    ft_id = ft.id
    receipt = await create_receipt(db, company_id, activity_id, reference_invoice_id=ft_id, amount=100.0)
    assert float(receipt.amount_received) == 100.0