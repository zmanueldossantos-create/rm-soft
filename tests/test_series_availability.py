"""A document without a series: the message names the document, the year and where to get its series; the Caixa
offers only the types that can take a number now (series_available, the same rules as get_or_create_current_series)."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.document_type import DocumentType
from app.models.establishment import Establishment
from app.services.document_series_service import SeriesNotFoundError, get_or_create_current_series, series_available


async def _types(db):
    return {t.code: t for t in (await db.execute(select(DocumentType))).scalars().all()}


@pytest.mark.asyncio
async def test_manual_without_automatic_series(db, company_with_essentials):
    company = await db.get(Company, company_with_essentials["company"].id)
    types = await _types(db)
    assert await series_available(db, company, types["FR"])  # «Série automática por ano»: made at the first document
    company.auto_series_year = False
    await db.commit()
    assert not await series_available(db, company, types["FR"])
    with pytest.raises(SeriesNotFoundError, match=f"Não há série FR para {date.today().year} - crie-a em Definições da Empresa"):
        await get_or_create_current_series(db, company, types["FR"].id)


@pytest.mark.asyncio
async def test_electronic_needs_the_series_of_the_agt(db, company_with_essentials):
    company = await db.get(Company, company_with_essentials["company"].id)
    company.issuance_mode, company.auto_series_year = "ELETRONICA", False
    db.add(Establishment(company_id=company.id, code="SEDE", name="Sede"))
    await db.commit()
    types = await _types(db)
    assert not await series_available(db, company, types["FR"])
    assert await series_available(db, company, types["FP"])  # a working document: one series a year, made automatically
    with pytest.raises(SeriesNotFoundError, match="Faturação Eletrónica\\) - peça-a à AGT"):
        await get_or_create_current_series(db, company, types["FR"].id)
