"""Changing a company's fiscal regime resyncs its VAT rates from the legal rates catalog, matched by category: a category the
new regime does not allow is deactivated, one it allows is reactivated (never duplicated) or created. Invoice lines keep
their own snapshot untouched."""
import pytest
from sqlalchemy import select

from app.models.fiscal_regime import FiscalRegime
from app.models.vat import VAT
from app.services.company_service import create_company, update_company


async def _active_categories(db, company_id):
    rates = (await db.execute(select(VAT).where(VAT.company_id == company_id))).scalars().all()
    return sorted(r.tax_category for r in rates if r.is_active), len(rates)


@pytest.mark.asyncio
async def test_a_regime_change_resyncs_the_rates_by_category(db, legal_vat_rates):
    every_rate = FiscalRegime(name="Regime A (todas as taxas)", allows_nor=True, allows_red=True, allows_ise=True)
    nor_only = FiscalRegime(name="Regime B (so NOR)", allows_nor=True, allows_red=False, allows_ise=False)
    db.add_all([every_rate, nor_only])
    await db.commit()
    await db.refresh(every_rate)
    await db.refresh(nor_only)

    company = await create_company(
        db, name="Empresa Regime Teste", nif="5001234567", email="regime@teste.com", phone_number="+244900000001",
        gestor_full_name="Gestor RT", gestor_phone_number="+244900000002", gestor_password="senha1234",
        fiscal_regime_id=every_rate.id,
    )
    company_id = company.id
    assert await _active_categories(db, company_id) == (["ISE", "NOR", "RED"], 3)

    # The GESTOR renames a rate: it is still recognised by its category.
    normal = (await db.execute(select(VAT).where(VAT.company_id == company_id, VAT.tax_category == "NOR"))).scalar_one()
    normal.name = "IVA 14 %"
    await db.commit()

    await update_company(db, company_id, name=company.name, nif=company.nif, email=company.email,
                         phone_number=company.phone_number, fiscal_regime_id=nor_only.id)
    assert await _active_categories(db, company_id) == (["NOR"], 3)

    await update_company(db, company_id, name=company.name, nif=company.nif, email=company.email,
                         phone_number=company.phone_number, fiscal_regime_id=every_rate.id)
    assert await _active_categories(db, company_id) == (["ISE", "NOR", "RED"], 3)  # reactivated, no duplicate
