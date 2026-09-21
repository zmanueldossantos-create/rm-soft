"""The drawer journal shows the cash received for a document of the Payments section, not its total."""
from datetime import date

import pytest
from sqlalchemy import text

from app.models.customer import Customer, LegalPersonType
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.services.cash_session_service import open_session
from app.services.daily_report_service import get_daily_report
from app.services.invoice_service import create_invoice, create_receipt


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


@pytest.mark.asyncio
async def test_journal_amount_follows_the_saft_section_rule(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    tax = WithholdingTax(name="Retencao rapport", rate=6.5, tax_type="II")
    db.add(tax)
    customer = Customer(company_id=company_id, name="Empresa PJ", nif="5000111999", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    await db.refresh(tax)
    await db.refresh(customer)
    customer_id = customer.id
    service = Service(company_id=company_id, code="SRV-RR", name="Servico RR", price=1000.0,
                      vat_id=ctx["vat_nor"].id, withholding_tax_id=tax.id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    session_id = session.id
    invoice = await create_invoice(  # 2280, withholding 130 -> cash due 2150
        db, company_id, activity_id, customer_id=customer_id, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}], cash_session_id=session_id,
    )
    invoice_id = invoice.id
    await create_receipt(db, company_id, activity_id, reference_invoice_id=invoice_id, amount=2150.0, cash_session_id=session_id)

    async def amounts():
        entries = await get_daily_report(db, company_id, pos_id, date.today(), date.today())
        return {e["description"].split(" ")[0]: e["amount"] for e in entries if e["type"] == "venda"}

    assert await amounts() == {"FT": 2280.0, "RC": 2150.0}
    try:
        await _set_rule(db, "RC", saft_section="INVOICES")  # no longer a payment document: its total is shown
        assert await amounts() == {"FT": 2280.0, "RC": 2280.0}
    finally:
        await _set_rule(db, "RC", saft_section="PAYMENTS")