"""
The AI assistant's conversation: the user's question, the AI's turns with the tools it asks for (run here, for the
user's company only, within his role's permissions), and its answer, kept with the question. The company's monthly
limit counts its questions; a question the provider could not answer is not kept nor counted.
"""
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation import AiConversation, AiMessage
from app.models.company import Company
from app.models.company_ai_settings import CompanyAiSettings
from app.models.user import User
from app.services.ai import provider_client
from app.services.ai.provider_client import AiProviderError
from app.services.ai.tools import run_tool, tools_for
from app.services.ai_settings_service import AiSettingsError, get_company_ai, platform_ai_credentials
from app.services.company_module_service import list_company_modules
from app.services.permission_service import list_my_permissions

LUANDA = ZoneInfo("Africa/Luanda")
MAX_TOOL_ROUNDS = 6  # the AI may chain a few tools for one question, never loop forever
HISTORY_MESSAGES = 16  # the earlier exchanges sent back with a new question
MAX_QUESTION = 2000


class AssistantError(Exception):
    """The assistant cannot answer - the message is shown as it is (PT-PT)."""


class ConversationNotFoundError(Exception):
    pass


def _month_start() -> datetime:
    now = datetime.now(LUANDA)
    return datetime(now.year, now.month, 1, tzinfo=LUANDA)


async def questions_this_month(db: AsyncSession, company_id: uuid.UUID) -> int:
    return (await db.execute(select(func.count(AiMessage.id)).where(
        AiMessage.company_id == company_id, AiMessage.role == "user", AiMessage.created_at >= _month_start()))).scalar_one()


async def assistant_status(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """What the floating button needs: whether the assistant is on, usable, and the month's count."""
    settings = await get_company_ai(db, company_id)
    return {"enabled": settings["ai_enabled"], "available": settings["ai_enabled"] and settings["platform_configured"],
            "used": await questions_this_month(db, company_id), "limit": settings["effective_monthly_limit"]}


async def _system_prompt(db: AsyncSession, company_id: uuid.UUID, user: User) -> str:
    company = await db.get(Company, company_id)
    modules = ", ".join(m.name for m in await list_company_modules(db, company_id)) or "-"
    today = datetime.now(LUANDA).date()
    return (
        "És o assistente do RM SOFT, um ERP angolano (faturação certificada AGT, caixa, stock, compras, tesouraria). "
        f"Falas com {user.full_name}, da empresa «{company.name}» (NIF {company.nif}). Módulos da empresa: {modules}. "
        f"Hoje é {today.isoformat()} ({_weekday(today)}), em Luanda.\n\n"
        "Regras:\n"
        "- Responde na língua da pergunta (português de Portugal por omissão).\n"
        "- Para qualquer número da empresa (stock, vendas, dívidas, caixas, documentos) usa SEMPRE as ferramentas; "
        "nunca inventes nem estimes valores. Se nenhuma ferramenta responde, diz claramente que ainda não sabes fazer isso.\n"
        "- Só tens acesso aos dados desta empresa. Não respondas sobre outras empresas.\n"
        "- Ainda não podes emitir, alterar nem enviar documentos: se te pedirem, explica que essa função virá em breve "
        "e indica o ecrã da aplicação onde se faz.\n"
        "- Valores em kwanzas no formato 1 234,56 Kz; datas no formato DD/MM/AAAA.\n"
        "- Sê curto e claro: primeiro a resposta, depois o detalhe útil. Podes usar listas com «- » e **negrito**.\n"
        "- Para «ontem», «esta semana», «este mês», calcula as datas a partir de hoje."
    )


def _weekday(day: date) -> str:
    return ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"][day.weekday()]


async def get_conversation(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID) -> AiConversation:
    conversation = (await db.execute(select(AiConversation).where(
        AiConversation.id == conversation_id, AiConversation.company_id == company_id, AiConversation.user_id == user_id,
    ))).scalar_one_or_none()
    if conversation is None:
        raise ConversationNotFoundError("Conversa não encontrada")
    return conversation


async def list_conversations(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, limit: int = 30) -> list[AiConversation]:
    return list((await db.execute(select(AiConversation).where(
        AiConversation.company_id == company_id, AiConversation.user_id == user_id,
    ).order_by(AiConversation.updated_at.desc()).limit(limit))).scalars().all())


async def list_messages(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID) -> list[AiMessage]:
    await get_conversation(db, company_id, user_id, conversation_id)
    return list((await db.execute(select(AiMessage).where(AiMessage.conversation_id == conversation_id)
                                  .order_by(AiMessage.created_at, AiMessage.role.desc()))).scalars().all())


async def ask(db: AsyncSession, user: User, question: str, conversation_id: uuid.UUID | None = None,
              channel: str = "APP") -> tuple[AiConversation, AiMessage]:
    """The user's question answered: returns the conversation and the assistant's message (both kept)."""
    company_id = user.company_id
    question = (question or "").strip()
    if not question:
        raise AssistantError("Escreva a sua pergunta")
    if len(question) > MAX_QUESTION:
        raise AssistantError(f"Pergunta demasiado longa (máximo {MAX_QUESTION} caracteres)")
    settings = (await db.execute(select(CompanyAiSettings).where(CompanyAiSettings.company_id == company_id))).scalar_one_or_none()
    if settings is None or not settings.ai_enabled:
        raise AssistantError("O assistente IA não está ativo para a sua empresa")
    status = await assistant_status(db, company_id)
    if status["used"] >= status["limit"]:
        raise AssistantError(f"Limite mensal de {status['limit']} mensagens atingido - o assistente volta no próximo mês")
    try:
        provider, model, key = await platform_ai_credentials(db)
    except AiSettingsError as e:
        raise AssistantError(str(e))

    asked_at = datetime.now(LUANDA)
    conversation = await get_conversation(db, company_id, user.id, conversation_id) if conversation_id else None
    transcript: list[dict] = []
    if conversation is not None:
        earlier = (await db.execute(select(AiMessage).where(AiMessage.conversation_id == conversation.id)
                                    .order_by(AiMessage.created_at.desc(), AiMessage.role).limit(HISTORY_MESSAGES))).scalars().all()
        transcript = [{"role": m.role, "content": m.content} for m in reversed(earlier)]
    transcript.append({"role": "user", "content": question})

    permissions = set(await list_my_permissions(db, company_id, user.role.value))
    tools = tools_for(permissions)
    system = await _system_prompt(db, company_id, user)
    used: list[str] = []
    answer = ""
    try:
        for _ in range(MAX_TOOL_ROUNDS + 1):
            reply = await provider_client.chat(provider, model, key, system, transcript, tools)
            if not reply.tool_calls:
                answer = reply.text
                break
            transcript.append({"role": "assistant", "content": reply.text, "tool_calls": reply.tool_calls, "extra": reply.extra})
            for call in reply.tool_calls:
                used.append(call["name"])
                result = await run_tool(db, company_id, permissions, call["name"], call["arguments"])
                transcript.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": result})
        else:
            answer = ""
    except AiProviderError as e:
        await db.rollback()
        raise AssistantError(str(e))
    if not answer:
        await db.rollback()
        raise AssistantError("O assistente não conseguiu responder - reformule a pergunta")

    if conversation is None:
        conversation = AiConversation(company_id=company_id, user_id=user.id, title=question[:120], channel=channel)
        db.add(conversation)
        await db.flush()
    db.add(AiMessage(conversation_id=conversation.id, company_id=company_id, role="user", content=question, created_at=asked_at))
    message = AiMessage(conversation_id=conversation.id, company_id=company_id, role="assistant", content=answer,
                        tools_used=sorted(set(used)) or None, created_at=max(datetime.now(LUANDA), asked_at))
    db.add(message)
    conversation.updated_at = datetime.now(LUANDA)
    await db.commit()
    await db.refresh(conversation)
    await db.refresh(message)
    return conversation, message
