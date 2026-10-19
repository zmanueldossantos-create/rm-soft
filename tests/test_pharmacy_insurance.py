"""
Farmácia, livraison 4: insurers and agreements. An insurer is a customer with its share; a counter sale shared with it
gives the patient's Fatura-Recibo (his part - the parapharmacy whole when the insurer covers medicines only - the stock
leaving with it) and the insurer's Fatura (its part, paid later, no stock), linked; at 100 % the insurer's Fatura alone.
The monthly statement lists them with what the insurer still owes.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models.company_module import CompanyModule
from app.models.insurance_share import InsuranceShare
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.module import Module
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services.cash_session_service import open_session
from app.services.customer_service import create_customer
from app.services.insurance_service import InsuranceError, list_shares, split_price
from app.services.pos_service import checkout
from app.services.sector_service import seed_sector_catalog
from app.services.stock_service import receive_stock
from app.utils.pharmacy_pdf import generate_insurance_statement_pdf

TODAY = date.today()


async def _setup(db, ctx):
    await seed_sector_catalog(db)
    module = (await db.execute(select(Module).where(Module.code == "FARMACIA"))).scalar_one()
    db.add(CompanyModule(company_id=ctx["company"].id, module_id=module.id, is_enabled=True))
    medicine = Product(company_id=ctx["company"].id, code="AMX" + uuid.uuid4().hex[:4], name="Amoxicilina 500",
                       vat_id=ctx["vat_ise"].id, exemption_reason_id=ctx["exemption_m11"].id, price=1000,
                       min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                       is_medicine=True, active_substance="Amoxicilina", dispensing_regime="LIVRE")
    soap = Product(company_id=ctx["company"].id, code="SAB" + uuid.uuid4().hex[:4], name="Sabonete", vat_id=ctx["vat_nor"].id,
                   price=300, min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add_all([medicine, soap])
    await db.commit()
    for product in (medicine, soap):
        await receive_stock(db, ctx["company"].id, product.id, 10, warehouse_id=ctx["activity_warehouse"].id)
    await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["gestor"], 0)
    return medicine.id, soap.id


async def _stock(db, ctx, product_id):
    return float((await db.execute(select(Stock.quantity).where(
        Stock.product_id == product_id, Stock.warehouse_id == ctx["activity_warehouse"].id))).scalar_one())


def _sale(ctx, lines, pays):
    return dict(lines_input=[{"product_id": pid, "service_id": None, "quantity": q, "sale_unit_id": None} for pid, q in lines],
                payments=[{"payment_method_id": ctx["pm_numerario"].id, "amount": pays}] if pays else [])


@pytest.mark.asyncio
async def test_a_sale_shared_with_an_insurer(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    assert split_price(1000, 80) == (800.0, 200.0) and split_price(333.33, 33) == (110.0, 223.33)

    # an insurer needs the Farmácia, a share between 0 and 100 %, and is never the Consumidor final
    with pytest.raises(InsuranceError):
        await create_customer(db, company_id, "ENSA", "5410000001", insurer={"is_insurer": True, "insurer_coverage_pct": 80})
    medicine, soap = await _setup(db, ctx)
    with pytest.raises(InsuranceError):
        await create_customer(db, company_id, "ENSA", "5410000001", insurer={"is_insurer": True, "insurer_coverage_pct": 0})
    ensa = await create_customer(db, company_id, "ENSA Seguros", "5410000001",
                                 insurer={"is_insurer": True, "insurer_coverage_pct": 80, "insurer_medicines_only": True})
    assert (ensa.is_insurer, float(ensa.insurer_coverage_pct), ensa.insurer_medicines_only) == (True, 80.0, True)

    # 2 medicines at 1 000 and a soap at 300 + 14 %: the insurer pays 80 % of the medicines (1 600), the patient
    # 2 x 200 + the soap whole (342) = 742
    insurance = {"insurer_id": ensa.id, "card_number": " ENSA-0001 ", "beneficiary_name": "Ana Paulo"}
    patient = await checkout(db, company_id, ctx["pos"].id, ctx["gestor"], None, invoice_type="FACTURA_RECIBO",
                             insurance=insurance, **_sale(ctx, [(medicine, 2), (soap, 1)], 742))
    insurer_invoice = (await db.execute(select(Invoice).where(Invoice.id == patient.insurer_invoice_id))).scalar_one()
    assert patient.insurer_invoice_reference == f"{insurer_invoice.series}/{insurer_invoice.number}"
    assert patient.insurer_invoice_total == float(insurer_invoice.total)
    assert (float(patient.total), float(insurer_invoice.total)) == (742.0, 1600.0)
    assert insurer_invoice.customer_id == ensa.id and insurer_invoice.invoice_type.value == "FACTURA"
    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == insurer_invoice.id))).scalars().all()
    assert [(float(l.quantity), float(l.unit_price)) for l in lines] == [(2.0, 800.0)]  # the soap is not covered
    assert f"FR {patient.series}/{patient.number}" in insurer_invoice.observations
    assert f"FT {insurer_invoice.series}/{insurer_invoice.number}" in patient.observations
    # the stock left once, with the patient's document
    assert (await _stock(db, ctx, medicine), await _stock(db, ctx, soap)) == (8.0, 9.0)
    share = (await db.execute(select(InsuranceShare).where(InsuranceShare.insurer_invoice_id == insurer_invoice.id))).scalar_one()
    assert (share.patient_invoice_id, share.card_number, float(share.coverage_pct)) == (patient.id, "ENSA-0001", 80.0)

    # 100 %: the insurer's Fatura alone, and it moves the stock
    alone = await checkout(db, company_id, ctx["pos"].id, ctx["gestor"], None, invoice_type="FACTURA_RECIBO",
                           insurance={**insurance, "coverage_pct": 100}, **_sale(ctx, [(medicine, 1)], 0))
    assert alone.customer_id == ensa.id and alone.insurer_invoice_id == alone.id and float(alone.total) == 1000.0
    assert await _stock(db, ctx, medicine) == 7.0

    # nothing covered (a soap only, the insurer covers medicines): refused, nothing issued
    count = (await db.execute(select(Invoice).where(Invoice.company_id == company_id))).scalars().all()
    with pytest.raises(InsuranceError):
        await checkout(db, company_id, ctx["pos"].id, ctx["gestor"], None, invoice_type="FACTURA_RECIBO",
                       insurance=insurance, **_sale(ctx, [(soap, 1)], 342))
    with pytest.raises(InsuranceError):  # no card
        await checkout(db, company_id, ctx["pos"].id, ctx["gestor"], None, invoice_type="FACTURA_RECIBO",
                       insurance={**insurance, "card_number": "  "}, **_sale(ctx, [(medicine, 1)], 200))
    assert len((await db.execute(select(Invoice).where(Invoice.company_id == company_id))).scalars().all()) == len(count)

    # the statement: both sales, what the insurer owes; the patient's column is his part of the medicines (2 x 200),
    # not the soap he bought too
    rows = await list_shares(db, company_id, TODAY, TODAY, ensa.id)
    assert [(r["patient_reference"] is not None, r["insurer_amount"], r["amount_due"], r["patient_amount"]) for r in rows] == [
        (True, 1600.0, 1600.0, 400.0), (False, 1000.0, 1000.0, 0.0)]
    assert generate_insurance_statement_pdf(rows, {"name": "Farmácia", "nif": "1", "address": None, "bank_accounts": []},
                                            TODAY, TODAY, "ENSA Seguros").startswith(b"%PDF")
    assert generate_insurance_statement_pdf(rows, {"name": "Farmácia", "nif": "1", "address": None, "bank_accounts": []},
                                            TODAY, TODAY, None).startswith(b"%PDF")
