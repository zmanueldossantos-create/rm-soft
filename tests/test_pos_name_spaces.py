"""A till's name is kept without stray spaces: « Caixa 1  - Balcão » prints as «Caixa 1 - Balcão» in the reports and
the Telegram alerts («Caixa:  Caixa 1» came from a leading space)."""
import pytest

from app.services.point_of_sale_service import create_point_of_sale, update_point_of_sale


@pytest.mark.asyncio
async def test_the_name_of_a_till_is_trimmed(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    pos = await create_point_of_sale(db, company_id, ctx["activity"].id, "  Caixa 9  - Balcão ")
    assert pos.name == "Caixa 9 - Balcão"
    pos = await update_point_of_sale(db, company_id, pos.id, " Caixa 9 - Esplanada")
    assert pos.name == "Caixa 9 - Esplanada"
