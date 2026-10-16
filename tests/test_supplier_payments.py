"""Point 3: paying the suppliers - a payment (PAG) settles invoices of one supplier, fully or in part, never more than
what is owed (an NC lowers it; a FR was paid on issue); cash leaves a till (an automatic exit), cancelling puts it back;
an invoice with a payment is not cancelled; the conta corrente gives the running balance."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.cash_movement import CashMovement
from app.models.supplier import Supplier
from app.services.cash_session_service import get_current_expected_cash_balance, get_open_session, open_session
from app.services.purchase_invoice_service import (
    PurchaseInvoiceError, cancel_purchase_invoice, get_purchase_invoice, list_purchase_invoices, register_purchase_invoice,
)
from app.services.supplier_payment_service import (
    SupplierPaymentError, cancel_supplier_payment, create_supplier_payment, get_supplier_payment, supplier_balances,
    supplier_statement,
)
from tests.test_purchase_invoices import _line, _rates


async def _setup(db, ctx):
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    supplier = Supplier(company_id=company_id, name="Moagem do Kikolo", nif="5000333444")
    other = Supplier(company_id=company_id, name="Outro", nif="5000333555")
    db.add_all([supplier, other])
    nor, _ = await _rates(db)
    await db.commit()
    today = date.today()
    # 1140 each (10 x 100 + 14 %)
    ft1 = await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/1", today, [_line(nor)])
    ft1.due_date = today - timedelta(days=1)  # overdue
    await db.commit()
    ft2 = await register_purchase_invoice(db, company_id, user_id, supplier.id, "FT A/2", today, [_line(nor)])
    fr = await register_purchase_invoice(db, company_id, user_id, supplier.id, "FR A/3", today, [_line(nor)], purchase_type="FR")
    nc = await register_purchase_invoice(db, company_id, user_id, supplier.id, "NC A/1", today, [_line(nor, quantity=1)],
                                         purchase_type="NC", reference_invoice_id=ft2.id)  # 114 off FT A/2
    other_ft = await register_purchase_invoice(db, company_id, user_id, other.id, "FT B/1", today, [_line(nor)])
    return company_id, supplier.id, ft1.id, ft2.id, fr.id, nc.id, other_ft.id


async def _by_doc(db, company_id, supplier_id):
    return {i["supplier_document"]: i for i in await list_purchase_invoices(db, company_id, supplier_id=supplier_id)}


@pytest.mark.asyncio
async def test_a_payment_settles_what_is_owed_and_leaves_the_till(db, company_with_essentials):
    ctx = company_with_essentials
    user = ctx["gestor"]
    company_id, supplier_id, ft1, ft2, fr, nc, other_ft = await _setup(db, ctx)
    docs = await _by_doc(db, company_id, supplier_id)
    assert (docs["FT A/1"]["amount_due"], docs["FT A/1"]["payment_status"], docs["FT A/1"]["overdue"]) == (1140.0, "PENDENTE", True)
    assert (docs["FT A/2"]["amount_due"], docs["FT A/2"]["payment_status"]) == (1026.0, "PARCIAL")  # the NC lowers it
    assert (docs["FR A/3"]["amount_due"], docs["FR A/3"]["payment_status"]) == (0.0, "PAGA")  # paid on issue
    assert (await supplier_balances(db, company_id))[supplier_id] == 2166.0

    cash, pos = ctx["pm_numerario"].id, ctx["pos"].id
    with pytest.raises(SupplierPaymentError, match="excede"):
        await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": ft2, "amount": 1140}], ctx["pm_mb"].id)
    with pytest.raises(SupplierPaymentError, match="não é deste fornecedor"):
        await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": other_ft, "amount": 10}], ctx["pm_mb"].id)
    with pytest.raises(SupplierPaymentError, match="não se paga"):
        await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": fr, "amount": 10}], ctx["pm_mb"].id)
    with pytest.raises(SupplierPaymentError, match="sessão aberta"):  # cash from a closed till
        await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": ft1, "amount": 100}], cash, pos_id=pos)

    await db.refresh(user)  # a refused payment rolled the session back
    await open_session(db, company_id, pos, user, 1000)
    with pytest.raises(SupplierPaymentError, match="disponíveis"):  # more than the drawer holds
        await create_supplier_payment(db, company_id, user, supplier_id, [{"purchase_invoice_id": ft1, "amount": 1140}],
                                      cash, pos_id=pos)
    await db.refresh(user)
    payment = await create_supplier_payment(db, company_id, user, supplier_id,
                                            [{"purchase_invoice_id": ft1, "amount": 500}, {"purchase_invoice_id": ft2, "amount": 300}],
                                            cash, pos_id=pos, reference_text="  rec  12 ")
    payment_id = payment.id
    detail = await get_supplier_payment(db, company_id, payment_id)
    assert (detail["reference"], detail["amount"], detail["reference_text"]) == (f"PAG{date.today().year}/1", 800.0, "rec 12")
    assert sorted(a["amount"] for a in detail["allocations"]) == [300.0, 500.0]
    session = await get_open_session(db, company_id, pos)
    assert await get_current_expected_cash_balance(db, company_id, pos, session) == 200.0  # 1000 - 800
    docs = await _by_doc(db, company_id, supplier_id)
    assert (docs["FT A/1"]["payment_status"], docs["FT A/1"]["amount_due"], docs["FT A/1"]["overdue"]) == ("PARCIAL", 640.0, True)
    assert (docs["FT A/2"]["amount_paid"], docs["FT A/2"]["amount_due"]) == (300.0, 726.0)

    with pytest.raises(PurchaseInvoiceError, match="Anule primeiro o pagamento"):
        await cancel_purchase_invoice(db, company_id, ft1, user.id, "Erro")

    statement = await supplier_statement(db, company_id, supplier_id)
    assert [l["description"] for l in statement["lines"]][-1].startswith("Pagamento (Numerário) - rec 12")
    assert statement["closing_balance"] == 1366.0  # 1140 + 1140 + 1140 - 1140 (FR paid) - 114 (NC) - 800

    await cancel_supplier_payment(db, company_id, payment_id, user, "Valor errado")
    assert (await get_supplier_payment(db, company_id, payment_id))["status"] == "ANULADO"
    session = await get_open_session(db, company_id, pos)
    assert await get_current_expected_cash_balance(db, company_id, pos, session) == 1000.0  # the cash is back
    assert (await supplier_balances(db, company_id))[supplier_id] == 2166.0
    with pytest.raises(SupplierPaymentError, match="já está anulado"):
        await cancel_supplier_payment(db, company_id, payment_id, user, "outra vez")
    assert len((await db.execute(select(CashMovement).where(CashMovement.company_id == company_id))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_the_statement_opens_with_the_balance_before_the_period(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, supplier_id, ft1, *_ = await _setup(db, ctx)
    await create_supplier_payment(db, company_id, ctx["gestor"], supplier_id, [{"purchase_invoice_id": ft1, "amount": 140}],
                                  ctx["pm_mb"].id, reference_text="TRF 99")
    tomorrow = date.today() + timedelta(days=1)
    later = await supplier_statement(db, company_id, supplier_id, date_from=tomorrow)
    assert (later["opening_balance"], later["lines"], later["closing_balance"]) == (2026.0, [], 2026.0)
    pdf_data = await get_purchase_invoice(db, company_id, ft1)
    assert (pdf_data["amount_paid"], pdf_data["amount_due"]) == (140.0, 1000.0)

    from app.services.cash_report_service import _company_dict
    from app.utils.supplier_payment_pdf import generate_supplier_payment_pdf, generate_supplier_statement_pdf
    from app.services.supplier_payment_service import list_supplier_payments
    payment = (await list_supplier_payments(db, company_id, supplier_id))[0]
    company = _company_dict(ctx["company"])
    assert generate_supplier_payment_pdf(await get_supplier_payment(db, company_id, payment["id"]), company).startswith(b"%PDF")
    assert generate_supplier_statement_pdf(await supplier_statement(db, company_id, supplier_id), company).startswith(b"%PDF")
