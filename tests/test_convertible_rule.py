"""Converting a pro-forma follows the catalog: the source must be convertible, the target a plain invoice."""
import pytest
from sqlalchemy import text

from app.models.invoice import InvoiceType
from app.models.service import Service
from app.services.invoice_service import (
    ProFormaNotFoundError, ReferenceInvoiceTypeNotEligibleError, convert_pro_forma_to_invoice, create_invoice, create_pro_forma,
)


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


@pytest.mark.asyncio
async def test_conversion_follows_the_convertible_rule(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service = Service(company_id=company_id, code="SRV-CV", name="Servico CV", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]

    ft = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
    ft_id = ft.id
    pro_forma = await create_pro_forma(db, company_id, activity_id, None, lines)
    pro_forma_id = pro_forma.id

    with pytest.raises(ProFormaNotFoundError):  # an invoice is not convertible
        await convert_pro_forma_to_invoice(db, company_id, ft_id, "FACTURA")
    for target in ("NOTA_CREDITO", "PRO_FORMA", "XYZ"):  # the target must be a plain invoice
        with pytest.raises(ReferenceInvoiceTypeNotEligibleError):
            await convert_pro_forma_to_invoice(db, company_id, pro_forma_id, target)

    converted = await convert_pro_forma_to_invoice(db, company_id, pro_forma_id, "FACTURA")
    assert converted.invoice_type == InvoiceType.FACTURA

    second = await create_pro_forma(db, company_id, activity_id, None, lines)
    second_id = second.id
    try:
        await _set_rule(db, "FP", convertible=False)
        with pytest.raises(ProFormaNotFoundError):  # the catalog says it can no longer be converted
            await convert_pro_forma_to_invoice(db, company_id, second_id, "FACTURA")
    finally:
        await _set_rule(db, "FP", convertible=True)