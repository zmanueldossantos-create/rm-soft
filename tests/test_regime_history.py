"""A company's fiscal regimes are kept with the day each took effect; the regime of a given day is read there."""
from datetime import date, timedelta

import pytest

from app.models.company_fiscal_regime import CompanyFiscalRegime
from app.models.fiscal_regime import FiscalRegime
from app.services.company_service import create_company, list_regime_history, regime_on, update_company


@pytest.mark.asyncio
async def test_a_regime_change_is_kept_in_the_history(db, legal_vat_rates):
    exclusion = FiscalRegime(name="Exclusao (historico)", allows_nor=False, allows_red=False, allows_ise=True)
    general = FiscalRegime(name="Geral (historico)", allows_nor=True, allows_red=True, allows_ise=True)
    db.add_all([exclusion, general])
    await db.commit()
    company = await create_company(
        db, name="Empresa Historico", nif="5007654321", email="historico@teste.com", phone_number="+244900000011",
        gestor_full_name="Gestor H", gestor_phone_number="+244900000012", gestor_password="senha1234",
        fiscal_regime_id=exclusion.id,
    )
    company_id = company.id
    await update_company(db, company_id, name=company.name, nif=company.nif, email=company.email,
                         phone_number=company.phone_number, fiscal_regime_id=general.id)
    history = await list_regime_history(db, company_id)
    assert [h["regime"] for h in history] == ["Geral (historico)", "Exclusao (historico)"]


@pytest.mark.asyncio
async def test_the_regime_of_a_day_is_read_in_the_history(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    exclusion = FiscalRegime(name="Exclusao (data)", allows_nor=False, allows_red=False, allows_ise=True)
    general = FiscalRegime(name="Geral (data)", allows_nor=True, allows_red=True, allows_ise=True)
    db.add_all([exclusion, general])
    await db.flush()
    today = date.today()
    db.add_all([
        CompanyFiscalRegime(company_id=company_id, fiscal_regime_id=exclusion.id, valid_from=today - timedelta(days=60)),
        CompanyFiscalRegime(company_id=company_id, fiscal_regime_id=general.id, valid_from=today - timedelta(days=10)),
    ])
    await db.commit()
    assert (await regime_on(db, company_id, today - timedelta(days=30))).name == "Exclusao (data)"
    assert (await regime_on(db, company_id, today)).name == "Geral (data)"
    assert await regime_on(db, company_id, today - timedelta(days=90)) is None
