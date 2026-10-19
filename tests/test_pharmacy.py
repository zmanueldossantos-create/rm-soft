"""
Farmácia, livraison 1: the medicine sheet (substance, form, dosage, dispensing regime, cold storage - always followed by
lot and expiry), only for a company with the Farmácia sector; the GESTOR's list of pharmaceutical forms; and the
exemptions a regime imposing a motive still keeps (M11 medicines under the Simplificado: their own motive, out of the
turnover base) - data set by the SUPER_ADMIN after the accountant's answer.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models.company_module import CompanyModule
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_regime import FiscalRegime
from app.models.invoice import Invoice, InvoiceType
from app.models.invoice_line import InvoiceLine
from app.models.module import Module
from app.models.product import Product, ProductType
from app.models.vat_code import VatCode
from app.services.fiscal_regime_service import _kept_exemptions
from app.services.pharmacy_service import (
    MedicineError, PharmaceuticalFormAlreadyExistsError, create_form, pharmacy_context, toggle_form, update_form,
)
from app.services.product_service import LotTrackingLockedError, create_product, update_product
from app.services.sector_service import seed_sector_catalog
from app.services.stock_service import receive_stock
from app.services.vat_return_service import get_vat_return
from app.services.vat_rule_service import (
    ArticleVatError, articles_to_reclassify, auto_reclassify, imposed_exemption, resolve_article_vat,
)


async def _grant_pharmacy(db, ctx):
    await seed_sector_catalog(db)
    module = (await db.execute(select(Module).where(Module.code == "FARMACIA"))).scalar_one()
    db.add(CompanyModule(company_id=ctx["company"].id, module_id=module.id, is_enabled=True))
    await db.commit()


def _sheet(ctx, **extra):
    base = dict(code="MED" + uuid.uuid4().hex[:5], name="Ben-u-ron " + uuid.uuid4().hex[:4], barcode=None,
                vat_id=ctx["vat_ise"].id, price=850, min_stock_threshold=0, unit_of_measure_id=ctx["unit_un"].id,
                exemption_reason_id=ctx["exemption_m11"].id)
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_a_medicine_needs_the_pharmacy_sector_and_is_always_followed_by_lot_and_expiry(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    medicine = dict(is_medicine=True, active_substance="  Paracetamol ", dosage="500 mg", dispensing_regime="LIVRE")

    # a company without the Farmácia sector: no medicine, no context
    with pytest.raises(MedicineError):
        await create_product(db, company_id, **_sheet(ctx, **medicine))
    assert (await pharmacy_context(db, company_id))["enabled"] is False

    await _grant_pharmacy(db, ctx)
    context = await pharmacy_context(db, company_id)
    assert context["enabled"] is True and context["medicine_exemption"]["code"] == "M11"

    # the substance and the dispensing regime are required; the form must be the company's and active
    with pytest.raises(MedicineError):
        await create_product(db, company_id, **_sheet(ctx, **{**medicine, "active_substance": "  "}))
    with pytest.raises(MedicineError):
        await create_product(db, company_id, **_sheet(ctx, **{**medicine, "dispensing_regime": None}))
    tablet = await create_form(db, company_id, "Comprimido")
    with pytest.raises(PharmaceuticalFormAlreadyExistsError):
        await create_form(db, company_id, " comprimido ")
    syrup = await create_form(db, company_id, "Xarope")
    await toggle_form(db, company_id, syrup.id)
    with pytest.raises(MedicineError):
        await create_product(db, company_id, **_sheet(ctx, **medicine, pharmaceutical_form_id=syrup.id))

    # saved: followed by stock, lot and expiry whatever the form sent; the substance cleaned
    product = await create_product(db, company_id, **_sheet(ctx, **medicine, pharmaceutical_form_id=tablet.id,
                                                             managed_by_batch=False, managed_by_expiry=False,
                                                             cold_storage=True))
    assert (product.is_medicine, product.active_substance, product.dosage, product.cold_storage) == (True, "Paracetamol", "500 mg", True)
    assert (product.managed_by_stock, product.managed_by_batch, product.managed_by_expiry) == (True, True, True)
    assert product.pharmaceutical_form_id == tablet.id

    # a form deactivated since is kept by the medicine that has it; renamed, it follows
    await toggle_form(db, company_id, tablet.id)
    await update_form(db, company_id, tablet.id, "Comprimido revestido")
    sheet = _sheet(ctx, **{**medicine, "dispensing_regime": "RECEITA"}, pharmaceutical_form_id=tablet.id)
    sheet.update(code=product.code, name=product.name)
    product = await update_product(db, company_id, product.id, **sheet)
    assert product.dispensing_regime == "RECEITA"

    # with stock, it cannot stop being followed by lot: no longer a medicine is refused until the stock is zero
    await receive_stock(db, company_id, product.id, 10, lot_number="L1", expiry_date=date(2030, 1, 1))
    plain = _sheet(ctx)
    plain.update(code=product.code, name=product.name)
    with pytest.raises(LotTrackingLockedError):
        await update_product(db, company_id, product.id, **plain)

    # not a medicine: no pharmacy field kept
    other = await create_product(db, company_id, **_sheet(ctx, active_substance="Ibuprofeno", dispensing_regime="LIVRE"))
    assert (other.is_medicine, other.active_substance, other.dispensing_regime) == (False, None, None)


async def _simplified_regime(db, ctx, kept):
    m00 = VatCode(code="M00", name="IVA - Regime Simplificado", rate=0, country_id=ctx["exemption_m11"].country_id,
                  valid_from=date(2021, 1, 1))
    db.add(m00)
    await db.flush()
    regime = FiscalRegime(name="Simplificado " + uuid.uuid4().hex[:5], allows_nor=False, allows_red=False, allows_ise=True,
                          required_exemption_id=m00.id, turnover_vat_pct=7, input_vat_deductible_pct=7,
                          kept_exemption_ids=kept)
    db.add(regime)
    await db.flush()
    company = ctx["company"]
    company.fiscal_regime_id = regime.id
    await db.commit()
    return regime, m00


@pytest.mark.asyncio
async def test_a_regime_imposing_a_motive_keeps_the_exemptions_it_lists(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, m11 = ctx["company"].id, ctx["exemption_m11"]
    regime, m00 = await _simplified_regime(db, ctx, [m11.id])

    # kept: only under a regime imposing a motive, never the imposed motive itself, without duplicates
    assert _kept_exemptions(None, [m11.id]) == []
    assert _kept_exemptions(m00.id, [m11.id, m00.id, m11.id]) == [m11.id]

    # the kept exemption stays the article's own; anything else takes the imposed motive
    assert await resolve_article_vat(db, company_id, ctx["vat_ise"].id, m11.id) == m11.id
    assert await resolve_article_vat(db, company_id, ctx["vat_ise"].id, None) == m00.id
    rule = await imposed_exemption(db, company_id)
    assert rule["exemption"]["code"] == "M00" and [k["code"] for k in rule["kept"]] == ["M11"]

    medicine = Product(company_id=company_id, code="PARA1", name="Paracetamol", vat_id=ctx["vat_ise"].id, price=1,
                       min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                       exemption_reason_id=m11.id)
    soap = Product(company_id=company_id, code="SAB1", name="Sabonete", vat_id=ctx["vat_nor"].id, price=1,
                   min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add_all([medicine, soap])
    await db.commit()
    await auto_reclassify(db, company_id, regime)
    await db.commit()
    await db.refresh(medicine)
    await db.refresh(soap)
    assert (medicine.exemption_reason_id, soap.exemption_reason_id, soap.vat_id) == (m11.id, m00.id, ctx["vat_ise"].id)
    assert (await articles_to_reclassify(db, company_id))["products"] == []

    # the accountant says no: M11 no longer kept - the medicine must be reclassified, M11 is refused
    regime.kept_exemption_ids = []
    await db.commit()
    assert [p["code"] for p in (await articles_to_reclassify(db, company_id))["products"]] == ["PARA1"]
    assert await resolve_article_vat(db, company_id, ctx["vat_ise"].id, m11.id) == m00.id
    with pytest.raises(ArticleVatError):
        from app.services.vat_rule_service import ensure_article_sellable
        await ensure_article_sellable(db, medicine)


@pytest.mark.asyncio
async def test_the_kept_exemptions_stay_out_of_the_turnover_base(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    regime, _ = await _simplified_regime(db, ctx, [ctx["exemption_m11"].id])
    invoice = Invoice(company_id=company_id, activity_id=ctx["activity"].id, invoice_type=InvoiceType.FACTURA_RECIBO,
                      series="T", number=1, business_date=date.today(), subtotal=1500, vat_total=0, total=1500,
                      atcud="X", invoice_hash="X", qr_code_data="X")
    db.add(invoice)
    await db.flush()
    for base, exemption in ((1000, "M11"), (500, "M00")):  # a medicine and a soap
        db.add(InvoiceLine(invoice_id=invoice.id, product_name_snapshot="Artigo", quantity=1, unit_price=base,
                           vat_rate_snapshot=0, tax_code_snapshot="ISE", exemption_code=exemption, line_subtotal=base,
                           line_vat=0, line_total=base))
    await db.commit()
    period_id = (await db.execute(select(FiscalPeriod.id).where(FiscalPeriod.company_id == company_id))).scalar_one()

    data = await get_vat_return(db, company_id, period_id)
    assert (data["sales_base"], data["turnover_base"], data["turnover_excluded"], data["turnover_vat"]) == (1500.0, 500.0, 1000.0, 35.0)
    assert data["turnover_excluded_codes"] == ["M11"]

    # nothing kept: every sale is in the base
    regime.kept_exemption_ids = []
    await db.commit()
    data = await get_vat_return(db, company_id, period_id)
    assert (data["turnover_base"], data["turnover_vat"]) == (1500.0, 105.0)
