"""A system sub-account keeps the name of what it stands for: the till «Caixa Geral» renamed «Receção» renames its
45.1.x at the next sync (the code and the link stay) - the accountant finds it by its new name."""
import pytest
from sqlalchemy import select

from app.models.account import Account, AccountLink
from app.services.account_mapping_service import sync_subaccounts
from app.services.chart_of_accounts_service import start_chart
from app.services.point_of_sale_service import update_point_of_sale


@pytest.mark.asyncio
async def test_a_renamed_till_renames_its_sub_account(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, pos = ctx["company"].id, ctx["pos"]
    await start_chart(db, company_id, "PGC")
    await sync_subaccounts(db, company_id)

    async def account():
        return (await db.execute(select(Account).join(AccountLink, AccountLink.account_id == Account.id).where(
            AccountLink.company_id == company_id, AccountLink.entity_kind == "TILL", AccountLink.entity_id == pos.id))).scalar_one()
    before = await account()
    assert before.name == "Caixa Teste (Atividade Teste)"
    code = before.code

    await update_point_of_sale(db, company_id, pos.id, "Receção")
    await sync_subaccounts(db, company_id)
    after = await account()
    assert (after.code, after.name) == (code, "Receção (Atividade Teste)")
