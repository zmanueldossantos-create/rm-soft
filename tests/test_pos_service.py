"""
Tests for pos_service.checkout - covers the split-payment scenario
(e.g. 4000 Kz numerario + 6000 Kz Multicaixa Express for a 10000 Kz sale)
and the requirement that a sale is blocked without an open cash session.
"""
import pytest

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.payment import Payment
from app.services.cash_session_service import open_session
from app.services.pos_service import checkout, NoOpenSessionError
from app.services.invoice_service import PaymentAmountMismatchError
from sqlalchemy import select


async def _make_product(db, company, vat, price=10000.0):
    product = Product(
        company_id=company.id, code="POS-001", name="Produto POS",
        vat_id=vat.id, price=price, min_stock_threshold=0, product_type=ProductType.BEM,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def test_checkout_records_split_payment_correctly(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], price=10000.0)
    db.add(Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=5))
    await db.commit()

    await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=0)

    invoice = await checkout(
        db, company.id, setup["pos"].id, setup["gestor"], customer_id=None,
        lines_input=[{"product_id": product.id, "quantity": 1}],
        payments=[
            {"payment_method_id": setup["pm_numerario"].id, "amount": 4000.0},
            {"payment_method_id": setup["pm_mb"].id, "amount": 6000.0},
        ],
    )

    assert float(invoice.total) == 10000.0

    result = await db.execute(select(Payment).where(Payment.invoice_id == invoice.id))
    payments = {p.payment_method_id: float(p.amount) for p in result.scalars().all()}
    assert payments == {setup["pm_numerario"].id: 4000.0, setup["pm_mb"].id: 6000.0}


async def test_checkout_rejects_mismatched_payment_total(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], price=10000.0)
    db.add(Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=5))
    await db.commit()

    await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=0)

    with pytest.raises(PaymentAmountMismatchError):
        await checkout(
            db, company.id, setup["pos"].id, setup["gestor"], customer_id=None,
            lines_input=[{"product_id": product.id, "quantity": 1}],
            payments=[{"payment_method_id": setup["pm_numerario"].id, "amount": 5000.0}],  # short by 5000
        )


async def test_checkout_blocks_sale_without_open_session(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], price=10000.0)
    db.add(Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=5))
    await db.commit()

    # No open_session() call here - the register was never opened.
    with pytest.raises(NoOpenSessionError):
        await checkout(
            db, company.id, setup["pos"].id, setup["gestor"], customer_id=None,
            lines_input=[{"product_id": product.id, "quantity": 1}],
            payments=[{"payment_method_id": setup["pm_numerario"].id, "amount": 10000.0}],
        )


async def test_checkout_links_invoice_to_session(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], price=10000.0)
    db.add(Stock(company_id=company.id, product_id=product.id, warehouse_id=setup["activity_warehouse"].id, quantity=5))
    await db.commit()

    session = await open_session(db, company.id, setup["pos"].id, setup["gestor"], opening_amount=1000)

    invoice = await checkout(
        db, company.id, setup["pos"].id, setup["gestor"], customer_id=None,
        lines_input=[{"product_id": product.id, "quantity": 1}],
        payments=[{"payment_method_id": setup["pm_numerario"].id, "amount": 10000.0}],
    )

    assert invoice.cash_session_id == session.id
    assert invoice.business_date == session.business_date
