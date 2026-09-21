"""At the POS a document billed later (a Fatura) needs pos:checkout_ft on top of pos:checkout; one paid on issue does not."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.issuable import ensure_may_bill_later
from app.services.permission_service import PERMISSION_CATALOG, _ensure_catalog, set_role_permission


def test_the_permission_is_in_the_catalog_and_given_to_the_cashier_by_default():
    entry = next(e for e in PERMISSION_CATALOG if e[0] == "pos:checkout_ft")
    assert "CAIXA" in entry[3]


@pytest.mark.asyncio
async def test_billing_later_needs_the_extra_permission(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    cashier = SimpleNamespace(company_id=company_id, role=SimpleNamespace(value="CAIXA"))
    manager = SimpleNamespace(company_id=company_id, role=SimpleNamespace(value="GESTOR"))

    await ensure_may_bill_later(db, cashier, "FACTURA_RECIBO")  # paid on issue: no extra permission
    with pytest.raises(HTTPException) as refused:
        await ensure_may_bill_later(db, cashier, "FACTURA")
    assert refused.value.status_code == 403
    await ensure_may_bill_later(db, manager, "FACTURA")  # the manager is always allowed

    permission_id = (await _ensure_catalog(db))["pos:checkout_ft"].id
    await db.commit()
    await set_role_permission(db, company_id, "CAIXA", permission_id, True)
    await ensure_may_bill_later(db, cashier, "FACTURA")  # granted: allowed