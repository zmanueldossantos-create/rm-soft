"""Changing a company's fiscal_regime_id resyncs its VAT rates: deactivates ones the new regime
disallows, (re)activates/creates ones it allows. Invoice lines keep their own snapshot untouched."""
import pytest
from sqlalchemy import select

from app.models.fiscal_regime import FiscalRegime
from app.models.vat import VAT
from app.services.company_service import create_company, update_company


@pytest.mark.asyncio
async def test_switching_from_simplificado_to_geral_deactivates_ise_and_red(db):
    simplificado = FiscalRegime(name="Simplificado Teste", allows_nor=True, allows_red=True, allows_ise=True)
    geral = FiscalRegime(name="Geral Teste", allows_nor=True, allows_red=False, allows_ise=False)
    db.add(simplificado)
    db.add(geral)
    await db.commit()
    await db.refresh(simplificado)
    await db.refresh(geral)

    company = await create_company(
        db, name="Empresa Regime Teste", nif="5001234567", email="regime@teste.com", phone_number="+244900000001",
        gestor_full_name="Gestor RT", gestor_phone_number="+244900000002", gestor_password="senha1234",
        fiscal_regime_id=simplificado.id,
    )

    rates = (await db.execute(select(VAT).where(VAT.company_id == company.id))).scalars().all()
    assert {r.name for r in rates if r.is_active} == {"Isento", "Taxa reduzida", "Taxa normal"}

    await update_company(
        db, company.id, name=company.name, nif=company.nif, email=company.email, phone_number=company.phone_number,
        fiscal_regime_id=geral.id,
    )

    rates_after = (await db.execute(select(VAT).where(VAT.company_id == company.id))).scalars().all()
    active_names = {r.name for r in rates_after if r.is_active}
    inactive_names = {r.name for r in rates_after if not r.is_active}
    assert active_names == {"Taxa normal"}
    assert inactive_names == {"Isento", "Taxa reduzida"}