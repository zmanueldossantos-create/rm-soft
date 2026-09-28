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


@pytest.mark.asyncio
async def test_credit_note_cannot_be_dated_before_its_invoice(db, company_with_essentials):
    from datetime import date, timedelta
    if date.today().day == 1:
        pytest.skip("the day before would fall in another fiscal period")
    ids = _ids(company_with_essentials)
    product_id, invoice_id = await _sold_product(db, ids)  # issued today
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()

    with pytest.raises(EmptyInvoiceError) as excinfo:
        await create_credit_note(
            db, ids["company"], ids["activity"], reference_invoice_id=invoice_id,
            credit_note_reason="RTF", credit_note_cause="Teste",
            lines_input=[{"invoice_line_id": line_id, "quantity": 1}],
            business_date=date.today() - timedelta(days=1),
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
