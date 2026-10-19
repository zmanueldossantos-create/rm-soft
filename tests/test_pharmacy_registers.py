"""
Farmácia, livraison 3: the registers built from what is recorded - the trace of a lot (where it came from, who bought
it, what is left), the registo de receitas and the registo de psicotrópicos (stock at the start, entries, exits with
their receita, stock at the end), and their PDFs.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.stock_lot import StockLot
from app.services.invoice_service import create_invoice
from app.services.pharmacy_register_service import (
    LotNotFoundError, RegisterError, list_prescriptions, psychotropic_register, trace_lot,
)
from app.services.stock_service import receive_stock, record_stock_loss, transfer_stock
from app.utils.pharmacy_pdf import generate_lot_trace_pdf, generate_prescriptions_pdf, generate_psychotropics_pdf

TODAY = date.today()
EXPIRY = TODAY + timedelta(days=300)
COMPANY = {"name": "Farmácia Teste", "nif": "5000000000", "address": None, "bank_accounts": []}


async def _medicine(db, ctx, regime, name):
    product = Product(company_id=ctx["company"].id, code=name[:3].upper() + uuid.uuid4().hex[:4], name=name,
                      vat_id=ctx["vat_ise"].id, exemption_reason_id=ctx["exemption_m11"].id, price=500,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                      managed_by_batch=True, managed_by_expiry=True, is_medicine=True, active_substance=name,
                      dosage="5 mg", dispensing_regime=regime)
    db.add(product)
    await db.commit()
    return product.id


async def _sell(db, ctx, product_id, quantity, prescription=None):
    return await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                                lines_input=[{"product_id": product_id, "quantity": quantity}], prescription=prescription)


@pytest.mark.asyncio
async def test_the_registers_of_a_medicine_of_receita_especial(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, central, shop = ctx["company"].id, ctx["central_warehouse"].id, ctx["activity_warehouse"].id
    diazepam = await _medicine(db, ctx, "RECEITA_ESPECIAL", "Diazepam")
    await receive_stock(db, company_id, diazepam, 10, reason="Fatura de compra 1 - Grossista", lot_number="D1",
                        expiry_date=EXPIRY, warehouse_id=central)
    await transfer_stock(db, company_id, diazepam, central, shop, 6)
    sale = await _sell(db, ctx, diazepam, 2, {"number": "R-1", "prescriber": "Dr. Silva", "patient_name": "Ana Paulo",
                                              "patient_document": "004512345LA041"})
    await record_stock_loss(db, company_id, shop, diazepam, 1, "QUEBRA", "Frasco partido")

    # the trace of the lot: the entry, the transfer (both warehouses), the sale with its customer and receita, the loss
    lot = (await db.execute(select(StockLot).where(StockLot.product_id == diazepam, StockLot.warehouse_id == shop))).scalar_one()
    trace = await trace_lot(db, company_id, lot.id)
    assert [(m["type"], m["quantity_in"], m["quantity_out"]) for m in trace["movements"]] == [
        ("Entrada", 10.0, None), ("Transferência", None, 6.0), ("Transferência", 6.0, None),
        ("Saída", None, 2.0), ("Perda", None, 1.0)]
    sale_row = trace["movements"][3]
    assert (sale_row["reference"], sale_row["detail"], sale_row["prescription"]) == (f"FT {sale.series}/{sale.number}", "Consumidor final", "R-1")
    assert trace["sold_total"] == 2.0 and trace["remaining_total"] == 7.0
    assert sorted((r["warehouse"], r["quantity"]) for r in trace["remaining"]) == [
        ("Armazem Principal", 4.0), ("Atividade - Ponto de Venda", 3.0)]
    with pytest.raises(LotNotFoundError):
        await trace_lot(db, company_id, uuid.uuid4())

    # the registo de receitas: the sale, its medicine and lot
    entries = await list_prescriptions(db, company_id, TODAY, TODAY)
    assert [(e["number"], e["is_special"], e["patient_document"]) for e in entries] == [("R-1", True, "004512345LA041")]
    assert entries[0]["items"][0]["product_name"] == "Diazepam" and entries[0]["items"][0]["lots"][0].startswith("Lote D1")
    assert await list_prescriptions(db, company_id, TODAY, TODAY, special=False) == []
    assert len(await list_prescriptions(db, company_id, TODAY, TODAY, search="silva")) == 1
    with pytest.raises(RegisterError):
        await list_prescriptions(db, company_id, TODAY, TODAY - timedelta(days=1))

    # the registo de psicotrópicos: 0 at the start, +10, -2 sold (with its receita), -1 lost, 7 at the end - the
    # transfer between the company's warehouses is not listed
    register = await psychotropic_register(db, company_id, TODAY, TODAY)
    assert len(register) == 1
    product = register[0]
    assert (product["opening"], product["total_in"], product["total_out"], product["closing"]) == (0.0, 10.0, 3.0, 7.0)
    assert [(l["type"], l["balance"]) for l in product["lines"]] == [("Entrada", 10.0), ("Saída", 8.0), ("Perda", 7.0)]
    assert (product["lines"][1]["prescription"], product["lines"][1]["patient"]) == ("R-1", "Ana Paulo")
    assert product["lines"][2]["detail"] == "quebra - Frasco partido"

    # a later period starts from the stock at its start
    later = await psychotropic_register(db, company_id, TODAY + timedelta(days=1), TODAY + timedelta(days=2))
    assert [(p["opening"], p["closing"], p["lines"]) for p in later] == [(7.0, 7.0, [])]

    assert generate_lot_trace_pdf(trace, COMPANY).startswith(b"%PDF")
    assert generate_prescriptions_pdf(entries, COMPANY, TODAY, TODAY).startswith(b"%PDF")
    assert generate_psychotropics_pdf(register, COMPANY, TODAY, TODAY).startswith(b"%PDF")
    assert generate_psychotropics_pdf([], COMPANY, TODAY, TODAY).startswith(b"%PDF")
