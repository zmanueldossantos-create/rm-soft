"""
A credit note can put the credited goods back into stock, but only when asked to (restock=True): the return goes to
the warehouse the sale took the goods from, is recorded as a RECEPCAO referencing the credit note, and is refused when
there is nothing to return. The caps are cumulative: what earlier credit notes already credited counts against the invoice.
"""
import pytest
from sqlalchemy import func, select

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.models.stock_movement import MovementType, StockMovement
from app.services.invoice_service import (
    CreditNoteExceedsOriginalError, EmptyInvoiceError, create_credit_note, create_invoice,
)


def _ids(ctx):
    return {
        "company": ctx["company"].id, "activity": ctx["activity"].id,
        "warehouse": ctx["activity_warehouse"].id, "vat": ctx["vat_nor"].id,
    }


async def _sold_product(db, ids, quantity=4, stock=10):
    product = Product(company_id=ids["company"], code="PRD-NC", name="Produto NC", vat_id=ids["vat"], price=1000.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    product_id = product.id
    db.add(Stock(company_id=ids["company"], product_id=product_id, warehouse_id=ids["warehouse"], quantity=stock))
    await db.commit()
    invoice = await create_invoice(
        db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
        lines_input=[{"product_id": product_id, "quantity": quantity}],
    )
    return product_id, invoice.id


async def _stock(db, ids, product_id):
    return float((await db.execute(
        select(Stock.quantity).where(Stock.product_id == product_id, Stock.warehouse_id == ids["warehouse"])
    )).scalar_one())


async def _credit(db, ids, invoice_id, quantity, restock=False):
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()
    return await create_credit_note(
        db, ids["company"], ids["activity"], reference_invoice_id=invoice_id,
        credit_note_reason="ANL", credit_note_cause="Teste",
        lines_input=[{"invoice_line_id": line_id, "quantity": quantity}], restock=restock,
    )


@pytest.mark.asyncio
async def test_credit_note_does_not_touch_stock_unless_asked(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)
    assert await _stock(db, ids, product_id) == 6.0  # 10 - 4 sold

    await _credit(db, ids, invoice_id, 1)
    assert await _stock(db, ids, product_id) == 6.0
    returns = (await db.execute(select(func.count(StockMovement.id)).where(
        StockMovement.product_id == product_id, StockMovement.movement_type == MovementType.RECEPCAO
    ))).scalar_one()
    assert returns == 0


@pytest.mark.asyncio
async def test_restock_returns_the_goods_to_the_sale_warehouse(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)

    note = await _credit(db, ids, invoice_id, 1, restock=True)
    note_reference = "NC " + str(note.series) + "/" + str(note.number)

    assert await _stock(db, ids, product_id) == 7.0
    movement = (await db.execute(select(StockMovement).where(
        StockMovement.product_id == product_id, StockMovement.movement_type == MovementType.RECEPCAO
    ))).scalars().one()
    assert float(movement.quantity) == 1.0
    assert movement.warehouse_id == ids["warehouse"]
    assert movement.reference == note_reference


@pytest.mark.asyncio
async def test_restock_is_refused_when_no_credited_line_holds_stock(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    service = Service(company_id=ids["company"], code="SRV-NC", name="Servico NC", price=1000.0, vat_id=ids["vat"])
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id
    invoice = await create_invoice(
        db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}],
    )
    invoice_id = invoice.id

    with pytest.raises(EmptyInvoiceError):
        await _credit(db, ids, invoice_id, 1, restock=True)
    notes = (await db.execute(select(func.count(Invoice.id)).where(Invoice.reference_invoice_id == invoice_id))).scalar_one()
    assert notes == 0  # refused before anything was created


@pytest.mark.asyncio
async def test_credit_caps_are_cumulative(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)  # 4 units, 1140 each with VAT

    await _credit(db, ids, invoice_id, 3)
    with pytest.raises(CreditNoteExceedsOriginalError) as excinfo:
        await _credit(db, ids, invoice_id, 2)
    assert "por creditar" in str(excinfo.value)

    last = await _credit(db, ids, invoice_id, 1)  # exactly what is left
    assert float(last.total) == 1140.0


@pytest.mark.asyncio
async def test_first_credit_over_the_original_keeps_its_message(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)

    with pytest.raises(CreditNoteExceedsOriginalError) as excinfo:
        await _credit(db, ids, invoice_id, 5)
    assert "excede a quantidade original" in str(excinfo.value)


async def _status(db, invoice_id):
    value = (await db.execute(select(Invoice.document_status).where(Invoice.id == invoice_id))).scalar_one()
    return getattr(value, "value", value)


async def _credit_rtf(db, ids, invoice_id, quantity):
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()
    return await create_credit_note(
        db, ids["company"], ids["activity"], reference_invoice_id=invoice_id,
        credit_note_reason="RTF", credit_note_cause="Teste",
        lines_input=[{"invoice_line_id": line_id, "quantity": quantity}],
    )


@pytest.mark.asyncio
async def test_invoice_fully_credited_by_several_partial_notes_is_no_longer_partial(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)  # 4 units

    await _credit_rtf(db, ids, invoice_id, 3)
    assert await _status(db, invoice_id) == "RECTIFICADO_PARCIAL"

    await _credit_rtf(db, ids, invoice_id, 1)  # the remainder: nothing left to credit
    assert await _status(db, invoice_id) == "RECTIFICADO"


@pytest.mark.asyncio
async def test_restock_follows_the_real_sale_warehouse_not_the_current_activity_one(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)  # sold from the activity warehouse: 10 - 4 = 6

    # The activity is moved to another warehouse after the sale.
    activity = company_with_essentials["activity"]
    activity.warehouse_id = company_with_essentials["central_warehouse"].id
    await db.commit()

    await _credit(db, ids, invoice_id, 1, restock=True)

    assert await _stock(db, ids, product_id) == 7.0  # back where it came from
    in_new_warehouse = (await db.execute(select(func.count(Stock.id)).where(
        Stock.product_id == product_id, Stock.warehouse_id == company_with_essentials["central_warehouse"].id
    ))).scalar_one()
    assert in_new_warehouse == 0


async def _open_period_for(db, company_id, day):
    """Opens (in the test database) the fiscal year and period covering `day` when they do not exist yet."""
    from app.models.fiscal_period import FiscalPeriod
    from app.models.fiscal_year import FiscalYear
    year = (await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.year == day.year)
    )).scalar_one_or_none()
    if year is None:
        year = FiscalYear(company_id=company_id, year=day.year, status="ABERTO")
        db.add(year)
        await db.commit()
        await db.refresh(year)
    period = (await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == year.id, FiscalPeriod.month == day.month)
    )).scalar_one_or_none()
    if period is None:
        db.add(FiscalPeriod(company_id=company_id, fiscal_year_id=year.id, month=day.month, status="ABERTO"))
        await db.commit()


@pytest.mark.asyncio
async def test_credit_note_cannot_be_dated_before_its_invoice(db, company_with_essentials):
    from datetime import date, timedelta
    yesterday = date.today() - timedelta(days=1)
    # On the 1st of a month (or of January) yesterday lies in another period: open it, so the test always checks the rule.
    await _open_period_for(db, company_with_essentials["company"].id, yesterday)
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)  # issued today
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()

    with pytest.raises(EmptyInvoiceError) as excinfo:
        await create_credit_note(
            db, ids["company"], ids["activity"], reference_invoice_id=invoice_id,
            credit_note_reason="RTF", credit_note_cause="Teste",
            lines_input=[{"invoice_line_id": line_id, "quantity": 1}],
            business_date=yesterday,
        )
    assert "data anterior" in str(excinfo.value)
    notes = (await db.execute(select(func.count(Invoice.id)).where(Invoice.reference_invoice_id == invoice_id))).scalar_one()
    assert notes == 0


from app.models.payment import Payment  # noqa: E402
from app.services.cash_session_service import get_current_expected_cash_balance, open_session  # noqa: E402
from app.services.invoice_service import RefundNotAllowedError  # noqa: E402


async def _sold_fr(db, ctx, ids, quantity=2, in_session=True):
    """A Fatura/Recibo paid in cash (Numerario by default), optionally inside an open session of the test POS."""
    product = Product(company_id=ids["company"], code="PRD-RF", name="Produto RF", vat_id=ids["vat"], price=1000.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    product_id = product.id
    db.add(Stock(company_id=ids["company"], product_id=product_id, warehouse_id=ids["warehouse"], quantity=10))
    await db.commit()
    session = await open_session(db, ids["company"], ctx["pos"].id, ctx["gestor"], opening_amount=0)
    invoice = await create_invoice(
        db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=[{"product_id": product_id, "quantity": quantity}],
        cash_session_id=session.id if in_session else None,
    )
    return session, invoice.id


async def _credit_with_refund(db, ids, invoice_id, quantity, refunds, pos_id=None):
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()
    return await create_credit_note(
        db, ids["company"], ids["activity"], reference_invoice_id=invoice_id,
        credit_note_reason="RTF", credit_note_cause="Teste",
        lines_input=[{"invoice_line_id": line_id, "quantity": quantity}],
        refunds=refunds, refund_pos_id=pos_id,
    )


async def _notes_count(db, invoice_id):
    return (await db.execute(select(func.count(Invoice.id)).where(Invoice.reference_invoice_id == invoice_id))).scalar_one()


@pytest.mark.asyncio
async def test_cash_refund_leaves_the_chosen_cash_point(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    session, invoice_id = await _sold_fr(db, ctx, ids)  # 2 x 1140 = 2280 in cash
    assert await get_current_expected_cash_balance(db, ids["company"], ctx["pos"].id, session) == 2280.0

    note = await _credit_with_refund(
        db, ids, invoice_id, 1, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 1140}], ctx["pos"].id,
    )

    amounts = (await db.execute(select(Payment.amount).where(Payment.invoice_id == note.id))).scalars().all()
    assert [float(a) for a in amounts] == [-1140.0]
    assert note.cash_session_id == session.id
    assert await get_current_expected_cash_balance(db, ids["company"], ctx["pos"].id, session) == 1140.0


@pytest.mark.asyncio
async def test_refund_above_the_overpayment_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    session, invoice_id = await _sold_fr(db, ctx, ids)

    with pytest.raises(RefundNotAllowedError) as excinfo:
        await _credit_with_refund(
            db, ids, invoice_id, 1, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 2280}], ctx["pos"].id,
        )
    assert "reembolsavel" in str(excinfo.value)
    assert await _notes_count(db, invoice_id) == 0


@pytest.mark.asyncio
async def test_cash_refund_without_a_chosen_cash_point_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    session, invoice_id = await _sold_fr(db, ctx, ids)

    with pytest.raises(RefundNotAllowedError) as excinfo:
        await _credit_with_refund(db, ids, invoice_id, 1, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 1140}])
    assert "Selecione a caixa" in str(excinfo.value)
    assert await _notes_count(db, invoice_id) == 0


@pytest.mark.asyncio
async def test_nothing_is_refundable_on_an_unpaid_fatura(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    product_id, invoice_id = await _sold_product(db, ids)  # FACTURA, nothing collected

    with pytest.raises(RefundNotAllowedError) as excinfo:
        await _credit_with_refund(db, ids, invoice_id, 1, [{"payment_method_id": ctx["pm_mb"].id, "amount": 100}])
    assert "(0.00)" in str(excinfo.value)


@pytest.mark.asyncio
async def test_cash_refund_above_the_cash_in_the_drawer_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    session, invoice_id = await _sold_fr(db, ctx, ids, in_session=False)  # paid, but not into this drawer: it holds 0

    with pytest.raises(RefundNotAllowedError) as excinfo:
        await _credit_with_refund(
            db, ids, invoice_id, 1, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 1140}], ctx["pos"].id,
        )
    assert "insuficiente" in str(excinfo.value)
    assert await _notes_count(db, invoice_id) == 0


@pytest.mark.asyncio
async def test_credit_note_without_refund_belongs_to_no_session(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    session, invoice_id = await _sold_fr(db, ctx, ids)

    note = await _credit_with_refund(db, ids, invoice_id, 1, [])

    assert note.cash_session_id is None
    payments = (await db.execute(select(func.count(Payment.id)).where(Payment.invoice_id == note.id))).scalar_one()
    assert payments == 0
    assert await get_current_expected_cash_balance(db, ids["company"], ctx["pos"].id, session) == 2280.0


from app.services.daily_report_service import get_daily_report  # noqa: E402


@pytest.mark.asyncio
async def test_daily_journal_shows_the_refund_as_an_outgoing_line(db, company_with_essentials):
    from datetime import date
    ctx = company_with_essentials
    ids = _ids(ctx)
    session, invoice_id = await _sold_fr(db, ctx, ids)
    await _credit_with_refund(
        db, ids, invoice_id, 1, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 1140}], ctx["pos"].id,
    )

    entries = await get_daily_report(
        db, company_id=ids["company"], pos_id=ctx["pos"].id, date_from=date.today(), date_to=date.today(),
    )
    lines = sorted((e["direction"], e["amount"]) for e in entries)
    assert lines == [("entrada", 2280.0), ("saida", 1140.0)]
    refund = next(e for e in entries if e["direction"] == "saida")
    assert refund["description"].endswith("Reembolso")


from app.services.invoice_service import get_credit_note_info  # noqa: E402


@pytest.mark.asyncio
async def test_refund_info_gives_the_figures_and_the_open_cash_points(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    session, invoice_id = await _sold_fr(db, ctx, ids)

    info = await get_credit_note_info(db, ids["company"], invoice_id)
    assert (info["collected"], info["refunded"], info["due"]) == (2280.0, 0.0, 2280.0)
    assert info["cash_points"] == [{"pos_id": str(ctx["pos"].id), "name": ctx["pos"].name, "available_cash": 2280.0}]

    await _credit_with_refund(
        db, ids, invoice_id, 1, [{"payment_method_id": ctx["pm_numerario"].id, "amount": 1140}], ctx["pos"].id,
    )
    info = await get_credit_note_info(db, ids["company"], invoice_id)
    assert (info["collected"], info["refunded"], info["due"]) == (2280.0, 1140.0, 1140.0)
    assert info["cash_points"][0]["available_cash"] == 1140.0


@pytest.mark.asyncio
async def test_credit_note_info_gives_what_is_left_to_credit_per_line(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)  # 4 units
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()
    assert (await get_credit_note_info(db, ids['company'], invoice_id))['remaining_by_line'] == {str(line_id): 4.0}

    await _credit_rtf(db, ids, invoice_id, 3)
    assert (await get_credit_note_info(db, ids['company'], invoice_id))['remaining_by_line'] == {str(line_id): 1.0}


from app.services.invoice_service import ReceiptExceedsPendingError, attach_amount_due, create_receipt  # noqa: E402


async def _due(db, invoice_id):
    invoice = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one()
    await attach_amount_due(db, [invoice])
    return invoice.amount_due, invoice.amount_credited


@pytest.mark.asyncio
async def test_amount_due_of_a_fatura_deducts_its_credit_notes_and_caps_the_receipt(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)  # FACTURA 4 x 1140 = 4560, nothing paid
    await _credit_rtf(db, ids, invoice_id, 1)
    assert await _due(db, invoice_id) == (3420.0, 1140.0)

    with pytest.raises(ReceiptExceedsPendingError):
        await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=4560.0)
    await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=3420.0)
    assert await _due(db, invoice_id) == (0.0, 1140.0)


@pytest.mark.asyncio
async def test_a_fatura_fully_credited_owes_nothing(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)
    await _credit_rtf(db, ids, invoice_id, 4)
    assert await _due(db, invoice_id) == (0.0, 4560.0)


@pytest.mark.asyncio
async def test_amount_due_counts_the_deposit_and_the_credit_notes(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product = Product(company_id=ids["company"], code="PRD-DP", name="Produto DP", vat_id=ids["vat"], price=1000.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    product_id = product.id
    db.add(Stock(company_id=ids["company"], product_id=product_id, warehouse_id=ids["warehouse"], quantity=10))
    await db.commit()
    invoice = await create_invoice(
        db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
        lines_input=[{"product_id": product_id, "quantity": 4}], amount_received=1000.0,
    )
    invoice_id = invoice.id
    await _credit_rtf(db, ids, invoice_id, 1)
    assert await _due(db, invoice_id) == (2420.0, 1140.0)


from app.services.pos_documents_service import list_pos_documents  # noqa: E402


@pytest.mark.asyncio
async def test_caixa_stops_listing_a_fatura_once_credit_notes_leave_nothing_owed(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    product_id, invoice_id = await _sold_product(db, ids)  # FACTURA issued outside any session, 4560 owed

    listed = {inv.id: inv for inv in await list_pos_documents(db, ids["company"], ctx["pos"].id)}
    assert listed[invoice_id].amount_due == 4560.0

    await _credit_rtf(db, ids, invoice_id, 4)
    listed = {inv.id for inv in await list_pos_documents(db, ids["company"], ctx["pos"].id)}
    assert invoice_id not in listed


from app.services.invoice_service import CashPointRequiredError  # noqa: E402


async def _product_in_stock(db, ids, code):
    product = Product(company_id=ids["company"], code=code, name="Produto " + code, vat_id=ids["vat"], price=1000.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    product_id = product.id
    db.add(Stock(company_id=ids["company"], product_id=product_id, warehouse_id=ids["warehouse"], quantity=10))
    await db.commit()
    return product_id


async def _fr_from_invoicing_screen(db, ids, product_id, cash_pos_id=None):
    return await create_invoice(
        db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=[{"product_id": product_id, "quantity": 1}], cash_pos_id=cash_pos_id, require_cash_point=True,
    )


@pytest.mark.asyncio
async def test_cash_sale_from_invoicing_needs_a_chosen_cash_point(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id = await _product_in_stock(db, ids, "PRD-CP1")
    with pytest.raises(CashPointRequiredError) as excinfo:
        await _fr_from_invoicing_screen(db, ids, product_id)
    assert "Selecione a caixa" in str(excinfo.value)
    await db.rollback()
    count = (await db.execute(select(func.count(Invoice.id)).where(Invoice.company_id == ids["company"]))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_cash_sale_from_invoicing_enters_the_chosen_cash_point(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    product_id = await _product_in_stock(db, ids, "PRD-CP2")
    session = await open_session(db, ids["company"], ctx["pos"].id, ctx["gestor"], opening_amount=0)
    invoice = await _fr_from_invoicing_screen(db, ids, product_id, ctx["pos"].id)
    assert invoice.cash_session_id == session.id
    assert await get_current_expected_cash_balance(db, ids["company"], ctx["pos"].id, session) == 1140.0


@pytest.mark.asyncio
async def test_a_closed_cash_point_cannot_take_cash(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    product_id = await _product_in_stock(db, ids, "PRD-CP3")  # no session opened on the POS
    with pytest.raises(CashPointRequiredError) as excinfo:
        await _fr_from_invoicing_screen(db, ids, product_id, ctx["pos"].id)
    assert "nao tem sessao aberta" in str(excinfo.value)


@pytest.mark.asyncio
async def test_receipt_in_cash_needs_a_cash_point_and_other_methods_do_not(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    product_id, invoice_id = await _sold_product(db, ids)  # FACTURA 4560, nothing paid

    with pytest.raises(CashPointRequiredError):
        await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=1000.0,
                             require_cash_point=True)
    await db.rollback()
    # A rollback expires every loaded object: reload the ones read below (no lazy load in async).
    for obj in (ctx["pm_mb"], ctx["pos"], ctx["gestor"]):
        await db.refresh(obj)

    by_card = await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=1000.0,
                                   payment_method_id=ctx["pm_mb"].id, require_cash_point=True)
    assert by_card.cash_session_id is None

    session = await open_session(db, ids["company"], ctx["pos"].id, ctx["gestor"], opening_amount=0)
    in_cash = await create_receipt(db, ids["company"], ids["activity"], reference_invoice_id=invoice_id, amount=1000.0,
                                   cash_pos_id=ctx["pos"].id, require_cash_point=True)
    assert in_cash.cash_session_id == session.id
    assert await get_current_expected_cash_balance(db, ids["company"], ctx["pos"].id, session) == 1000.0


@pytest.mark.asyncio
async def test_mixed_invoice_credit_note_returns_only_the_products_to_stock(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id = await _product_in_stock(db, ids, "PRD-MX")
    service = Service(company_id=ids["company"], code="SRV-MX", name="Servico MX", price=500.0, vat_id=ids["vat"])
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id
    invoice = await create_invoice(
        db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
        lines_input=[{"product_id": product_id, "quantity": 2}, {"service_id": service_id, "quantity": 1}],
    )
    invoice_id = invoice.id
    assert await _stock(db, ids, product_id) == 8.0

    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().all()
    await create_credit_note(
        db, ids["company"], ids["activity"], reference_invoice_id=invoice_id,
        credit_note_reason="ANL", credit_note_cause="Teste misto",
        lines_input=[{"invoice_line_id": l.id, "quantity": float(l.quantity)} for l in lines], restock=True,
    )

    assert await _stock(db, ids, product_id) == 10.0
    returns = (await db.execute(select(StockMovement).where(
        StockMovement.company_id == ids["company"], StockMovement.movement_type == MovementType.RECEPCAO,
    ))).scalars().all()
    assert [(r.product_id, float(r.quantity)) for r in returns] == [(product_id, 2.0)]
    assert await _status(db, invoice_id) == "ANULADO"


from app.models.payment_term import PaymentTerm  # noqa: E402


async def _pronto_term(db):
    term = PaymentTerm(name="Pronto pagamento", fixed_days=False, days=0, months_fixed_day=0, discount=0, is_active=True)
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return term.id


@pytest.mark.asyncio
async def test_a_document_paid_on_issue_is_pronto_pagamento_due_on_its_date(db, company_with_essentials):
    ctx = company_with_essentials
    ids = _ids(ctx)
    pronto_id = await _pronto_term(db)
    product_id = await _product_in_stock(db, ids, "PRD-PT1")
    await open_session(db, ids["company"], ctx["pos"].id, ctx["gestor"], opening_amount=0)
    invoice = await _fr_from_invoicing_screen(db, ids, product_id, ctx["pos"].id)
    assert invoice.payment_term_id == pronto_id
    assert invoice.due_date == invoice.business_date


@pytest.mark.asyncio
async def test_a_fatura_from_invoicing_needs_its_mandatory_payment_term(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id = await _product_in_stock(db, ids, "PRD-PT2")
    from app.services.document_rules import get_document_rules
    assert (await get_document_rules(db, "FT")).code, "the FT document rules are missing from the test database"
    from app.models.document_type import DocumentType
    ft = (await db.execute(select(DocumentType).where(DocumentType.code == "FT"))).scalar_one()
    ft.requires_payment_term = True
    await db.commit()
    with pytest.raises(EmptyInvoiceError) as excinfo:
        await create_invoice(
            db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
            lines_input=[{"product_id": product_id, "quantity": 1}], enforce_document_rules=True,
        )
    assert "condicao de pagamento" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_receipt_on_an_unknown_bank_account_is_refused(db, company_with_essentials):
    import uuid as _uuid
    ctx = company_with_essentials
    ids = _ids(ctx)
    product_id, invoice_id = await _sold_product(db, ids)
    with pytest.raises(EmptyInvoiceError) as excinfo:
        await create_receipt(db, ids['company'], ids['activity'], reference_invoice_id=invoice_id, amount=100.0,
                             payment_method_id=ctx['pm_mb'].id, bank_account_id=_uuid.uuid4())
    assert 'Conta bancaria invalida' in str(excinfo.value)


from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog  # noqa: E402
from app.services.product_service import list_products  # noqa: E402


@pytest.mark.asyncio
async def test_listed_products_carry_their_unit_code(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    unit = UnitOfMeasureCatalog(code='CX', name='Caixa')
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    product_id = await _product_in_stock(db, ids, 'PRD-UN')
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    product.unit_of_measure_id = unit.id
    await db.commit()
    listed = {p.id: p for p in await list_products(db, ids['company'])}
    assert listed[product_id].unit_of_measure_code == 'CX'


from app.models.product_sale_unit import ProductSaleUnit  # noqa: E402
from app.services.invoice_service import ProductNotFoundError  # noqa: E402


async def _box_of(db, ids, product_id, code, factor=5, price=4500):
    unit = UnitOfMeasureCatalog(code=code, name="Caixa " + code)
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    sale_unit = ProductSaleUnit(company_id=ids["company"], product_id=product_id, unit_of_measure_id=unit.id, factor=factor, price=price)
    db.add(sale_unit)
    await db.commit()
    await db.refresh(sale_unit)
    return sale_unit


async def _ft_in_box(db, ids, product_id, sale_unit_id, quantity=1):
    return await create_invoice(
        db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
        lines_input=[{"product_id": product_id, "quantity": quantity, "sale_unit_id": sale_unit_id}],
    )


@pytest.mark.asyncio
async def test_a_box_sold_takes_its_factor_in_base_units_out_of_stock(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id = await _product_in_stock(db, ids, "PRD-SU1")
    before = await _stock(db, ids, product_id)
    assert before >= 5
    box = await _box_of(db, ids, product_id, "CX5")
    invoice = await _ft_in_box(db, ids, product_id, box.id)
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))).scalar_one()
    assert (float(line.quantity), float(line.unit_price), float(line.unit_factor)) == (1.0, 4500.0, 5.0)
    assert (line.sale_unit_id, line.unit_code_snapshot) == (box.id, "CX5")
    assert await _stock(db, ids, product_id) == before - 5


@pytest.mark.asyncio
async def test_a_credit_note_on_a_box_returns_its_base_units(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id = await _product_in_stock(db, ids, "PRD-SU2")
    before = await _stock(db, ids, product_id)
    box = await _box_of(db, ids, product_id, "CX6")
    invoice = await _ft_in_box(db, ids, product_id, box.id)
    credit_note = await _credit(db, ids, invoice.id, 1, restock=True)
    assert await _stock(db, ids, product_id) == before
    nc_line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == credit_note.id))).scalar_one()
    assert (float(nc_line.unit_factor), nc_line.unit_code_snapshot, nc_line.sale_unit_id) == (5.0, "CX6", box.id)


@pytest.mark.asyncio
async def test_the_sale_unit_of_another_product_is_refused(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id = await _product_in_stock(db, ids, "PRD-SU3")
    other_id = await _product_in_stock(db, ids, "PRD-SU4")
    other_box = await _box_of(db, ids, other_id, "CX7")
    with pytest.raises(ProductNotFoundError, match="Unidade ou embalagem invalida"):
        await _ft_in_box(db, ids, product_id, other_box.id)


@pytest.mark.asyncio
async def test_a_decimal_quantity_only_in_a_fractional_unit(db, company_with_essentials):
    ids = _ids(company_with_essentials)
    product_id = await _product_in_stock(db, ids, "PRD-KG")
    with pytest.raises(ProductNotFoundError, match="deve ser inteira"):
        await create_invoice(db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
                             lines_input=[{"product_id": product_id, "quantity": 1.5}])
    await db.rollback()
    kilo = UnitOfMeasureCatalog(code="KGT", name="Quilo teste", is_fractional=True)
    db.add(kilo)
    await db.commit()
    await db.refresh(kilo)
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    product.unit_of_measure_id = kilo.id
    await db.commit()
    before = await _stock(db, ids, product_id)
    await create_invoice(db, ids["company"], ids["activity"], customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"product_id": product_id, "quantity": 1.25}])
    assert await _stock(db, ids, product_id) == pytest.approx(before - 1.25)
