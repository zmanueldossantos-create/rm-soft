"""
Tests for company_service.create_company - covers fiscal regime VAT
seeding, the exact behaviour Manuel manually verified in the browser
earlier this session (Regime de Exclusao -> only Isento/0% is created).
"""
from app.models.fiscal_regime import FiscalRegime
from app.models.vat import VAT
from app.services.company_service import create_company
from sqlalchemy import select


async def test_regime_exclusao_seeds_only_ise_vat(db):
    regime = FiscalRegime(name="Regime de Exclusao (teste)", allows_nor=False, allows_red=False, allows_ise=True)
    db.add(regime)
    await db.flush()

    company = await create_company(
        db, name="Empresa Exclusao Teste", nif="5111111111", email="exclusao@teste.co.ao",
        phone_number="+244911111111", gestor_full_name="Gestor Teste",
        gestor_phone_number="+244922222222", gestor_password="Teste@2026",
        fiscal_regime_id=regime.id,
    )

    result = await db.execute(select(VAT).where(VAT.company_id == company.id))
    vat_rates = result.scalars().all()

    assert len(vat_rates) == 1
    assert float(vat_rates[0].rate) == 0


async def test_regime_geral_seeds_all_three_vat_rates(db):
    regime = FiscalRegime(name="Regime Geral (teste)", allows_nor=True, allows_red=True, allows_ise=True)
    db.add(regime)
    await db.flush()

    company = await create_company(
        db, name="Empresa Geral Teste", nif="5222222222", email="geral@teste.co.ao",
        phone_number="+244933333333", gestor_full_name="Gestor Teste",
        gestor_phone_number="+244944444444", gestor_password="Teste@2026",
        fiscal_regime_id=regime.id,
    )

    result = await db.execute(select(VAT).where(VAT.company_id == company.id))
    rates = {float(v.rate) for v in result.scalars().all()}

    assert rates == {0.0, 5.0, 14.0}
