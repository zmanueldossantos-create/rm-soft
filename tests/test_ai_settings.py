"""
The AI assistant, livraison 1: the platform's provider, model and key (kept encrypted, never sent back), the switches
of each company (SUPER_ADMIN) and its confirmations (gestor), the connection test.
"""
import pytest
from sqlalchemy import select

from app.core.secret_box import decrypt_secret, encrypt_secret, secret_hint
from app.models.platform_settings import PlatformSettings
from app.services import ai_settings_service
from app.services.ai.provider_client import AiProviderError

check_platform_ai = ai_settings_service.test_platform_ai  # not named test_*: pytest would collect it
from app.services.ai_settings_service import (
    AiSettingsError, get_company_ai, get_platform_ai, update_company_ai_confirmations,
    update_company_ai_switches, update_platform_ai,
)


def test_secrets_are_encrypted_and_only_their_end_is_shown():
    token = encrypt_secret("sk-ant-1234567890abcd")
    assert "1234567890" not in token and decrypt_secret(token) == "sk-ant-1234567890abcd"
    assert decrypt_secret("not-a-token") is None and decrypt_secret(None) is None
    assert secret_hint("sk-ant-1234567890abcd") == "•••• abcd"


@pytest.mark.asyncio
async def test_the_platform_settings(db):
    view = await get_platform_ai(db)
    assert (view["provider"], view["has_api_key"], view["monthly_limit"]) == (None, False, 300)
    with pytest.raises(AiSettingsError):
        await update_platform_ai(db, "GEMINI", "x", "k", 300)
    with pytest.raises(AiSettingsError):  # a provider needs its model
        await update_platform_ai(db, "ANTHROPIC", " ", "k", 300)
    with pytest.raises(AiSettingsError):
        await check_platform_ai(db)  # nothing configured yet

    view = await update_platform_ai(db, "ANTHROPIC", " claude-sonnet ", " sk-ant-1234567890abcd ", 500)
    assert (view["provider"], view["model"], view["has_api_key"], view["api_key_hint"], view["monthly_limit"]) == (
        "ANTHROPIC", "claude-sonnet", True, "•••• abcd", 500)
    stored = (await db.execute(select(PlatformSettings))).scalar_one()
    assert "1234567890" not in stored.ai_api_key_encrypted  # never in clear in the database
    assert "api_key" not in view and "sk-ant" not in str(view)  # never sent back

    # the key unchanged when not sent, removed when sent empty
    view = await update_platform_ai(db, "OPENAI", "gpt-4o-mini", None, 500)
    assert view["has_api_key"] and view["provider"] == "OPENAI"
    assert (await update_platform_ai(db, "OPENAI", "gpt-4o-mini", "", 500))["has_api_key"] is False


@pytest.mark.asyncio
async def test_the_connection_test(db, monkeypatch):
    await update_platform_ai(db, "OPENROUTER", "openai/gpt-4o-mini", "sk-or-1234567890", 300)
    calls = []

    async def answering(provider, model, api_key, system, messages, **kwargs):
        calls.append((provider, model, api_key))
        return "OK"
    monkeypatch.setattr(ai_settings_service, "complete", answering)
    result = await check_platform_ai(db)
    assert result["answer"] == "OK" and calls == [("OPENROUTER", "openai/gpt-4o-mini", "sk-or-1234567890")]

    async def silent(*args, **kwargs):
        return ""
    monkeypatch.setattr(ai_settings_service, "complete", silent)
    with pytest.raises(AiSettingsError, match="não devolveu texto"):
        await check_platform_ai(db)

    async def refusing(*args, **kwargs):
        raise AiProviderError("Chave de acesso recusada pelo fornecedor de IA")
    monkeypatch.setattr(ai_settings_service, "complete", refusing)
    with pytest.raises(AiSettingsError, match="recusada"):
        await check_platform_ai(db)


@pytest.mark.asyncio
async def test_the_company_switches_and_confirmations(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    view = await get_company_ai(db, company_id)  # created on first read: off, the confirmations on
    assert (view["ai_enabled"], view["confirm_documents"], view["confirm_sends"], view["effective_monthly_limit"],
            view["platform_configured"]) == (False, True, True, 300, False)

    # a channel only works with the assistant on
    view = await update_company_ai_switches(db, company_id, False, True, True, True, None)
    assert (view["whatsapp_enabled"], view["telegram_enabled"], view["email_enabled"]) == (False, False, False)
    view = await update_company_ai_switches(db, company_id, True, True, False, True, 50)
    assert (view["ai_enabled"], view["whatsapp_enabled"], view["telegram_enabled"], view["email_enabled"],
            view["effective_monthly_limit"]) == (True, True, False, True, 50)
    with pytest.raises(AiSettingsError):
        await update_company_ai_switches(db, company_id, True, False, False, False, -1)

    # the gestor's confirmations do not touch the switches
    view = await update_company_ai_confirmations(db, company_id, False, True)
    assert (view["confirm_documents"], view["confirm_sends"], view["ai_enabled"], view["whatsapp_enabled"]) == (
        False, True, True, True)
