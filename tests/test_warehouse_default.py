"""
Armazém por defeito: the gestor chooses the warehouse the Stock screen opens with (and Compras proposes) - one per
company, an active one; the default cannot be switched off before another is chosen. The central warehouse (where
receptions land) stays what it is.
"""
import httpx
import pytest

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.services.auth_service import create_user
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
from app.services.stock_service import (
    DefaultWarehouseError, create_warehouse, get_default_warehouse, list_warehouses, set_default_warehouse,
    toggle_warehouse_status,
)


async def _defaults(db, company_id):
    return [w.name for w in await list_warehouses(db, company_id) if w.is_default]


async def test_one_default_per_company(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    central = await get_default_warehouse(db, company_id)
    shop = company_with_essentials["activity_warehouse"]
    assert await _defaults(db, company_id) == []  # none chosen yet: the screens use the central one

    await set_default_warehouse(db, company_id, shop.id)
    assert await _defaults(db, company_id) == [shop.name]
    await set_default_warehouse(db, company_id, central.id)
    assert await _defaults(db, company_id) == [central.name]  # the previous one is no longer the default
    await set_default_warehouse(db, company_id, central.id)  # again: no error, still one
    assert await _defaults(db, company_id) == [central.name]


async def test_inactive_and_switching_off(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    depot = await create_warehouse(db, company_id, "Depósito Viana")
    await set_default_warehouse(db, company_id, depot.id)
    with pytest.raises(DefaultWarehouseError, match="escolha primeiro outro"):
        await toggle_warehouse_status(db, company_id, depot.id)
    await set_default_warehouse(db, company_id, (await get_default_warehouse(db, company_id)).id)
    depot = await toggle_warehouse_status(db, company_id, depot.id)
    assert not depot.is_active
    with pytest.raises(DefaultWarehouseError, match="inativo"):
        await set_default_warehouse(db, company_id, depot.id)


async def test_the_route(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    cashier = await create_user(db, company_id, "Caixa", "+244923000421", "Teste@2026", "CAIXA")
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    await db.commit()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session

    def headers(user):
        return {"Authorization": "Bearer " + create_access_token(subject=str(user.id), company_id=str(company_id),
                                                                 role=user.role.value)}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            url = f"/api/v1/stock/warehouses/{ctx['activity_warehouse'].id}/default"
            assert (await client.post(url, headers=headers(cashier))).status_code == 403
            made = await client.post(url, headers=headers(ctx["gestor"]))
            assert made.status_code == 200, made.text
            assert made.json()["is_default"] is True
            listed = (await client.get("/api/v1/stock/warehouses", headers=headers(ctx["gestor"]))).json()
            assert [w["name"] for w in listed if w["is_default"]] == [ctx["activity_warehouse"].name]
    finally:
        app.dependency_overrides.pop(get_db, None)
