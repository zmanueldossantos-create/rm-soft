"""
Farmácia, livraison 2: the receita of a sale - required by the medicines sold (RECEITA: by the company's policy;
RECEITA_ESPECIAL: always, with the patient and his document), recorded with the document - and the lots the goods
left in, printed under the lines of the documents (any sector).
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.prescription import Prescription
from app.models.product import Product, ProductType
from app.services.invoice_service import create_invoice
from app.services.pharmacy_service import PrescriptionRequiredError, prescription_text
from app.services.stock_lot_service import lots_of_document
from app.services.stock_service import receive_stock

EXPIRY = date.today() + timedelta(days=400)


async def _medicine(db, ctx, regime, name):
    product = Product(company_id=ctx["company"].id, code=name[:3].upper() + uuid.uuid4().hex[:4], name=name,
                      vat_id=ctx["vat_ise"].id, exemption_reason_id=ctx["exemption_m11"].id, price=500,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                      managed_by_batch=True, managed_by_expiry=True, is_medicine=True, active_substance=name,
                      dispensing_regime=regime)
    db.add(product)
    await db.commit()
    shop = ctx["activity_warehouse"].id
    await receive_stock(db, ctx["company"].id, product.id, 3, lot_number="A1", expiry_date=EXPIRY, warehouse_id=shop)
    await receive_stock(db, ctx["company"].id, product.id, 5, lot_number="B2", expiry_date=EXPIRY + timedelta(days=30), warehouse_id=shop)
    return product.id


async def _sell(db, ctx, product_id, quantity=1, prescription=None, invoice_type="FACTURA"):
    return await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type=invoice_type,
                                lines_input=[{"product_id": product_id, "quantity": quantity}], prescription=prescription)


@pytest.mark.asyncio
async def test_a_medicine_on_prescription_needs_its_receita_by_the_company_policy(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    free = await _medicine(db, ctx, "LIVRE", "Paracetamol")
    amox = await _medicine(db, ctx, "RECEITA", "Amoxicilina")

    # a medicine sold freely: nothing asked, nothing recorded (even if sent)
    invoice = await _sell(db, ctx, free, prescription={"number": "999"})
    assert (await db.execute(select(Prescription).where(Prescription.invoice_id == invoice.id))).scalar_one_or_none() is None

    # OBRIGATORIA (the default): no number, no sale - and no number taken from the series
    with pytest.raises(PrescriptionRequiredError):
        await _sell(db, ctx, amox, prescription={"prescriber": "Dr. Silva"})
    invoice = await _sell(db, ctx, amox, prescription={"number": " 12345 ", "prescriber": "Dr. Silva", "patient_name": ""})
    assert invoice.number == 2  # the refused sale used no number
    recorded = (await db.execute(select(Prescription).where(Prescription.invoice_id == invoice.id))).scalar_one()
    assert (recorded.number, recorded.prescriber, recorded.patient_name, recorded.is_special) == ("12345", "Dr. Silva", None, False)
    assert prescription_text(recorded) == "Receita n.º 12345 · Dr. Silva"

    # SE_APRESENTADA: the sale goes through without a receita
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
    company.prescription_policy = "SE_APRESENTADA"
    await db.commit()
    invoice = await _sell(db, ctx, amox)
    assert (await db.execute(select(Prescription).where(Prescription.invoice_id == invoice.id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_receita_especial_always_needs_the_patient_and_his_document(db, company_with_essentials):
    ctx = company_with_essentials
    company = ctx["company"]
    company.prescription_policy = "SE_APRESENTADA"  # whatever the policy
    await db.commit()
    diazepam = await _medicine(db, ctx, "RECEITA_ESPECIAL", "Diazepam")
    with pytest.raises(PrescriptionRequiredError) as refused:
        await _sell(db, ctx, diazepam, prescription={"number": "77"})
    assert "nome do utente" in str(refused.value) and "documento de identificação" in str(refused.value)
    invoice = await _sell(db, ctx, diazepam, prescription={"number": "77", "patient_name": "Ana Paulo",
                                                         "patient_document": "004512345LA041"})
    recorded = (await db.execute(select(Prescription).where(Prescription.invoice_id == invoice.id))).scalar_one()
    assert recorded.is_special and prescription_text(recorded) == "Receita especial n.º 77 · Utente: Ana Paulo (004512345LA041)"


@pytest.mark.asyncio
async def test_the_lots_a_sale_took_are_found_for_its_document(db, company_with_essentials):
    ctx = company_with_essentials
    product_id = await _medicine(db, ctx, "LIVRE", "Ibuprofeno")
    one = await _sell(db, ctx, product_id, quantity=2)
    two = await _sell(db, ctx, product_id, quantity=3)  # 1 left in A1, then 2 from B2
    one_lots = await lots_of_document(db, ctx["company"].id, f"FT {one.series}/{one.number}")
    two_lots = await lots_of_document(db, ctx["company"].id, f"FT {two.series}/{two.number}")
    day = EXPIRY.strftime("%d/%m/%Y")
    later = (EXPIRY + timedelta(days=30)).strftime("%d/%m/%Y")
    assert one_lots == {product_id: [f"Lote A1 · Val. {day}"]}
    assert two_lots == {product_id: [f"Lote A1 · Val. {day} (1)", f"Lote B2 · Val. {later} (2)"]}

    # printed under the line, on the A4 and on the ticket
    from app.utils.pdf_generator import generate_invoice_pdf_a4, generate_invoice_pdf_thermal
    invoice = {"invoice_type": "FT", "series": two.series, "number": two.number, "business_date": str(date.today()),
               "subtotal": 1500.0, "vat_total": 0.0, "total": 1500.0, "print_count": 1, "is_fiscal_doc": True,
               "atcud": "X", "invoice_hash": "X", "qr_code_data": "X", "prescription": "Receita n.º 1 · Dr. X",
               "created_at": None, "payments": []}
    lines = [{"code": "IBU", "unit": "UN", "product_name_snapshot": "Ibuprofeno", "quantity": 3, "unit_code": "UN",
              "unit_price": 500.0, "discount_percent": 0, "vat_rate_snapshot": 0, "line_subtotal": 1500.0,
              "line_total": 1500.0, "exemption_code": "M11", "exemption_reason": "Isento", "lots": two_lots[product_id]}]
    company = {"name": "Farmácia", "nif": "5000000000", "address": None, "bank_accounts": []}
    assert generate_invoice_pdf_a4(invoice, lines, company, None).startswith(b"%PDF")
    assert generate_invoice_pdf_thermal(invoice, lines, company, None).startswith(b"%PDF")
