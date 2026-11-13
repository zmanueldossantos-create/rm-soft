"""«Fornecedor diverso» (NIF 999999999): every company has one supplier for the purchases from someone without a NIF
(a market seller), as the Consumidor final of the sales - created with the company, never twice."""
import uuid

import pytest
from sqlalchemy import select

from app.models.fiscal_regime import FiscalRegime
from app.models.supplier import Supplier
from app.services.company_service import create_company
from app.services.supplier_service import GENERIC_SUPPLIER_NIF, ensure_generic_supplier


@pytest.mark.asyncio
async def test_a_new_company_has_its_generic_supplier(db):
    regime = (await db.execute(select(FiscalRegime).limit(1))).scalar_one_or_none()
    if regime is None:
        regime = FiscalRegime(name="Regime Geral (fornecedor diverso)", allows_nor=True, allows_red=True, allows_ise=True)
        db.add(regime)
        await db.flush()
    suffix = uuid.uuid4().int % 10_000_000
    company = await create_company(
        db, name=f"Padaria {suffix} Lda", short_name=f"Padaria {suffix}", nif=f"54{suffix:08d}", email=f"p{suffix}@teste.ao",
        phone_number=f"+24492{suffix:07d}", gestor_full_name="Gestor", gestor_phone_number=f"+24493{suffix:07d}",
        gestor_password="Teste@2026", fiscal_regime_id=regime.id)
    suppliers = (await db.execute(select(Supplier).where(Supplier.company_id == company.id))).scalars().all()
    assert [(s.name, s.nif) for s in suppliers] == [("Fornecedor diverso", GENERIC_SUPPLIER_NIF)]

    await ensure_generic_supplier(db, company.id)  # never twice
    assert len((await db.execute(select(Supplier).where(Supplier.company_id == company.id))).scalars().all()) == 1
