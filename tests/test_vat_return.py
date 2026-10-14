"""Point 12, step 4 (Apuramento do IVA): the VAT of a month - charged on the sales documents (a credit note against,
each line after its share of the global discount, pro-formas left out), deductible on the purchase invoices booked in
the period - and the result by the regime's data (Regime Geral: liquidado - dedutível; a turnover rate adds its %)."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_regime import FiscalRegime
from app.models.invoice import Invoice, InvoiceType
from app.models.invoice_line import InvoiceLine
from app.models.legal_vat_rate import LegalVatRate
from app.models.supplier import Supplier
from app.services.purchase_invoice_service import register_purchase_invoice
from app.services.vat_return_service import get_vat_return, list_vat_documents


async def _sale(db, ctx, invoice_type, number, lines, discount=0, total=None):
    """lines: (base, rate, code, exemption) - the stored amounts, before the global discount."""
    subtotal = sum(b for b, *_ in lines)
    vat = round(sum(b * r / 100 for b, r, *_ in lines), 2)
    invoice = Invoice(company_id=ctx["company"].id, activity_id=ctx["activity"].id, invoice_type=invoice_type,
                      series="T", number=number, business_date=date.today(), subtotal=subtotal, vat_total=vat,
                      total=total if total is not None else subtotal + vat, discount_global_percent=discount,
                      atcud="X", invoice_hash="X", qr_code_data="X")
    db.add(invoice)
    await db.flush()
    for base, rate, code, exemption in lines:
        db.add(InvoiceLine(invoice_id=invoice.id, product_name_snapshot="Artigo", quantity=1, unit_price=base,
                           vat_rate_snapshot=rate, tax_code_snapshot=code, exemption_code=exemption, line_subtotal=base,
                           line_vat=round(base * rate / 100, 2), line_total=round(base * (1 + rate / 100), 2)))


@pytest.mark.asyncio
async def test_the_month_vat_is_charged_minus_deductible(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    await _sale(db, ctx, InvoiceType.FACTURA, 1, [(1000, 14, "NOR", None), (300, 0, "ISE", "M11")])
    await _sale(db, ctx, InvoiceType.FACTURA_RECIBO, 2, [(600, 14, "NOR", None)], discount=10, total=615.6)  # 540 + 75,60
    await _sale(db, ctx, InvoiceType.NOTA_CREDITO, 3, [(200, 14, "NOR", None)])
    await _sale(db, ctx, InvoiceType.PRO_FORMA, 4, [(5000, 14, "NOR", None)])  # no VAT in a pro-forma
    supplier = Supplier(company_id=company_id, name="Grossista IVA", nif="5000999888")
    nor = (await db.execute(select(LegalVatRate).where(LegalVatRate.tax_category == "NOR"))).scalar_one_or_none()
    if nor is None:
        nor = LegalVatRate(tax_category="NOR", name="NOR", rate=14)
        db.add(nor)
    db.add(supplier)
    await db.commit()
    await register_purchase_invoice(db, company_id, ctx["gestor"].id, supplier.id, "FT C/1", date.today(),
                                    [{"description": "Farinha", "quantity": 1, "unit_price": 500, "legal_vat_rate_id": nor.id}])
    period_id = (await db.execute(select(FiscalPeriod.id).where(FiscalPeriod.company_id == company_id))).scalar_one()

    data = await get_vat_return(db, company_id, period_id)
    assert [(l["tax_code"], l["exemption_code"], l["base"], l["vat"], l["documents"]) for l in data["sales"]] == [
        ("NOR", None, 1340.0, 187.6, 3), ("ISE", "M11", 300.0, 0.0, 1)]
    assert (data["output_vat"], data["deductible_vat"], data["result"], data["to_pay"]) == (187.6, 70.0, 117.6, 117.6)

    documents = await list_vat_documents(db, company_id, period_id, "sales", "NOR", 14)
    assert sorted((d["reference"], d["base"], d["vat"]) for d in documents) == [
        ("FR T/2", 540.0, 75.6), ("FT T/1", 1000.0, 140.0), ("NC T/3", -200.0, -28.0)]

    # a regime that owes 7 % of its turnover adds it: 187,60 + 1 640 x 7 % - 70
    regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == ctx["company"].fiscal_regime_id))).scalar_one()
    regime.turnover_vat_pct = 7
    await db.commit()
    data = await get_vat_return(db, company_id, period_id)
    assert (data["turnover_vat"], data["result"]) == (114.8, 232.4)
    from app.services.cash_report_service import _company_dict
    from app.utils.vat_return_pdf import generate_vat_return_pdf
    assert generate_vat_return_pdf(data, _company_dict(ctx["company"])).startswith(b"%PDF")
