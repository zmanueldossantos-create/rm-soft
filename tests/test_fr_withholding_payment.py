"""
A Fatura/Recibo with withholding is paid net of the withholding (the customer keeps it): the payments must add up to
the total minus the withholding - by default, or when given explicitly - and the gross total is refused.
"""
import pytest
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.payment import Payment
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.services.invoice_service import PaymentAmountMismatchError, create_invoice


async def _payments(db, invoice_id):
    rows = (await db.execute(select(Payment).where(Payment.invoice_id == invoice_id))).scalars().all()
    return [(float(p.amount), p.payment_method_id) for p in rows]


@pytest.mark.asyncio
async def test_fr_with_withholding_is_paid_net_of_the_withholding(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, numerario_id = ctx["company"].id, ctx["activity"].id, ctx["pm_numerario"].id
    tax = WithholdingTax(name="Retencao FR", rate=6.5, tax_type="II")
    db.add(tax)
    customer = Customer(company_id=company_id, name="Empresa PJ", nif="5000111888", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    await db.refresh(tax)
    await db.refresh(customer)
    customer_id = customer.id
    service = Service(company_id=company_id, code="SRV-FRR", name="Servico FR retencao", price=1000.0,
                      vat_id=ctx["vat_nor"].id, withholding_tax_id=tax.id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id
    lines = [{"service_id": service_id, "quantity": 2}]  # 2280, withholding 130, the customer pays 2150

    default = await create_invoice(db, company_id, activity_id, customer_id=customer_id, invoice_type="FACTURA_RECIBO", lines_input=lines)
    default_id = default.id
    assert await _payments(db, default_id) == [(2150.0, numerario_id)]

    explicit = await create_invoice(
        db, company_id, activity_id, customer_id=customer_id, invoice_type="FACTURA_RECIBO", lines_input=lines,
        payments=[{"payment_method_id": numerario_id, "amount": 2150.0}],
    )
    explicit_id = explicit.id
    assert await _payments(db, explicit_id) == [(2150.0, numerario_id)]

    with pytest.raises(PaymentAmountMismatchError):
        await create_invoice(
            db, company_id, activity_id, customer_id=customer_id, invoice_type="FACTURA_RECIBO", lines_input=lines,
            payments=[{"payment_method_id": numerario_id, "amount": 2280.0}],
        )