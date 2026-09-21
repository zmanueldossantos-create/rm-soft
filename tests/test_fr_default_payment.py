"""
A Fatura/Recibo issued without explicit payments records its payment with the method chosen on the document
(Numerario when none was chosen) - it used to be Numerario whatever the method chosen.
"""
import pytest
from sqlalchemy import select, text

from app.models.payment import Payment
from app.models.service import Service
from app.services.invoice_service import create_invoice


async def _payments(db, invoice_id):
    rows = (await db.execute(select(Payment).where(Payment.invoice_id == invoice_id))).scalars().all()
    return [(float(p.amount), p.payment_method_id) for p in rows]


@pytest.mark.asyncio
async def test_fr_payment_uses_the_method_chosen_on_the_document(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, numerario_id = ctx["company"].id, ctx["activity"].id, ctx["pm_numerario"].id
    multicaixa_id = (await db.execute(text("SELECT id FROM payment_method_catalog WHERE code = 'MB'"))).scalar_one()
    service = Service(company_id=company_id, code="SRV-FR", name="Servico FR", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id

    chosen = await create_invoice(
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO", payment_method_id=multicaixa_id,
        lines_input=[{"service_id": service_id, "quantity": 1}],
    )
    chosen_id = chosen.id
    assert await _payments(db, chosen_id) == [(1140.0, multicaixa_id)]

    none_chosen = await create_invoice(
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=[{"service_id": service_id, "quantity": 1}],
    )
    none_chosen_id = none_chosen.id
    assert await _payments(db, none_chosen_id) == [(1140.0, numerario_id)]