"""
The AI assistant's settings: the platform's provider, model, key and message limit (SUPER_ADMIN); the switches of
each company (SUPER_ADMIN) and its confirmations (gestor). The API key is kept encrypted and never sent back.
"""
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secret_box import decrypt_secret, encrypt_secret, secret_hint
from app.models.company import Company
from app.models.company_ai_settings import CompanyAiSettings
from app.services.ai.provider_client import PROVIDERS, AiProviderError, complete
from app.services.platform_settings_service import get_or_create_platform_settings


class AiSettingsError(Exception):
    """A setting refused - the message is shown as it is (PT-PT)."""


# ---------- The platform (SUPER_ADMIN)

def platform_ai_view(settings) -> dict:
    key = decrypt_secret(settings.ai_api_key_encrypted)
    return {
        "provider": settings.ai_provider, "model": settings.ai_model, "monthly_limit": settings.ai_monthly_limit,
        "has_api_key": bool(settings.ai_api_key_encrypted),
        "api_key_hint": secret_hint(key) if key else ("Ilegível - introduza de novo" if settings.ai_api_key_encrypted else None),
        "providers": [{"value": k, "label": v} for k, v in PROVIDERS.items()],
        "telegram_configured": bool(settings.telegram_bot_token_encrypted),
        "telegram_bot_username": settings.telegram_bot_username,
    }


async def get_platform_ai(db: AsyncSession) -> dict:
    return platform_ai_view(await get_or_create_platform_settings(db))


async def update_platform_ai(db: AsyncSession, provider: str | None, model: str | None, api_key: str | None,
                             monthly_limit: int) -> dict:
    """api_key: None = unchanged, "" = removed, otherwise the new key."""
    if provider is not None and provider not in PROVIDERS:
        raise AiSettingsError("Fornecedor de IA desconhecido")
    if monthly_limit < 0:
        raise AiSettingsError("O limite mensal não pode ser negativo")
    model = (model or "").strip() or None
    if provider and not model:
        raise AiSettingsError("Indique o modelo do fornecedor")
    settings = await get_or_create_platform_settings(db)
    settings.ai_provider, settings.ai_model, settings.ai_monthly_limit = provider, model, monthly_limit
    if api_key is not None:
        api_key = api_key.strip()
        settings.ai_api_key_encrypted = encrypt_secret(api_key) if api_key else None
    await db.commit()
    await db.refresh(settings)
    return platform_ai_view(settings)


async def platform_ai_credentials(db: AsyncSession) -> tuple[str, str, str]:
    """(provider, model, key) - or the reason the assistant cannot answer."""
    settings = await get_or_create_platform_settings(db)
    key = decrypt_secret(settings.ai_api_key_encrypted)
    if not settings.ai_provider or not settings.ai_model or not key:
        raise AiSettingsError("O assistente IA não está configurado na plataforma")
    return settings.ai_provider, settings.ai_model, key


async def test_platform_ai(db: AsyncSession) -> dict:
    """A short question to the configured provider: its answer and how long it took."""
    provider, model, key = await platform_ai_credentials(db)
    start = time.monotonic()
    try:
        # room for the models that think before answering (Gemini, o-series...): a few tokens would all go to the thinking
        answer = await complete(provider, model, key, "És um teste de ligação.",
                                [{"role": "user", "content": "Responde apenas: OK"}], max_tokens=1000, timeout=60)
    except AiProviderError as e:
        raise AiSettingsError(str(e))
    if not answer:
        raise AiSettingsError("O fornecedor respondeu, mas o modelo não devolveu texto - experimente outro modelo")
    return {"answer": answer[:200], "seconds": round(time.monotonic() - start, 1)}


# ---------- A company (SUPER_ADMIN switches, gestor confirmations)

async def _company_settings(db: AsyncSession, company_id: uuid.UUID) -> CompanyAiSettings:
    row = (await db.execute(select(CompanyAiSettings).where(CompanyAiSettings.company_id == company_id))).scalar_one_or_none()
    if row is None:
        if await db.get(Company, company_id) is None:
            raise AiSettingsError("Empresa não encontrada")
        row = CompanyAiSettings(company_id=company_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def company_ai_view(db: AsyncSession, row: CompanyAiSettings) -> dict:
    platform = await get_or_create_platform_settings(db)
    return {
        "ai_enabled": row.ai_enabled, "whatsapp_enabled": row.whatsapp_enabled, "telegram_enabled": row.telegram_enabled,
        "email_enabled": row.email_enabled, "monthly_limit": row.monthly_limit,
        "effective_monthly_limit": row.monthly_limit if row.monthly_limit is not None else platform.ai_monthly_limit,
        "platform_monthly_limit": platform.ai_monthly_limit,
        "confirm_documents": row.confirm_documents, "confirm_sends": row.confirm_sends,
        "platform_configured": bool(platform.ai_provider and platform.ai_model and platform.ai_api_key_encrypted),
    }


async def get_company_ai(db: AsyncSession, company_id: uuid.UUID) -> dict:
    return await company_ai_view(db, await _company_settings(db, company_id))


async def update_company_ai_switches(db: AsyncSession, company_id: uuid.UUID, ai_enabled: bool, whatsapp_enabled: bool,
                                     telegram_enabled: bool, email_enabled: bool, monthly_limit: int | None) -> dict:
    """SUPER_ADMIN: the assistant and its channels for a company. The channels only work with the assistant on."""
    if monthly_limit is not None and monthly_limit < 0:
        raise AiSettingsError("O limite mensal não pode ser negativo")
    row = await _company_settings(db, company_id)
    row.ai_enabled = ai_enabled
    row.whatsapp_enabled, row.telegram_enabled, row.email_enabled = (
        ai_enabled and whatsapp_enabled, ai_enabled and telegram_enabled, ai_enabled and email_enabled)
    row.monthly_limit = monthly_limit
    await db.commit()
    await db.refresh(row)
    return await company_ai_view(db, row)


async def update_company_ai_confirmations(db: AsyncSession, company_id: uuid.UUID, confirm_documents: bool,
                                          confirm_sends: bool) -> dict:
    """Gestor: whether the assistant waits for his confirmation before issuing a document / sending one."""
    row = await _company_settings(db, company_id)
    row.confirm_documents, row.confirm_sends = confirm_documents, confirm_sends
    await db.commit()
    await db.refresh(row)
    return await company_ai_view(db, row)
