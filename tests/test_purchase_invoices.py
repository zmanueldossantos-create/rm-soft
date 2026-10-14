"""Point 12 (Faturas de compra): a supplier invoice is registered with the VAT the supplier charged; the company
deducts the share its regime allows (data of the regime), the rest is a cost. A supplier of Angola needs its NIF, the
same supplier document is never registered twice, and a registration is cancelled - never deleted."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.fiscal_regime import FiscalRegime
from app.models.legal_vat_rate import LegalVatRate
from app.models.supplier import Supplier
from app.models.vat_code import VatCode
from app.services.purchase_invoice_service import (
    PurchaseInvoiceError, cancel_purchase_invoice, get_purchase_invoice, list_purchase_invoices, register_purchase_invoice,
)
from app.services.supplier_service import SupplierNifRequiredError, create_supplier


async def _rates(db):
    async def rate(category, value):
        found = (await db.execute(select(LegalVatRate).where(LegalVatRate.tax_category == category))).scalar_one_or_none()
        if found is None:
            found = LegalVatRate(tax_category=category, name=category, rate=value)
            db.add(found)
            await db.flush()
        return found
    return await rate("NOR", 14), await rate("ISE", 0)


async def _setup(db, ctx, pct):
    company = ctx["company"]
    regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id))).scalar_one()
    regime.input_vat_deductible_pct = pct
    supplier = Supplier(company_id=company.id, name="Grossista Lda", nif="5000111222")
    db.add(supplier)
    nor, ise = await _rates(db)
    await db.commit()
    return supplier, nor, ise


def _line(rate, quantity=10, price=100, **extra):
    return {"description": "Farinha", "quantity": quantity, "unit_price": price, "legal_vat_rate_id": rate.id, **extra}


@pytest.mark.asyncio
@pytest.mark.parametrize("pct,deductible,cost", [(100, 140.0, 1000.0), (7, 9.8, 1130.2), (0, 0.0, 1140.0)])
async def test_the_regime_decides_the_deductible_vat(db, company_with_essentials, pct, deductible, cost):
    ctx = company_with_essentials
    supplier, nor, _ = await _setup(db, ctx, pct)
    invoice = await register_purchase_invoice(db, ctx["company"].id, ctx["gestor"].id, supplier.id, "FT A/1",
                                              date.today(), [_line(nor)])
    detail = await get_purchase_invoice(db, ctx["company"].id, invoice.id)
    assert detail["description"] is None  # the line's text never becomes the invoice's description
    assert (detail["subtotal"], detail["vat_total"], detail["total"]) == (1000.0, 140.0, 1140.0)
    assert (detail["vat_deductible"], detail["lines"][0]["cost"]) == (deductible, cost)
    assert detail["reference"] == f"COMP{date.today().year}/1"


@pytest.mark.asyncio
async def test_an_exempt_line_needs_its_motive_and_a_document_is_registered_once(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    supplier, nor, ise = await _setup(db, ctx, 100)
    with pytest.raises(PurchaseInvoiceError, match="motivo de isenção"):
        await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/2", date.today(), [_line(ise)])
    motive = (await db.execute(select(VatCode))).scalars().first()
    invoice = await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/2", date.today(),
                                              [_line(ise, exemption_id=motive.id)])
    with pytest.raises(PurchaseInvoiceError, match="já está registado"):
        await register_purchase_invoice(db, company_id, user_id, supplier.id, "ft a/2", date.today(), [_line(nor)])

    await cancel_purchase_invoice(db, company_id, invoice.id, user_id, "Registada em duplicado")
    listed = await list_purchase_invoices(db, company_id)
    assert [(i["supplier_document"], i["status"]) for i in listed] == [("FT A/2", "ANULADA")]
    await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/2", date.today(), [_line(nor)])  # again


@pytest.mark.asyncio
async def test_a_supplier_of_angola_needs_its_nif(db, company_with_essentials):
    with pytest.raises(SupplierNifRequiredError):
        await create_supplier(db, company_with_essentials["company"].id, "Sem NIF")
