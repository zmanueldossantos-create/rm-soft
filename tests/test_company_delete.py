"""Apagar empresa (SUPER_ADMIN): a company and everything it owns, refused once it has issued real documents."""
import pytest
from sqlalchemy import func, select

from app.models.company import Company
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.point_of_sale import PointOfSale
from app.models.service import Service
from app.models.user import User
from app.models.vat import VAT
from app.services.company_service import CompanyDeleteRefusedError, delete_company
from tests.test_training_mode import _issue, _service


async def _count(db, model, **where):
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return (await db.execute(query)).scalar_one()


@pytest.mark.asyncio
async def test_a_company_in_training_is_deleted_with_everything_it_owns(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    service = await _service(db, ctx)
    company = await db.get(Company, cid)
    company.training_mode = True
    await db.commit()
    invoice = await _issue(db, ctx, service)  # a training document, its lines, its series

    await delete_company(db, cid)

    assert await _count(db, Company, id=cid) == 0
    for model in (User, VAT, Service, PointOfSale, Invoice):
        assert await _count(db, model, company_id=cid) == 0
    assert await _count(db, InvoiceLine, invoice_id=invoice.id) == 0


@pytest.mark.asyncio
async def test_refused_once_a_real_document_was_issued(db, company_with_essentials):
    ctx = company_with_essentials
    service = await _service(db, ctx)
    await _issue(db, ctx, service)  # Modo formação off: a real document
    with pytest.raises(CompanyDeleteRefusedError, match="documentos reais"):
        await delete_company(db, ctx["company"].id)
    assert await db.get(Company, ctx["company"].id) is not None
