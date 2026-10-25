"""
app/tools/demo.py - the demonstration company (Padaria Sol de Luanda): built through the same services as the screens,
a month of sales with stock that never goes negative, two products left in alert, today's till open; --recriar deletes
it completely (and only it) before building it again.
"""
from datetime import date

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.cash_session import CashSession
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.module import Module
from app.models.movement_type import MovementDirection, MovementType
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.product import Product
from app.models.stock import Stock
from app.tools import demo


async def _platform_catalog(db):
    db.add(Module(name="Padaria"))
    db.add_all([MovementType(code="EAL", name="Entrada automática", direction=MovementDirection.ENTRADA, is_auto=True),
                MovementType(code="SAL", name="Saída automática", direction=MovementDirection.SAIDA, is_auto=True),
                PaymentMethodCatalog(code="CD", name="Cartão débito", is_cash=False)])
    await db.commit()


async def test_the_demonstration_company(db, company_with_essentials, legal_vat_rates, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # its pictures go to uploads/ of the current folder
    monkeypatch.setattr(get_settings(), "AGT_QUEUE", "base")  # the documents wait in the database queue
    await _platform_catalog(db)
    today = date.today()

    result = await demo.build(db, today)
    company = result["company"]
    assert company.nif == demo.DEMO_NIF and company.logo_path

    invoices = (await db.execute(select(func.count(Invoice.id)).where(Invoice.company_id == company.id))).scalar()
    assert invoices == result["invoices"] and invoices > 20
    today_sales = (await db.execute(select(func.count(Invoice.id)).where(
        Invoice.company_id == company.id, Invoice.business_date == today))).scalar()
    assert today_sales == 6
    assert (await db.execute(select(CashSession).where(CashSession.company_id == company.id))).scalar_one().closed_at is None

    stock = (await db.execute(select(Product.code, func.sum(Stock.quantity), Product.min_stock_threshold)
                              .join(Stock, Stock.product_id == Product.id).where(Product.company_id == company.id)
                              .group_by(Product.code, Product.min_stock_threshold))).all()
    assert min(float(q) for _, q, _ in stock) >= 0  # never sold what was not there
    assert {code for code, q, minimum in stock if float(q) <= float(minimum)} == demo.LOW_STOCK
    pictures = list((tmp_path / "uploads" / "products").glob("*.png"))
    assert len(pictures) == len(demo.ARTICLES)

    # --recriar: everything of the demonstration goes, nothing else
    other = company_with_essentials["company"].id
    assert await demo.purge(db)
    assert (await db.execute(select(Company).where(Company.nif == demo.DEMO_NIF))).first() is None
    assert (await db.execute(select(func.count(Invoice.id)).where(Invoice.company_id == company.id))).scalar() == 0
    assert (await db.execute(select(Company).where(Company.id == other))).first() is not None
    assert not list((tmp_path / "uploads" / "products").glob("*.png"))
    assert not await demo.purge(db)  # nothing left to delete
