"""
Configuração inicial: each step is read from the real data and ticks itself once done; the platform's own items carry
no link for the gestor; electronic invoicing adds the establishment and needs its series created by hand.
"""
import uuid

import pytest

from app.models.establishment import Establishment
from app.models.product import Product, ProductType
from app.models.user import User, UserRole
from app.core.security import hash_password
from app.services.setup_checklist_service import PLATFORM, get_setup_checklist


def _by_key(result: dict) -> dict:
    return {i["key"]: i for i in result["items"]}


@pytest.mark.asyncio
async def test_the_checklist_follows_the_data(db, company_with_essentials):
    ctx = company_with_essentials
    company = ctx["company"]

    result = await get_setup_checklist(db, company.id)
    items = _by_key(result)
    assert [k for k, i in items.items() if i["required"]] == ["dados", "registo", "regime", "atividade", "series", "periodo", "catalogo"]
    assert (result["required_done"], result["required_total"], result["complete"]) == (4, 7, False)
    assert items["dados"]["detail"] == "Falta: morada, cidade"
    assert items["registo"]["owner"] == PLATFORM and items["registo"]["link"] is None
    assert items["series"]["done"] and "automaticamente" in items["series"]["detail"]
    assert items["periodo"]["done"] and items["atividade"]["done"]
    assert not items["catalogo"]["done"] and items["catalogo"]["link"] == "/products"
    assert not items["equipa"]["done"] and not items["equipa"]["required"]

    company.address, company.city, company.commercial_registration_number = "Rua 1", "Luanda", "RC-123"
    db.add(Product(company_id=company.id, code="P" + uuid.uuid4().hex[:4], name="Pão", vat_id=ctx["vat_nor"].id,
                   price=100, min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id))
    db.add(User(company_id=company.id, full_name="Caixa", phone_number="+244911000111",
                password_hash=hash_password("Teste@2026"), role=UserRole.CAIXA))
    await db.commit()

    result = await get_setup_checklist(db, company.id)
    items = _by_key(result)
    assert (result["required_done"], result["required_total"], result["complete"], result["all_done"]) == (7, 7, True, False)
    assert items["catalogo"]["detail"] == "1 produto(s), 0 serviço(s)"
    assert items["equipa"]["done"]


@pytest.mark.asyncio
async def test_electronic_invoicing_needs_an_establishment_and_series(db, company_with_essentials):
    company = company_with_essentials["company"]
    company.issuance_mode = "ELETRONICA"
    await db.commit()

    items = _by_key(await get_setup_checklist(db, company.id))
    assert not items["estabelecimento"]["done"] and not items["series"]["done"]

    db.add(Establishment(company_id=company.id, code="SEDE", name="Sede"))
    await db.commit()
    items = _by_key(await get_setup_checklist(db, company.id))
    assert items["estabelecimento"]["done"] and not items["series"]["done"]
