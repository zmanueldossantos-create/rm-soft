"""A pro-forma carries the withholding like the invoice it becomes: a service with a withholding sold to a pessoa coletiva."""
import pytest
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.services.invoice_service import convert_pro_forma_to_invoice, create_pro_forma


@pytest.mark.asyncio
async def test_pro_forma_has_the_withholding_of_the_invoice_it_becomes(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    tax = WithholdingTax(name="Retencao PF", rate=6.5, tax_type="II")
    db.add(tax)
    company_customer = Customer(company_id=company_id, name="Empresa PJ", nif="5000222111", legal_person_type=LegalPersonType.JURIDICA)
    db.add(company_customer)
    await db.commit()
    await db.refresh(tax)
    await db.refresh(company_customer)
    customer_id = company_customer.id
    service = Service(company_id=company_id, code="SRV-PFR", name="Servico PFR", price=10000.0,
                      vat_id=ctx["vat_nor"].id, withholding_tax_id=tax.id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]  # 11400, withholding 650

    with_retention = await create_pro_forma(db, company_id, activity_id, customer_id, lines)
    with_id = with_retention.id
    assert float(with_retention.total) == 11400.0 and float(with_retention.retention_total) == 650.0
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == with_id))).scalars().one()
    assert (float(line.retention_amount), line.retention_type) == (650.0, "II")

    unknown = await create_pro_forma(db, company_id, activity_id, None, lines)  # a walk-in: no withholding, like an invoice
    assert float(unknown.retention_total) == 0.0

    invoice = await convert_pro_forma_to_invoice(
        db, company_id, with_id, "FACTURA_RECIBO", payments=[{"payment_method_id": ctx["pm_numerario"].id, "amount": 10750.0}],
    )
    assert float(invoice.retention_total) == float(with_retention.retention_total)  # same withholding on both documents