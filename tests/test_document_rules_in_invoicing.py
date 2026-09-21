"""
Invoicing follows the rules of the document type catalog, not the name of the type: paid on issue, sent to the AGT,
deducts stock. Each test changes one rule, checks the code follows it, and puts it back.
"""
import pytest
from sqlalchemy import select, text

from app.models.payment import Payment
from app.models.product import Product, ProductType
from app.models.service import Service
from app.models.stock import Stock
from app.services import invoice_service
from app.services.invoice_service import create_invoice, create_receipt


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


async def _service(db, ctx, code):
    service = Service(company_id=ctx["company"].id, code=code, name="Servico " + code, price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service.id


async def _payments(db, invoice_id):
    rows = (await db.execute(select(Payment).where(Payment.invoice_id == invoice_id))).scalars().all()
    return [float(p.amount) for p in rows]


@pytest.mark.asyncio
async def test_sending_to_the_agt_follows_the_sent_to_agt_rule(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    lines = [{"service_id": await _service(db, ctx, "SRV-AG"), "quantity": 1}]
    sent = []
    monkeypatch.setattr(invoice_service.submit_invoice_to_agt, "delay", lambda invoice_id: sent.append(invoice_id))

    ft = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
    ft_id = ft.id
    await create_receipt(db, company_id, activity_id, reference_invoice_id=ft_id, amount=100.0)
    assert len(sent) == 2  # the invoice and its receipt

    try:
        await _set_rule(db, "FT", sent_to_agt=False)
        await _set_rule(db, "RC", sent_to_agt=False)
        await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
        await create_receipt(db, company_id, activity_id, reference_invoice_id=ft_id, amount=100.0)
        assert len(sent) == 2  # neither is sent any more
    finally:
        await _set_rule(db, "FT", sent_to_agt=True)
        await _set_rule(db, "RC", sent_to_agt=True)


@pytest.mark.asyncio
async def test_payment_on_issue_follows_the_paid_on_issue_rule(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    lines = [{"service_id": await _service(db, ctx, "SRV-PI"), "quantity": 1}]  # 1140

    fr = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO", lines_input=lines)
    fr_id = fr.id
    assert await _payments(db, fr_id) == [1140.0]

    try:
        await _set_rule(db, "FR", paid_on_issue=False)
        await _set_rule(db, "FT", paid_on_issue=True)
        unpaid_fr = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO", lines_input=lines)
        unpaid_fr_id = unpaid_fr.id
        paid_ft = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
        paid_ft_id = paid_ft.id
        assert await _payments(db, unpaid_fr_id) == []
        assert await _payments(db, paid_ft_id) == [1140.0]
    finally:
        await _set_rule(db, "FR", paid_on_issue=True)
        await _set_rule(db, "FT", paid_on_issue=False)


@pytest.mark.asyncio
async def test_stock_deduction_follows_the_deducts_stock_rule(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, warehouse_id = ctx["company"].id, ctx["activity"].id, ctx["activity_warehouse"].id
    product = Product(company_id=company_id, code="PRD-DS", name="Produto DS", vat_id=ctx["vat_nor"].id, price=1000.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    product_id = product.id
    db.add(Stock(company_id=company_id, product_id=product_id, warehouse_id=warehouse_id, quantity=10))
    await db.commit()
    lines = [{"product_id": product_id, "quantity": 2}]

    async def quantity():
        return float((await db.execute(select(Stock.quantity).where(Stock.product_id == product_id, Stock.warehouse_id == warehouse_id))).scalar_one())

    await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
    assert await quantity() == 8.0

    try:
        await _set_rule(db, "FT", deducts_stock=False)
        await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
        assert await quantity() == 8.0  # no longer deducted
    finally:
        await _set_rule(db, "FT", deducts_stock=True)