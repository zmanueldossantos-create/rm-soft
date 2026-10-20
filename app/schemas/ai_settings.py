"""Schemas of the AI assistant's settings (platform and per company)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProviderOption(BaseModel):
    value: str
    label: str


class PlatformAiResponse(BaseModel):
    provider: str | None
    model: str | None
    monthly_limit: int
    has_api_key: bool
    api_key_hint: str | None
    providers: list[ProviderOption]
    telegram_configured: bool = False
    telegram_bot_username: str | None = None


class PlatformAiUpdateRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None  # None = unchanged, "" = removed
    monthly_limit: int = Field(300, ge=0)


class AiTestResponse(BaseModel):
    answer: str
    seconds: float


class CompanyAiResponse(BaseModel):
    ai_enabled: bool
    whatsapp_enabled: bool
    telegram_enabled: bool
    email_enabled: bool
    monthly_limit: int | None
    effective_monthly_limit: int
    platform_monthly_limit: int
    confirm_documents: bool
    confirm_sends: bool
    platform_configured: bool


class CompanyAiSwitchesRequest(BaseModel):
    ai_enabled: bool = False
    whatsapp_enabled: bool = False
    telegram_enabled: bool = False
    email_enabled: bool = False
    monthly_limit: int | None = Field(None, ge=0)  # None = the platform's default


class CompanyAiConfirmationsRequest(BaseModel):
    confirm_documents: bool = True
    confirm_sends: bool = True


# ---------- The assistant's conversation

class AssistantStatusResponse(BaseModel):
    enabled: bool
    available: bool
    used: int
    limit: int


class AskRequest(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None


class AiActionResponse(BaseModel):
    id: uuid.UUID
    kind: str
    summary: dict
    status: str
    result: dict | None = None
    expires_at: datetime

    class Config:
        from_attributes = True


class AiMessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tools_used: list[str] | None = None
    created_at: datetime
    action: AiActionResponse | None = None  # attached: the card of the action this answer prepared

    class Config:
        from_attributes = True


class AiConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    channel: str
    updated_at: datetime

    class Config:
        from_attributes = True


class AskResponse(BaseModel):
    conversation: AiConversationResponse
    message: AiMessageResponse
    used: int
    limit: int


class ActionDecisionResponse(BaseModel):
    action: AiActionResponse
    message: str


class EmailSettingsResponse(BaseModel):
    configured: bool
    smtp_host: str
    smtp_port: int
    security: str
    username: str
    from_email: str
    from_name: str
    has_password: bool
    password_hint: str | None
    is_active: bool


class EmailSettingsRequest(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    security: str = "STARTTLS"
    username: str | None = None
    password: str | None = None  # None = unchanged, "" = removed
    from_email: str
    from_name: str | None = None
    is_active: bool = True


class EmailTestRequest(BaseModel):
    to: str


class TelegramTokenRequest(BaseModel):
    token: str  # "" removes the bot


class TelegramBotResponse(BaseModel):
    configured: bool
    username: str | None


class ChannelStatus(BaseModel):
    enabled: bool
    linked: bool
    name: str | None
    linked_at: datetime | None


class ChannelsResponse(BaseModel):
    channels: dict[str, ChannelStatus]
    telegram_bot_username: str | None
    whatsapp_configured: bool = False  # the RM SOFT WhatsApp number is set
    whatsapp_number: str | None = None  # where the gestor sends LIGAR <code>


class LinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    link: str | None  # Telegram: opens the bot with the code


class WhatsAppSettingsResponse(BaseModel):
    configured: bool
    phone_number_id: str | None
    display_number: str | None
    has_access_token: bool
    access_token_hint: str | None
    has_app_secret: bool
    verify_token: str | None
    webhook_path: str


class WhatsAppSettingsRequest(BaseModel):
    phone_number_id: str | None = None
    display_number: str | None = None
    access_token: str | None = None  # None = unchanged, "" = removed
    app_secret: str | None = None  # None = unchanged, "" = removed
