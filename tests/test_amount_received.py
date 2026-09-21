"""An amount received on a Fatura creates its payment; a Fatura/Recibo is paid in full; an excess is refused."""
import pytest
from sqlalchemy import select, text

from app.models.payment import Payment
from app.models.service import Service
from app.services.invoice_service import PaymentAmountMismatchError, create_invoice


async def _payments(db, invoice_id):
    rows = (await db.execute(select(Payment).where(Payment.invoice_id == invoice_id))).scalars().all()
    return [(float(p.amount), p.payment_method_id) for p in rows]


@pytest.mark.asyncio
async def test_amount_received_follows_the_document_type(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, numerario_id = ctx["company"].id, ctx["activity"].id, ctx["pm_numerario"].id
    multicaixa_id = (await db.execute(text("SELECT id FROM payment_method_catalog WHERE code = 'MB'"))).scalar_one()
    service = Service(company_id=company_id, code="SRV-AR", name="Servico AR", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]  # 1140

    async def issue(invoice_type, **extra):
        invoice = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type=invoice_type,
                                       lines_input=lines, **extra)
        return invoice.id

    deposit_id = await issue("FACTURA", amount_received=500.0)
    assert await _payments(db, deposit_id) == [(500.0, numerario_id)]
    card_id = await issue("FACTURA", amount_received=140.0, payment_method_id=multicaixa_id)
    assert await _payments(db, card_id) == [(140.0, multicaixa_id)]
    assert await _payments(db, await issue("FACTURA")) == []  # no amount received: no payment
    assert await _payments(db, await issue("FACTURA_RECIBO", amount_received=1140.0)) == [(1140.0, numerario_id)]

    with pytest.raises(PaymentAmountMismatchError):
        await issue("FACTURA", amount_received=2000.0)  # more than what is due
    with pytest.raises(PaymentAmountMismatchError):
        await issue("FACTURA_RECIBO", amount_received=500.0)  # a Fatura/Recibo is paid in full