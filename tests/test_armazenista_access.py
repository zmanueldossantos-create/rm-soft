"""
The warehouse keeper (ARMAZENISTA, default rights) can do his whole job: the reference lists of a new warehouse, the
customers of a Guia de Remessa, the years/periods of the Resumo de Produção - and still not what is not his (the
customers' management, the fiscal periods' management, the till).
"""
import httpx
import pytest

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.services.auth_service import create_user
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog


@pytest.fixture
async def keeper(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    user = await create_user(db, company_id, "Paulo Armazém", "+244923000431", "Teste@2026", "ARMAZENISTA")
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    await db.commit()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    token = create_access_token(subject=str(user.id), company_id=str(company_id), role="ARMAZENISTA")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                 headers={"Authorization": "Bearer " + token}) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", [
    "/api/v1/catalogs/provinces", "/api/v1/catalogs/municipalities", "/api/v1/catalogs/units",  # a new warehouse, a recipe
    "/api/v1/customers",  # a Guia de Remessa to a customer (guias:manage)
    "/api/v1/fiscal/years",  # the Resumo de Produção's filter (production:view)
    "/api/v1/products/with-recipe", "/api/v1/suppliers",
])
async def test_what_the_keeper_reads(keeper, path):
    seen = await keeper.get(path)
    assert seen.status_code == 200, (path, seen.text)


@pytest.mark.parametrize("method, path", [
    ("post", "/api/v1/customers"),  # creating customers is the till's / the gestor's
    ("post", "/api/v1/fiscal/years"),
    ("get", "/api/v1/catalogs/countries"),  # the other reference catalogs stay behind catalogs:view_reference
])
async def test_what_stays_closed(keeper, method, path):
    refused = await getattr(keeper, method)(path, **({"json": {}} if method == "post" else {}))
    assert refused.status_code in (403, 422), (path, refused.status_code)
    if refused.status_code == 422:  # validated before the permission? then it must still be refused with a body
        pytest.fail(f"{path}: 422 before the permission check")
