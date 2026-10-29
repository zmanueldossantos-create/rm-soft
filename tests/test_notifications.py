"""
Notificações: the gestor's recipients (email, Telegram via a link opened once) receive the events chosen for each one;
an action of the gestor himself is not sent (unless switched on), stock baixo always; nothing without the plan's option;
the messages wait in the outbox and are retried 3 times before ERRO.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.notification import NotificationOutbox, NotificationRecipient, NotificationSettings
from app.models.user import UserRole
from app.services import notification_service as ns
from app.services.ai.channels import handle_incoming
from app.services.auth_service import create_user
from app.services.plan_service import save_plan, set_contract


class Actor:
    def __init__(self, role):
        self.role = role


async def _recipient(db, company_id, channel="EMAIL", events=("VENDA", "CAIXA_FECHADA"), **extra):
    return await ns.add_recipient(db, company_id, {"name": "Dono", "channel": channel, "address": "dono@empresa.ao",
                                                   "events": list(events), **extra})


async def _with_bot(db):
    """A Telegram bot set on this server (Configurações of the platform) - needed for a Telegram recipient."""
    from app.services.platform_settings_service import get_or_create_platform_settings
    platform = await get_or_create_platform_settings(db)
    platform.telegram_bot_username, platform.telegram_bot_token_encrypted = "rmsoft_bot", "x"
    await db.commit()


async def _outbox(db):
    return (await db.execute(select(NotificationOutbox).order_by(NotificationOutbox.created_at))).scalars().all()


async def test_recipients(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    with pytest.raises(ns.NotificationError, match="email inválido"):
        await ns.add_recipient(db, company_id, {"name": "X", "channel": "EMAIL", "address": "nao-email"})
    with pytest.raises(ns.NotificationError, match="WhatsApp"):
        await ns.add_recipient(db, company_id, {"name": "X", "channel": "WHATSAPP", "address": "+244923000000"})
    made = await _recipient(db, company_id, events=("VENDA", "CHECK_IN", "INVENTADO"))
    assert made["events"] == ["VENDA"] and made["linked"]  # no hotel for this company: CHECK_IN is not offered
    with pytest.raises(ns.NotificationError, match="bot Telegram"):
        await ns.add_recipient(db, company_id, {"name": "Gerente", "channel": "TELEGRAM", "events": ["VENDA"]})
    await _with_bot(db)
    telegram = await ns.add_recipient(db, company_id, {"name": "Gerente", "channel": "TELEGRAM", "events": ["VENDA"]})
    assert not telegram["linked"] and telegram["link"].startswith("https://t.me/rmsoft_bot?start=NT")


async def test_who_receives_what(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _recipient(db, company_id)
    await ns.add_recipient(db, company_id, {"name": "Caixa?", "channel": "EMAIL", "address": "b@e.ao", "events": ["VENDA"],
                                            "is_active": False})
    cashier, gestor = Actor(UserRole.CAIXA), Actor(UserRole.GESTOR)

    assert await ns.notify(db, company_id, "VENDA", "Venda FR 1 - 500 Kz", actor=cashier, amount=500) == 1
    assert await ns.notify(db, company_id, "VENDA", "Venda do gestor", actor=gestor, amount=500) == 0  # he knows
    assert await ns.notify(db, company_id, "MESA_ABERTA", "Mesa 1", actor=cashier) == 0  # not chosen
    settings = await ns.get_settings_row(db, company_id)
    settings.include_gestor_actions, settings.sale_min_amount = True, 1000
    assert await ns.notify(db, company_id, "VENDA", "Venda pequena", actor=gestor, amount=500) == 0  # under the minimum
    assert await ns.notify(db, company_id, "VENDA", "Venda grande", actor=gestor, amount=5000) == 1
    settings.enabled = False
    assert await ns.notify(db, company_id, "VENDA", "Desligado", actor=cashier, amount=5000) == 0
    await db.commit()
    texts = [m.text for m in await _outbox(db)]
    assert texts == ["Venda FR 1 - 500 Kz", "Venda grande"]


async def test_nothing_without_the_plan_option(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _recipient(db, company_id)
    plan = await save_plan(db, None, {"name": "Sem avisos", "options": []})
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "SAAS"})
    assert await ns.notify(db, company_id, "VENDA", "x", actor=Actor(UserRole.CAIXA)) == 0


async def test_telegram_link_and_sending(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _with_bot(db)
    await ns.add_recipient(db, company_id, {"name": "Gerente", "channel": "TELEGRAM", "events": ["VENDA"]})
    recipient = (await db.execute(select(NotificationRecipient))).scalar_one()
    assert await ns.notify(db, company_id, "VENDA", "antes", actor=Actor(UserRole.CAIXA)) == 0  # not linked yet
    answer = await handle_incoming(db, "TELEGRAM", "777", "@gerente", "/start " + recipient.link_code.lower())
    assert "Ligado" in answer[0]["text"]
    await db.refresh(recipient)
    assert recipient.address == "777" and recipient.telegram_name == "@gerente"
    assert await ns.notify(db, company_id, "VENDA", "depois", actor=Actor(UserRole.CAIXA)) == 1
    await db.commit()

    sent = []

    async def ok(_db, message):
        sent.append((message.channel, message.address, message.text))
    assert await ns.send_due(db, deliver=ok) == 1
    assert sent == [("TELEGRAM", "777", "depois")]
    assert (await _outbox(db))[0].status == "ENVIADA"


async def test_retries_then_error(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _recipient(db, company_id)
    await ns.notify(db, company_id, "VENDA", "x", actor=Actor(UserRole.CAIXA))
    await db.commit()

    async def down(_db, _message):
        raise RuntimeError("SMTP indisponível")
    now = datetime.now(timezone.utc)
    for minutes in (0, 2, 10, 40):  # the first try, then 1 min, 5 min, 30 min later
        assert await ns.send_due(db, deliver=down, now=now + timedelta(minutes=minutes)) == 1
    message = (await _outbox(db))[0]
    assert message.status == "ERRO" and message.attempts == 4 and message.last_error == "SMTP indisponível"
    assert await ns.send_due(db, deliver=down, now=now + timedelta(days=1)) == 0


async def test_the_screen(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            h = {"Authorization": "Bearer " + create_access_token(subject=str(ctx["gestor"].id), company_id=str(company_id),
                                                                  role="GESTOR")}
            view = (await client.get("/api/v1/company/me/notifications", headers=h)).json()
            assert view["allowed"] and [e["code"] for e in view["events"]] == ["VENDA", "PRECO_ALTERADO", "CAIXA_FECHADA"]
            assert view["channels"] == {"EMAIL": False, "TELEGRAM": False, "WHATSAPP": False}
            made = await client.post("/api/v1/company/me/notifications/recipients", headers=h,
                                     json={"name": "Dono", "channel": "EMAIL", "address": "dono@empresa.ao", "events": ["VENDA"]})
            assert made.status_code == 201, made.text
            assert (await client.post(f"/api/v1/company/me/notifications/recipients/{made.json()['id']}/test",
                                      headers=h)).status_code == 200
            assert (await client.put("/api/v1/company/me/notifications/settings", headers=h,
                                     json={"enabled": True, "include_gestor_actions": True, "sale_min_amount": 2500})).status_code == 200
            view = (await client.get("/api/v1/company/me/notifications", headers=h)).json()
            assert view["settings"]["sale_min_amount"] == 2500 and view["history"][0]["event"] == "Teste"
            cashier = await create_user(db, company_id, "Caixa", "+244923000301", "Teste@2026", "CAIXA")
            hc = {"Authorization": "Bearer " + create_access_token(subject=str(cashier.id), company_id=str(company_id), role="CAIXA")}
            assert (await client.get("/api/v1/company/me/notifications", headers=hc)).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
