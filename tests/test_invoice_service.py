"""
Tests for invoice_service.create_invoice - covers the two most critical
correctness properties: VAT is calculated correctly per line, and stock
is deducted from the SELLING ACTIVITY's own warehouse (not the central
one) - the exact bug class we hunted manually all session.
"""
import pytest
from datetime import date, timedelta
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.models.invoice import InvoiceType, DocumentLifecycleStatus
from app.models.customer import Customer, LegalPersonType
from app.models.withholding_tax import WithholdingTax
from app.services.invoice_service import create_invoice, create_credit_note, create_debit_note, create_receipt, create_pro_forma, convert_pro_forma_to_invoice, ProFormaAlreadyConvertedError, ReceiptExceedsPendingError, EmptyInvoiceError
from app.services.stock_service import receive_stock
from sqlalchemy import select


async def _make_product(db, company, vat, price=1000.0, code="PROD-001"):
    product = Product(
        company_id=company.id, code=code, name="Produto Teste",
        vat_id=vat.id, price=price, min_stock_threshold=0,
        product_type=ProductType.BEM,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def test_create_invoice_calculates_vat_correctly(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)  # 14% VAT
    # Stock must exist in the ACTIVITY's warehouse - create_invoice deducts
    # from there, never from the central warehouse (see other test below).
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 2}],
    )

    assert float(invoice.subtotal) == 2000.0
    assert float(invoice.vat_total) == 280.0  # 14% of 2000
    assert float(invoice.total) == 2280.0


async def test_create_invoice_deducts_stock_from_activity_warehouse_not_central(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"])

    # Stock only exists in the ACTIVITY's warehouse (simulating a completed transfer) -
    # the central warehouse has none. If create_invoice mistakenly deducted from
    # central, this would fail with InsufficientStockError.
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 3}],
    )

    result = await db.execute(
        select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id)
    )
    stock = result.scalar_one()
    assert float(stock.quantity) == 7  # 10 - 3


async def test_create_invoice_uses_document_series(db, company_with_essentials):
    """Series now comes from DocumentSeries (Company default: MANUAL + auto_series_year on),
    not Activity.series_code - see the integration decision. Format is {DocType}{Year}
    (SAF-T requires the code stay unique per document type - a bare year is not enough)."""
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"])
    await receive_stock(db, company.id, product.id, 5)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=5)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 1}],
    )

    from datetime import date as _date
    assert invoice.series == f"FT{_date.today().year}"
    assert invoice.number == 1


async def test_create_credit_note_full_marks_original_anulado(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 2}],
    )

    lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
    original_line = lines_result.scalars().first()

    credit_note = await create_credit_note(
        db, company.id, setup["activity"].id, reference_invoice_id=invoice.id,
        credit_note_reason="ANL", credit_note_cause="Cliente desistiu da compra",
        lines_input=[{"invoice_line_id": original_line.id, "quantity": 2}],
    )

    assert credit_note.invoice_type == InvoiceType.NOTA_CREDITO
    assert credit_note.reference_invoice_id == invoice.id
    assert float(credit_note.total) == float(invoice.total)
    assert credit_note.series.startswith("NC")

    await db.refresh(invoice)
    assert invoice.document_status == DocumentLifecycleStatus.ANULADO


async def test_create_credit_note_partial_marks_original_rectificado_parcial(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 2}],
    )

    lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
    original_line = lines_result.scalars().first()

    credit_note = await create_credit_note(
        db, company.id, setup["activity"].id, reference_invoice_id=invoice.id,
        credit_note_reason="RTF", credit_note_cause="Devolucao parcial de 1 unidade",
        lines_input=[{"invoice_line_id": original_line.id, "quantity": 1}],
    )

    assert float(credit_note.total) == float(invoice.total) / 2

    await db.refresh(invoice)
    assert invoice.document_status == DocumentLifecycleStatus.RECTIFICADO_PARCIAL


async def test_create_invoice_with_service_line_skips_stock_and_calculates_vat(db, company_with_essentials):
    """A Service line (separate table from Product) must never touch stock, and its own
    VAT rate/price are used - see the Phase C split-model decision."""
    setup = company_with_essentials
    company = setup["company"]
    service = Service(
        company_id=company.id, code="SRV-TEST", name="Servico de Teste",
        price=500.0, vat_id=setup["vat_red"].id,
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"service_id": service.id, "quantity": 2}],
    )

    assert float(invoice.subtotal) == 1000.0
    assert float(invoice.vat_total) == 50.0  # 5% Taxa reduzida
    assert float(invoice.total) == 1050.0

    lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
    line = lines_result.scalars().first()
    assert line.service_id == service.id
    assert line.product_id is None


async def test_create_invoice_applies_line_and_global_discounts(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)  # 14% VAT
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA",
        lines_input=[{"product_id": product.id, "quantity": 1, "discount_percent": 10}],
        discount_global_percent=10,
    )

    # Line: 1000 gross, 10% line discount = 900 subtotal, 14% VAT on 900 = 126, line total 1026
    assert float(invoice.subtotal) == 900.0
    assert float(invoice.vat_total) == 126.0
    # Global: 10% of (900+126)=1026 -> 102.6 discount -> 923.4 grand total
    assert float(invoice.total) == 923.4
    assert float(invoice.discount_global_percent) == 10.0


async def test_create_invoice_rejects_future_date_when_not_allowed(db, company_with_essentials):
    """Company.allows_future_sale_date defaults to False - a future business_date must be rejected."""
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"])
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    future_date = date.today() + timedelta(days=5)
    with pytest.raises(EmptyInvoiceError):
        await create_invoice(
            db, company.id, setup["activity"].id, customer_id=None,
            invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 1}],
            business_date=future_date,
        )


async def test_create_invoice_applies_retention_for_juridica_customer_service(db, company_with_essentials):
    """AGT rule (Ulemo 8.8): retention applies only to Service lines whose article has a
    withholding_tax_id set, and only when the customer is pessoa coletiva (JURIDICA)."""
    setup = company_with_essentials
    company = setup["company"]

    wh_tax = WithholdingTax(name="Retencao IRPC 6.5%", rate=6.5)
    db.add(wh_tax)
    await db.flush()

    customer = Customer(company_id=company.id, name="Empresa Cliente Lda", nif="5001234567", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.flush()

    service = Service(company_id=company.id, code="SRV-RET", name="Servico Sujeito a Retencao", price=1000.0, vat_id=setup["vat_nor"].id, withholding_tax_id=wh_tax.id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    await db.refresh(customer)

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=customer.id,
        invoice_type="FACTURA", lines_input=[{"service_id": service.id, "quantity": 1}],
    )

    assert float(invoice.retention_total) == 65.0  # 6.5% of 1000


async def test_create_invoice_no_retention_for_singular_customer(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]

    wh_tax = WithholdingTax(name="Retencao IRPC 6.5%", rate=6.5)
    db.add(wh_tax)
    await db.flush()

    customer = Customer(company_id=company.id, name="Cliente Individual", nif="003456789LA042", legal_person_type=LegalPersonType.FISICA)
    db.add(customer)
    await db.flush()

    service = Service(company_id=company.id, code="SRV-RET2", name="Servico Sujeito a Retencao", price=1000.0, vat_id=setup["vat_nor"].id, withholding_tax_id=wh_tax.id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    await db.refresh(customer)

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=customer.id,
        invoice_type="FACTURA", lines_input=[{"service_id": service.id, "quantity": 1}],
    )

    assert float(invoice.retention_total) == 0.0


async def test_create_debit_note_references_original_and_has_free_lines(db, company_with_essentials):
    """ND references an original invoice but its lines are free (not limited to the
    original's own lines/quantities) - it charges an additional amount."""
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 1}],
    )

    another_product = await _make_product(db, company, setup["vat_ise"], price=500.0, code="PROD-002")

    debit_note = await create_debit_note(
        db, company.id, setup["activity"].id, reference_invoice_id=invoice.id, customer_id=None,
        lines_input=[{"product_id": another_product.id, "quantity": 2}],
        observations="Item esquecido na fatura original",
    )

    assert debit_note.invoice_type == InvoiceType.NOTA_DEBITO
    assert debit_note.reference_invoice_id == invoice.id
    assert float(debit_note.subtotal) == 1000.0  # 2 x 500, unrelated to the original's own value
    assert debit_note.series.startswith("ND")

    # ND must NOT alter the original invoice's fiscal lifecycle - it only adds a new charge.
    await db.refresh(invoice)
    assert invoice.document_status == DocumentLifecycleStatus.EMITIDO


async def test_create_receipt_accumulates_payment_on_reference_invoice(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 1}],
    )
    # invoice.total = 1140.00 (1000 + 14% VAT)

    receipt = await create_receipt(
        db, company.id, setup["activity"].id, reference_invoice_id=invoice.id, amount=500.0,
    )

    assert receipt.invoice_type == InvoiceType.RECIBO
    assert receipt.reference_invoice_id == invoice.id
    assert float(receipt.total) == 500.0
    assert receipt.series.startswith("RC")

    await db.refresh(invoice)
    assert float(invoice.amount_received) == 500.0


async def test_create_receipt_rejects_amount_exceeding_pending(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], price=1000.0)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"product_id": product.id, "quantity": 1}],
    )
    # invoice.total = 1000.00 (isento)

    with pytest.raises(ReceiptExceedsPendingError):
        await create_receipt(
            db, company.id, setup["activity"].id, reference_invoice_id=invoice.id, amount=1500.0,
        )


async def test_create_pro_forma_does_not_deduct_stock_or_require_agt_submission(db, company_with_essentials):
    """FP is non-fiscal: it must not touch stock, and (unlike FT/FR/NC/ND/RC) it is never
    handed to the AGT submission worker."""
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    pro_forma = await create_pro_forma(
        db, company.id, setup["activity"].id, customer_id=None,
        lines_input=[{"product_id": product.id, "quantity": 2}],
    )

    assert pro_forma.invoice_type == InvoiceType.PRO_FORMA
    assert float(pro_forma.total) == 2280.0  # 2 x 1000 + 14% VAT
    assert pro_forma.series.startswith("FP")

    # Stock must be untouched - no sale has actually happened yet.
    stock_result = await db.execute(select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id))
    stock_row = stock_result.scalar_one()
    assert float(stock_row.quantity) == 10.0


async def test_convert_pro_forma_to_invoice_deducts_stock_and_is_single_use(db, company_with_essentials):
    """Converting replays the FP's lines through the real create_invoice flow (stock IS
    deducted this time), and a second conversion attempt must be rejected."""
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_nor"], price=1000.0)
    activity_stock = Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=10)
    db.add(activity_stock)
    await db.commit()

    pro_forma = await create_pro_forma(
        db, company.id, setup["activity"].id, customer_id=None,
        lines_input=[{"product_id": product.id, "quantity": 3}],
    )

    invoice = await convert_pro_forma_to_invoice(
        db, company.id, pro_forma_id=pro_forma.id, target_invoice_type="FACTURA",
    )

    assert invoice.invoice_type == InvoiceType.FACTURA
    assert float(invoice.total) == float(pro_forma.total)
    assert invoice.document_reference == f"FP {pro_forma.series}/{pro_forma.number}"

    await db.refresh(pro_forma)
    assert pro_forma.converted_to_invoice_id == invoice.id

    # Unlike the pro-forma itself, the real invoice DID deduct stock.
    stock_result = await db.execute(select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id))
    stock_row = stock_result.scalar_one()
    assert float(stock_row.quantity) == 7.0

    with pytest.raises(ProFormaAlreadyConvertedError):
        await convert_pro_forma_to_invoice(
            db, company.id, pro_forma_id=pro_forma.id, target_invoice_type="FACTURA",
        )
