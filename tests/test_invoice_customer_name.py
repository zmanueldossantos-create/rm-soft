"""list_invoices exposes customer_name dynamically (same mechanism as item_count) - None for a walk-in."""
import pytest

from app.models.customer import Customer, LegalPersonType
from app.models.service import Service
from app.services.invoice_service import create_pro_forma, list_invoices


@pytest.mark.asyncio
async def test_customer_name_is_attached_and_none_for_a_walk_in(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    customer = Customer(company_id=company_id, name="Cliente Teste CN", nif="5000333111", legal_person_type=LegalPersonType.FISICA)
    service = Service(company_id=company_id, code="SRV-CN", name="Servico CN", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(customer)
    db.add(service)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]

    with_customer = await create_pro_forma(db, company_id, activity_id, customer.id, lines)
    walk_in = await create_pro_forma(db, company_id, activity_id, None, lines)

    invoices = await list_invoices(db, company_id, invoice_type="PRO_FORMA")
    found_with = next(i for i in invoices if i.id == with_customer.id)
    found_walk_in = next(i for i in invoices if i.id == walk_in.id)
    assert found_with.customer_name == "Cliente Teste CN"
    assert found_walk_in.customer_name is None