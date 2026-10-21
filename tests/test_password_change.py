"""
The user's own password change (the menu at the bottom, «Alterar palavra-passe"): the current password proves it is
them; the other devices are logged out (their access and refresh both refused); this device receives a new session.
Refused during a support access. An admin's reset ends the account's sessions too.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest_asyncio
from jose import jwt

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_password
from app.main import app


def _older_session(user) -> tuple[str, str]:
    """A session opened a minute ago on another device."""
    settings = get_settings()
    issued = datetime.now(timezone.utc) - timedelta(minutes=1)
    base = {"sub": str(user.id), "company_id": str(user.company_id), "role": user.role.value, "iat": issued}
    access = jwt.encode({**base, "type": "access", "exp": issued + timedelta(minutes=30)},
                        settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    refresh = jwt.encode({**base, "type": "refresh", "exp": issued + timedelta(days=7)},
                         settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return access, refresh


@pytest_asyncio.fixture
async def client(db):
    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _auth(token):
    return {"Authorization": "Bearer " + token}


async def test_changing_ones_own_password(db, company_with_essentials, client):
    gestor = company_with_essentials["gestor"]
    access, refresh = _older_session(gestor)
    other_access, other_refresh = _older_session(gestor)  # another device
    url = "/api/v1/auth/me/password"

    wrong = await client.post(url, json={"current_password": "errada123", "new_password": "Nova@2026"}, headers=_auth(access))
    assert wrong.status_code == 422 and wrong.json()["detail"] == "A palavra-passe atual está incorreta"
    same = await client.post(url, json={"current_password": "Teste@2026", "new_password": "Teste@2026"}, headers=_auth(access))
    assert same.status_code == 422 and "diferente" in same.json()["detail"]
    short = await client.post(url, json={"current_password": "Teste@2026", "new_password": "curta"}, headers=_auth(access))
    assert short.status_code == 422

    done = await client.post(url, json={"current_password": "Teste@2026", "new_password": "Nova@2026"}, headers=_auth(access))
    assert done.status_code == 200
    await db.refresh(gestor)
    assert verify_password("Nova@2026", gestor.password_hash)

    # this device: its new session works, and refreshes
    assert (await client.get("/api/v1/auth/me", headers=_auth(done.json()["access_token"]))).status_code == 200
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": done.json()["refresh_token"]})).status_code == 200
    # the other devices: logged out, their refresh too
    gone = await client.get("/api/v1/auth/me", headers=_auth(other_access))
    assert gone.status_code == 401 and "alterada" in gone.json()["detail"]
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": other_refresh})).status_code == 401


async def test_an_admin_reset_ends_the_sessions_and_a_deactivated_account_cannot_refresh(db, company_with_essentials, client):
    from app.models.user import User, UserRole
    from app.core.security import hash_password
    from app.services.auth_service import reset_user_password
    ctx = company_with_essentials
    caixa = User(company_id=ctx["company"].id, full_name="Caixa", phone_number="+244923000777",
                 password_hash=hash_password("Teste@2026"), role=UserRole.CAIXA)
    db.add(caixa)
    await db.commit()
    access, refresh = _older_session(caixa)
    assert (await client.get("/api/v1/auth/me", headers=_auth(access))).status_code == 200
    await reset_user_password(db, caixa.id, "Outra@2026", ctx["gestor"])
    assert (await client.get("/api/v1/auth/me", headers=_auth(access))).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})).status_code == 401

    gestor_access, gestor_refresh = _older_session(ctx["gestor"])
    ctx["gestor"].is_active = False
    await db.commit()
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": gestor_refresh})).status_code == 401
