"""
A receipt settles its invoice pro rata: it carries the settled part of the document (net, VAT, total, withholding)
and the cash in amount_received / Payment - with the payment method given (else the invoice's, else Numerario) and,
when a cash session is given, the money counts in the drawer if the method is cash.
"""
import pytest
from sqlalchemy import select, text

from app.models.customer import Customer, LegalPersonType
from app.models.payment import Payment
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.services.cash_session_service import get_current_expected_cash_balance, open_session
from app.services.invoice_service import create_invoice, create_receipt


async def _service(db, ctx, code, withholding_tax_id=None):
    service = Service(company_id=ctx["company"].id, code=code, name="Servico " + code, price=1000.0,
                      vat_id=ctx["vat_nor"].id, withholding_tax_id=withholding_tax_id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service.id


async def _invoice(db, ctx, service_id, quantity, customer_id=None):
    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=customer_id, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": quantity}],
    )
    return invoice.id


def _figures(receipt):
    return (float(receipt.subtotal), float(receipt.vat_total), float(receipt.total),
            float(receipt.retention_total), float(receipt.amount_received))


async def _payments(db, receipt_id):
    rows = (await db.execute(select(Payment).where(Payment.invoice_id == receipt_id))).scalars().all()
    return [(float(p.amount), p.payment_method_id) for p in rows]


@pytest.mark.asyncio
async def test_receipt_settles_the_invoice_pro_rata_with_its_withholding(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, numerario_id = ctx["company"].id, ctx["activity"].id, ctx["pm_numerario"].id
    tax = WithholdingTax(name="Retencao RC", rate=6.5, tax_type="II")
    db.add(tax)
    customer = Customer(company_id=company_id, name="Empresa PJ", nif="5000111555", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    await db.refresh(tax)
    await db.refresh(customer)
    customer_id = customer.id
    service_id = await _service(db, ctx, "SRV-RC", tax.id)

    full_invoice_id = await _invoice(db, ctx, service_id, 2, customer_id)  # 2280, withholding 130, cash due 2150
    full = await create_receipt(db, company_id, activity_id, reference_invoice_id=full_invoice_id, amount=2150.0)
    full_id = full.id
    assert _figures(full) == (2000.0, 280.0, 2280.0, 130.0, 2150.0)
    assert await _payments(db, full_id) == [(2150.0, numerario_id)]

    half_invoice_id = await _invoice(db, ctx, service_id, 2, customer_id)
    half = await create_receipt(db, company_id, activity_id, reference_invoice_id=half_invoice_id, amount=1075.0)
    assert _figures(half) == (1000.0, 140.0, 1140.0, 65.0, 1075.0)


@pytest.mark.asyncio
async def test_receipt_without_withholding_keeps_the_vat_pro_rata(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    invoice_id = await _invoice(db, ctx, await _service(db, ctx, "SRV-VT"), 1)  # 1000 + 140 = 1140

    first = await create_receipt(db, company_id, activity_id, reference_invoice_id=invoice_id, amount=500.0)
    assert (round(float(first.subtotal), 2), round(float(first.vat_total), 2), round(float(first.total), 2)) == (438.6, 61.4, 500.0)
    second = await create_receipt(db, company_id, activity_id, reference_invoice_id=invoice_id, amount=640.0)
    assert (round(float(second.subtotal), 2), round(float(second.vat_total), 2), round(float(second.total), 2)) == (561.4, 78.6, 640.0)


@pytest.mark.asyncio
async def test_receipt_payment_method_and_cash_session(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    card_id = (await db.execute(text("SELECT id FROM payment_method_catalog WHERE code = 'MB'"))).scalar_one()
    invoice_id = await _invoice(db, ctx, await _service(db, ctx, "SRV-CX"), 1)

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    session_id = session.id

    cash = await create_receipt(db, company_id, activity_id, reference_invoice_id=invoice_id, amount=500.0, cash_session_id=session_id)
    cash_id = cash.id
    assert await get_current_expected_cash_balance(db, company_id, pos_id) == 500.0  # Numerario: money in the drawer

    card = await create_receipt(db, company_id, activity_id, reference_invoice_id=invoice_id, amount=100.0,
                                payment_method_id=card_id, cash_session_id=session_id)
    card_receipt_id = card.id
    assert await get_current_expected_cash_balance(db, company_id, pos_id) == 500.0  # a card payment is not cash
    assert await _payments(db, card_receipt_id) == [(100.0, card_id)]
    assert len(await _payments(db, cash_id)) == 1