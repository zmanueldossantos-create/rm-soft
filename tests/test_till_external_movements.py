"""A till transfers between tills and receives what is sent to it; a bank withdrawal or deposit, an external entry or
exit is the gestor's (tesouraria:external_movements) - unless the company gives that right to the cashier's role."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.tesouraria import routes as tesouraria_routes
from app.models.user import UserRole
from app.schemas.tesouraria import CashMovementCreateRequest
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog


@pytest.mark.asyncio
async def test_a_cashier_cannot_bring_cash_from_outside(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    cashier = SimpleNamespace(id=uuid.uuid4(), company_id=company_id, role=UserRole.CAIXA)
    withdrawal = CashMovementCreateRequest(movement_type="ENTRADA_EXTERNA", amount=10000,
                                           destination_pos_id=ctx["pos"].id, bank_account_id=uuid.uuid4())
    with pytest.raises(HTTPException) as refused:
        await tesouraria_routes.post_cash_movement(payload=withdrawal, db=db, current_user=cashier)
    assert refused.value.status_code == 403 and "registam-se pelo gestor" in refused.value.detail
    deposit = CashMovementCreateRequest(movement_type="SAIDA_EXTERNA", amount=10000, source_pos_id=ctx["pos"].id,
                                        bank_account_id=uuid.uuid4())
    with pytest.raises(HTTPException) as refused:
        await tesouraria_routes.post_cash_movement(payload=deposit, db=db, current_user=cashier)
    assert refused.value.status_code == 403
