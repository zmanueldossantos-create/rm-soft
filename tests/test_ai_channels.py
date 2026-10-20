"""
The AI assistant, livraison 4: the assistant from a chat (Telegram). A chat is linked to an account by a code shown in
the application; an unknown chat gets nothing; the same assistant answers (actions confirmed by SIM, a PDF sent into
the chat); NOVA starts another conversation; the answers are turned into Telegram's HTML.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.ai_channel import AiChannelLink
from app.models.product import Product, ProductType
from app.services.ai import provider_client, telegram
from app.services.ai.channels import NOT_LINKED, ChannelError, create_link_code, handle_incoming, list_links, unlink
from app.services.ai.provider_client import ProviderReply
from app.services.ai_settings_service import update_company_ai_switches, update_platform_ai
from app.services.customer_service import create_customer
from app.services.permission_service import seed_permission_catalog
from app.services.stock_service import receive_stock

CHAT = "778899"


async def _ready(db, ctx):
    company_id = ctx["company"].id
    await seed_permission_catalog(db)
    await update_platform_ai(db, "OPENROUTER", "google/gemini-3.8-flash", "sk-or-1234567890", 300)
    product = Product(company_id=company_id, code="BEN" + uuid.uuid4().hex[:4], name="Ben-u-ron 500", vat_id=ctx["vat_nor"].id,
                      price=1000, min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add(product)
    await db.commit()
    await receive_stock(db, company_id, product.id, 10, warehouse_id=ctx["activity_warehouse"].id)
    await create_customer(db, company_id, "Hotel Presidente", "5417000001")
    return product


def test_telegram_html():
    text = telegram.to_html("Total **1 000 Kz** <ok>\n- uma\n# Título\n| A | B |\n|---|---|\n| 1 | 2 |")
    assert text == "Total <b>1 000 Kz</b> &lt;ok&gt;\n• uma\n<b>Título</b>\nA · B\n1 · 2"


@pytest.mark.asyncio
async def test_linking_a_chat(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, gestor_id = ctx["company"].id, ctx["gestor"].id
    await _ready(db, ctx)

    with pytest.raises(ChannelError, match="não está ativo"):  # the channel must be switched on for the company
        await create_link_code(db, company_id, gestor_id, "TELEGRAM")
    await update_company_ai_switches(db, company_id, True, False, True, False, None)
    code = (await create_link_code(db, company_id, gestor_id, "TELEGRAM"))["code"]

    assert (await handle_incoming(db, "TELEGRAM", CHAT, "@gestor", "Quanto vendi hoje?"))[0]["text"] == NOT_LINKED
    assert "inválido" in (await handle_incoming(db, "TELEGRAM", CHAT, "@gestor", "/start 000000"))[0]["text"]
    assert "Ligado à conta" in (await handle_incoming(db, "TELEGRAM", CHAT, "@gestor", f"/start {code}"))[0]["text"]
    assert "inválido" in (await handle_incoming(db, "TELEGRAM", "other-chat", None, f"LIGAR {code}"))[0]["text"]  # used once
    links = await list_links(db, company_id, gestor_id)
    assert (links["TELEGRAM"]["linked"], links["TELEGRAM"]["name"], links["WHATSAPP"]["enabled"]) == (True, "@gestor", False)

    # another phone linking the same account replaces the first one
    code = (await create_link_code(db, company_id, gestor_id, "TELEGRAM"))["code"]
    await handle_incoming(db, "TELEGRAM", "new-phone", "@novo", code)
    assert (await handle_incoming(db, "TELEGRAM", CHAT, None, "Olá"))[0]["text"] == NOT_LINKED
    active = (await db.execute(select(AiChannelLink).where(AiChannelLink.is_active.is_(True)))).scalars().all()
    assert [l.external_id for l in active] == ["new-phone"]

    await unlink(db, company_id, gestor_id, "TELEGRAM")
    assert (await handle_incoming(db, "TELEGRAM", "new-phone", None, "Olá"))[0]["text"] == NOT_LINKED


@pytest.mark.asyncio
async def test_the_conversation_in_a_chat(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, gestor_id = ctx["company"].id, ctx["gestor"].id
    product = await _ready(db, ctx)
    await update_company_ai_switches(db, company_id, True, False, True, False, None)
    code = (await create_link_code(db, company_id, gestor_id, "TELEGRAM"))["code"]
    await handle_incoming(db, "TELEGRAM", CHAT, "@gestor", f"/start {code}")

    async def fake_chat(provider, model, key, system, transcript, offered, **kwargs):
        names = [t["name"] for t in offered]
        assert "enviar_pdf_no_chat" in names and "Telegram" in system
        last = transcript[-1]
        if last["role"] == "user" and "fatura" in last["content"]:
            return ProviderReply("", [{"id": "p", "name": "preparar_documento", "arguments": {
                "tipo": "FATURA", "cliente": "Hotel Presidente", "linhas": [{"artigo": product.code, "quantidade": 1}]}}])
        if last["role"] == "user" and "PDF" in last["content"]:
            return ProviderReply("", [{"id": "d", "name": "enviar_pdf_no_chat", "arguments": {"numero": "FT2026/1"}}])
        return ProviderReply("Feito.", [])
    monkeypatch.setattr(provider_client, "chat", fake_chat)

    items = await handle_incoming(db, "TELEGRAM", CHAT, "@gestor", "Faz uma fatura de 1 Ben-u-ron ao Hotel Presidente")
    assert items[0]["text"] == "Feito." and "Responda **SIM**" in items[1]["text"] and "Hotel Presidente" in items[1]["text"]
    done = await handle_incoming(db, "TELEGRAM", CHAT, "@gestor", "SIM")
    assert "emitido" in done[0]["text"]
    reference = done[0]["text"].split("**")[1]  # "FT FT2026/1"

    sent = await handle_incoming(db, "TELEGRAM", CHAT, "@gestor", f"Manda-me o PDF da {reference}")
    filename, content, caption = sent[1]["document"]
    assert content.startswith(b"%PDF") and caption == reference

    link = (await db.execute(select(AiChannelLink).where(AiChannelLink.external_id == CHAT))).scalar_one()
    first_conversation = link.conversation_id
    assert first_conversation is not None
    assert "Nova conversa" in (await handle_incoming(db, "TELEGRAM", CHAT, None, "NOVA"))[0]["text"]
    await handle_incoming(db, "TELEGRAM", CHAT, None, "Olá")
    await db.refresh(link)
    assert link.conversation_id not in (None, first_conversation)

    # the company switches Telegram off: the chat is told, nothing answered
    await update_company_ai_switches(db, company_id, True, False, False, False, None)
    assert "desativado" in (await handle_incoming(db, "TELEGRAM", CHAT, None, "Olá"))[0]["text"]


@pytest.mark.asyncio
async def test_the_answers_sent_to_telegram(monkeypatch):
    calls = []

    async def fake_call(token, method, data=None, files=None, timeout=30):
        calls.append((method, data, files))
        return {}
    monkeypatch.setattr(telegram, "call", fake_call)
    await telegram.send_items("t", "42", [{"text": "**Olá**\n" + "linha\n" * 900}, {"document": ("FT.pdf", b"%PDF-1", "FT 1")}])
    assert [c[0] for c in calls] == ["sendMessage", "sendMessage", "sendDocument"]  # a long text in two messages
    assert calls[0][1]["parse_mode"] == "HTML" and calls[0][1]["text"].startswith("<b>Olá</b>")
    assert calls[2][2]["document"][0] == "FT.pdf" and calls[2][1]["chat_id"] == "42"


# ---------- WhatsApp (WhatsApp Cloud API) - prepared before the RM SOFT number exists

def test_whatsapp_formatting_and_messages():
    from app.services.ai import whatsapp
    assert whatsapp.to_whatsapp("Total **1 000 Kz**\n- uma\n| A | B |\n|---|---|") == "Total *1 000 Kz*\n• uma\nA · B"
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "244923000102", "profile": {"name": "Manuel"}}],
        "messages": [{"from": "244923000102", "type": "text", "text": {"body": "Quanto vendi hoje?"}},
                     {"from": "244923000102", "type": "image", "image": {}}],
        "statuses": [{"status": "read"}]}}]}]}
    assert whatsapp.incoming_messages(payload) == [
        {"from": "244923000102", "name": "Manuel", "text": "Quanto vendi hoje?"},
        {"from": "244923000102", "name": "Manuel", "text": None}]
    assert whatsapp.incoming_messages({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}) == []


@pytest.mark.asyncio
async def test_whatsapp_settings_and_meta_checks(db):
    import hashlib
    import hmac
    from app.services.ai import whatsapp
    from app.services.platform_settings_service import get_or_create_platform_settings
    view = await whatsapp.update_settings(db, " 1234 5678 ", "244 931 000 000", "EAAG-token-123456", "app-secret-xyz")
    assert (view["configured"], view["phone_number_id"], view["display_number"], view["access_token_hint"]) == (
        True, "12345678", "+244931000000", "•••• 3456")
    assert "EAAG" not in str(view) and "app-secret" not in str(view) and view["verify_token"]
    settings = await get_or_create_platform_settings(db)

    # Meta's verification of the webhook: our verify token, or nothing
    assert whatsapp.verify_subscription(settings, "subscribe", view["verify_token"], "42") == "42"
    assert whatsapp.verify_subscription(settings, "subscribe", "wrong", "42") is None
    # every call signed with the app secret
    body = b'{"entry": []}'
    good = "sha256=" + hmac.new(b"app-secret-xyz", body, hashlib.sha256).hexdigest()
    assert whatsapp.signature_valid(settings, body, good)
    assert not whatsapp.signature_valid(settings, body + b" ", good) and not whatsapp.signature_valid(settings, body, None)

    # the token kept when not sent, the number off when removed
    assert (await whatsapp.update_settings(db, "12345678", "+244931000000", None, None))["has_access_token"]
    assert not (await whatsapp.update_settings(db, "12345678", "+244931000000", "", None))["configured"]


@pytest.mark.asyncio
async def test_whatsapp_answers_sent(monkeypatch):
    from app.services.ai import whatsapp
    calls = []

    async def fake_call(token, path, json=None, files=None, data=None):
        calls.append((path, json, files))
        return {"id": "media-1"} if path.endswith("/media") else {}
    monkeypatch.setattr(whatsapp, "call", fake_call)
    await whatsapp.send_items("t", "123", "244923000102", [{"text": "**Olá**"}, {"document": ("FT.pdf", b"%PDF-1", "FT 1")}])
    assert calls[0] == ("123/messages", {"messaging_product": "whatsapp", "to": "244923000102", "type": "text",
                                         "text": {"body": "*Olá*"}}, None)
    assert calls[1][0] == "123/media" and calls[1][2]["file"][0] == "FT.pdf"
    assert calls[2][1]["document"] == {"id": "media-1", "filename": "FT.pdf", "caption": "FT 1"}


@pytest.mark.asyncio
async def test_linking_whatsapp_with_ligar(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, gestor_id = ctx["company"].id, ctx["gestor"].id
    await _ready(db, ctx)
    await update_company_ai_switches(db, company_id, True, True, False, False, None)
    code = (await create_link_code(db, company_id, gestor_id, "WHATSAPP"))["code"]
    assert "Ligado à conta" in (await handle_incoming(db, "WHATSAPP", "244923000102", "Manuel", f"LIGAR {code}"))[0]["text"]
    assert (await list_links(db, company_id, gestor_id))["WHATSAPP"]["name"] == "Manuel"
    # the same number on Telegram is another chat: not linked there
    assert (await handle_incoming(db, "TELEGRAM", "244923000102", None, "Olá"))[0]["text"] == NOT_LINKED
