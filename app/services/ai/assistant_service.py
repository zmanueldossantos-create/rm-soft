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
from app.models.ai_pending_action import AiPendingAction
from app.models.company import Company
from app.models.company_ai_settings import CompanyAiSettings
from app.models.user import User
from app.services.ai import provider_client
from app.services.ai.provider_client import AiProviderError
from app.services.ai.actions import (
    ActionContext, ActionError, action_tools_for, decide_action, is_action_tool, run_action_tool,
)
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


async def _system_prompt(db: AsyncSession, company_id: uuid.UUID, user_name: str, channel: str = "APP") -> str:
    company = await db.get(Company, company_id)
    modules = ", ".join(m.name for m in await list_company_modules(db, company_id)) or "-"
    today = datetime.now(LUANDA).date()
    return (
        "És o assistente do RM SOFT, um ERP angolano (faturação certificada AGT, caixa, stock, compras, tesouraria). "
        f"Falas com {user_name}, da empresa «{company.name}» (NIF {company.nif}). Módulos da empresa: {modules}. "
        f"Hoje é {today.isoformat()} ({_weekday(today)}), em Luanda.\n\n"
        "Regras:\n"
        "- Responde na língua da pergunta (português de Portugal por omissão).\n"
        + (f"- Estás a falar por {channel.title()}: respostas curtas, sem tabelas (usa listas). Para dar o PDF de um "
           "documento ao utilizador, usa enviar_pdf_no_chat.\n" if channel != "APP" else "")
        + "- Para qualquer número da empresa (stock, vendas, dívidas, caixas, documentos) usa SEMPRE as ferramentas; "
        "nunca inventes nem estimes valores. Se nenhuma ferramenta responde, diz claramente que ainda não sabes fazer isso.\n"
        "- Só tens acesso aos dados desta empresa. Não respondas sobre outras empresas.\n"
        "- Podes criar clientes (criar_cliente), preparar Faturas, Pró-formas e Orçamentos (preparar_documento) e "
        "enviar documentos por email "
        "(enviar_documento_email). Se a ferramenta responde «a_aguardar_confirmacao», "
        + ("diz que o documento está pronto e que o utilizador o confirma com o botão Confirmar (ou respondendo SIM); "
           if channel == "APP" else
           "diz numa só frase que está pronto - o resumo e o pedido de SIM / NÃO seguem logo a seguir, não os repitas "
           "(aqui não há botões); ")
        + "nunca digas que foi emitido ou enviado "
        "antes de a ferramenta responder «feito». Fatura/Recibo, notas de crédito, recibos e alterações de clientes "
        "ou produtos "
        "fazem-se nos ecrãs da aplicação: indica qual.\n"
        "- Para «como faço…?», «onde…?» ou «para que serve…?», consulta SEMPRE os guias (consultar_ajuda) e responde com "
        "os passos e os nomes dos botões que eles dão - nunca inventes um procedimento. O utilizador encontra os mesmos "
        "guias no botão Ajuda (ícone ?), no topo da aplicação.\n"
        "- Valores em kwanzas no formato 1 234,56 Kz; datas no formato DD/MM/AAAA.\n"
        "- Sê curto e claro: primeiro a resposta, depois o detalhe útil. Podes usar listas com «- » e **negrito**.\n"
        "- Para «ontem», «esta semana», «este mês», calcula as datas a partir de hoje.\n"
        "- Para indicar um ecrã, usa só estes caminhos do menu (nunca inventes outro): Vendas → Caixa, Faturas, Clientes, "
        "Receitas e registos, Contas Abertas, Cozinha; Catálogo → Produtos, Serviços, Matéria-prima, Produtos "
        "configurados, Resumo de Produção; Stock → Resumo de Stock, Armazéns e Stock, Histórico de Movimentos, Consumo "
        "Interno, Fornecedores, Faturas de compra, Pagamentos a fornecedores, Guias; Reservas → Recursos, Reservas, "
        "Histórico; Finanças → Tesouraria, Períodos/Exercício, Apuramento do IVA, SAF-T; Administração → Empresa "
        "(Definições da Empresa: dados, atividades, séries, email, assistente), Catálogos, Utilizadores, Permissões. Alguns só aparecem conforme os módulos e os direitos do utilizador."
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

    # plain ids from here: a refused action rolls the session back and expires the loaded objects
    user_id, role, user_name = user.id, user.role.value, user.full_name
    asked_at = datetime.now(LUANDA)
    conversation = await get_conversation(db, company_id, user_id, conversation_id) if conversation_id else None
    conversation_id = conversation.id if conversation is not None else None

    # SIM / NÃO answering the action waiting in this conversation: done without the AI
    answer_to_action = _yes_no(question)
    if conversation_id is not None and answer_to_action is not None:
        waiting = (await db.execute(select(AiPendingAction).where(
            AiPendingAction.conversation_id == conversation_id, AiPendingAction.user_id == user_id,
            AiPendingAction.status == "PENDENTE").order_by(AiPendingAction.created_at.desc()))).scalars().first()
        if waiting is not None:
            db.add(AiMessage(conversation_id=conversation_id, company_id=company_id, role="user", content=question,
                             created_at=asked_at))
            await db.commit()
            try:
                action, _ = await decide_action(db, company_id, user_id, waiting.id, answer_to_action)
            except ActionError as e:
                raise AssistantError(str(e))
            message = (await db.execute(select(AiMessage).where(AiMessage.conversation_id == conversation_id)
                                        .order_by(AiMessage.created_at.desc()).limit(1))).scalar_one()
            return await get_conversation(db, company_id, user_id, conversation_id), message

    transcript: list[dict] = []
    if conversation_id is not None:
        earlier = (await db.execute(select(AiMessage).where(AiMessage.conversation_id == conversation_id)
                                    .order_by(AiMessage.created_at.desc(), AiMessage.role).limit(HISTORY_MESSAGES))).scalars().all()
        transcript = [{"role": m.role, "content": m.content} for m in reversed(earlier)]
    transcript.append({"role": "user", "content": question})

    permissions = set(await list_my_permissions(db, company_id, role))
    tools = tools_for(permissions) + action_tools_for(permissions, channel)
    ctx = ActionContext(company_id=company_id, user_id=user_id, permissions=permissions, conversation_id=conversation_id,
                        confirm_documents=settings.confirm_documents, confirm_sends=settings.confirm_sends, channel=channel)
    system = await _system_prompt(db, company_id, user_name, channel)
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
                if is_action_tool(call["name"]):
                    result = await run_action_tool(db, ctx, call["name"], call["arguments"])
                else:
                    result = await run_tool(db, company_id, permissions, call["name"], call["arguments"], role=role)
                transcript.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": result})
        else:
            answer = ""
    except AiProviderError as e:
        await db.rollback()
        raise AssistantError(str(e))
    if not answer:
        await db.rollback()
        raise AssistantError("O assistente não conseguiu responder - reformule a pergunta")

    if conversation_id is None:
        conversation = AiConversation(company_id=company_id, user_id=user_id, title=question[:120], channel=channel)
        db.add(conversation)
        await db.flush()
        conversation_id = conversation.id
    else:
        conversation = await get_conversation(db, company_id, user_id, conversation_id)
    for action_id in ctx.actions:  # the actions prepared before the conversation existed now belong to it
        action = await db.get(AiPendingAction, action_id)
        if action is not None and action.conversation_id is None:
            action.conversation_id = conversation_id
    db.add(AiMessage(conversation_id=conversation_id, company_id=company_id, role="user", content=question, created_at=asked_at))
    message = AiMessage(conversation_id=conversation_id, company_id=company_id, role="assistant", content=answer,
                        tools_used=sorted(set(used)) or None, created_at=max(datetime.now(LUANDA), asked_at),
                        action_id=ctx.actions[-1] if ctx.actions else None)
    db.add(message)
    conversation.updated_at = datetime.now(LUANDA)
    await db.commit()
    await db.refresh(conversation)
    await db.refresh(message)
    message.outbox = ctx.outbox  # files for a WhatsApp / Telegram chat (not stored)
    return conversation, message


def _yes_no(text: str) -> bool | None:
    """SIM -> True, NÃO -> False, anything else None (a real question for the AI)."""
    word = text.strip().lower().rstrip(".!")
    if word in ("sim", "s", "confirmo", "confirmar", "confirma", "ok", "yes", "oui"):
        return True
    if word in ("não", "nao", "n", "cancelar", "cancela", "cancelo", "no", "non"):
        return False
    return None
