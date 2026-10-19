"""
The AI assistant, livraison 2: read-only tools answered by the application for the signed-in user's company only
(another company never sees anything), offered according to the role's permissions; the conversation loop with the
provider (fake here), its messages kept, the monthly limit; the providers' formats (OpenAI-like and Anthropic).
"""
import json
import uuid
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.models.ai_conversation import AiConversation, AiMessage
from app.models.product import Product, ProductType
from app.services.ai import assistant_service, provider_client, tools
from app.services.ai.assistant_service import AssistantError, ask, assistant_status, list_conversations, list_messages
from app.services.ai.provider_client import AiProviderError, ProviderReply, _anthropic_messages, _openai_messages
from app.services.ai_settings_service import update_company_ai_switches, update_platform_ai
from app.services.customer_service import create_customer
from app.services.invoice_service import create_invoice
from app.services.permission_service import seed_permission_catalog
from app.services.stock_service import receive_stock

TODAY = date.today()
EVERYTHING = {"stock:view", "invoices:view", "purchases:view", "tesouraria:overview"}


async def _product(db, ctx, name, threshold=0, company_id=None, vat_id=None):
    product = Product(company_id=company_id or ctx["company"].id, code=name[:3].upper() + uuid.uuid4().hex[:4], name=name,
                      vat_id=vat_id or ctx["vat_nor"].id, price=1000, min_stock_threshold=threshold,
                      product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                      managed_by_batch=True, managed_by_expiry=True, active_substance="Paracetamol")
    db.add(product)
    await db.commit()
    return product


async def _second_company(db):
    from tests.test_multi_tenant.test_multi_tenant_isolation import _make_second_company
    return await _make_second_company(db)


@pytest.mark.asyncio
async def test_the_tools_answer_for_the_company_only(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    panadol = await _product(db, ctx, "Panadol 500", threshold=20)
    await receive_stock(db, company_id, panadol.id, 12, lot_number="P1", expiry_date=TODAY + timedelta(days=10),
                        warehouse_id=ctx["activity_warehouse"].id)
    customer = await create_customer(db, company_id, "Hotel Presidente", "5417000001")
    ft = await create_invoice(db, company_id, ctx["activity"].id, customer_id=customer.id, invoice_type="FACTURA",
                              lines_input=[{"product_id": panadol.id, "quantity": 2}])

    def call(name, **arguments):
        return tools.run_tool(db, company_id, EVERYTHING, name, arguments)

    stock = json.loads(await call("consultar_stock", pesquisa="paracet"))  # by its substance
    item = stock["produtos"][0]
    assert (item["nome"], item["stock_total"], item["stock_minimo"]) == ("Panadol 500", 10.0, 20.0)  # 12 in, 2 sold
    assert item["lotes"][0]["lote"] == "P1" and item["lotes"][0]["quantidade"] == 10.0

    sales = json.loads(await call("resumo_vendas", data_inicio=TODAY.isoformat(), data_fim=TODAY.isoformat()))
    assert (sales["documentos_de_venda"], sales["total_vendas_com_iva"]) == (1, float(ft.total))
    top = json.loads(await call("produtos_mais_vendidos", data_inicio=TODAY.isoformat(), data_fim=TODAY.isoformat()))
    assert top["artigos"] == [{"artigo": "Panadol 500", "quantidade_unidade_base": 2.0, "valor_com_iva": float(ft.total)}]

    alerts = json.loads(await call("alertas_stock", dias=30))
    assert [a["nome"] for a in alerts["abaixo_do_minimo"]] == ["Panadol 500"]
    assert alerts["lotes_a_expirar"][0]["lote"] == "P1" and alerts["lotes_a_expirar"][0]["expirado"] is False

    debts = json.loads(await call("clientes_em_divida"))
    assert debts["total_por_receber"] == float(ft.total) and debts["clientes"][0]["cliente"] == "Hotel Presidente"
    document = json.loads(await call("consultar_documento", numero=f"FT {ft.series}/{ft.number}"))
    assert document["cliente"] == "Hotel Presidente" and document["por_receber"] == float(ft.total)
    assert document["linhas"][0]["artigo"] == "Panadol 500"
    assert "caixas" in json.loads(await call("caixas"))
    assert json.loads(await call("fornecedores_a_pagar"))["total_a_pagar"] == 0.0

    # refused arguments come back as an error for the AI, never an exception
    assert "erro" in json.loads(await call("resumo_vendas", data_inicio="ontem"))
    assert "erro" in json.loads(await call("resumo_vendas", data_inicio="2026-01-01", data_fim="2025-01-01"))
    assert "erro" in json.loads(await call("consultar_documento", numero="FT2026"))

    # another company, even asking for the same names and number, sees nothing of this one
    other = await _second_company(db)
    other_id = other["company"].id

    def other_call(name, **arguments):
        return tools.run_tool(db, other_id, EVERYTHING, name, arguments)

    assert json.loads(await other_call("consultar_stock", pesquisa="Panadol"))["produtos"] == []
    assert json.loads(await other_call("resumo_vendas", data_inicio=TODAY.isoformat(), data_fim=TODAY.isoformat()))[
        "documentos_de_venda"] == 0
    assert json.loads(await other_call("clientes_em_divida"))["clientes"] == []
    assert json.loads(await other_call("alertas_stock"))["lotes_a_expirar"] == []
    assert "nota" in json.loads(await other_call("consultar_documento", numero=f"{ft.series}/{ft.number}"))


@pytest.mark.asyncio
async def test_the_tools_follow_the_role_permissions(db, company_with_essentials):
    names = [t["name"] for t in tools.tools_for({"stock:view"})]
    assert names == ["consultar_stock", "alertas_stock"]
    refused = await tools.run_tool(db, company_with_essentials["company"].id, {"stock:view"}, "resumo_vendas",
                                   {"data_inicio": TODAY.isoformat(), "data_fim": TODAY.isoformat()})
    assert "não disponível" in json.loads(refused)["erro"]
    assert "não disponível" in json.loads(await tools.run_tool(db, uuid.uuid4(), EVERYTHING, "apagar_tudo", {}))["erro"]


@pytest.mark.asyncio
async def test_a_question_answered_with_a_tool(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, gestor = ctx["company"].id, ctx["gestor"]
    await seed_permission_catalog(db)  # the GESTOR holds every permission of the catalog
    await _product(db, ctx, "Panadol 500")

    with pytest.raises(AssistantError, match="não está ativo"):
        await ask(db, gestor, "Olá")
    await update_company_ai_switches(db, company_id, True, False, False, False, 2)
    with pytest.raises(AssistantError, match="não está configurado"):
        await ask(db, gestor, "Olá")
    await update_platform_ai(db, "OPENROUTER", "google/gemini-3.8-flash", "sk-or-1234567890", 300)

    seen = []

    async def fake_chat(provider, model, key, system, transcript, offered, **kwargs):
        seen.append([dict(m) for m in transcript])
        if transcript[-1]["role"] == "user":  # first round: the AI asks for the stock
            return ProviderReply("", [{"id": "c1", "name": "consultar_stock", "arguments": {"pesquisa": "Panadol"}}],
                                 {"reasoning_details": [{"type": "x"}]})
        result = json.loads(transcript[-1]["content"])
        return ProviderReply(f"Tem {result['produtos'][0]['stock_total']:g} unidades de Panadol 500.", [])
    monkeypatch.setattr(provider_client, "chat", fake_chat)

    conversation, message = await ask(db, gestor, "  Quanto Panadol tenho? ")
    assert message.content == "Tem 0 unidades de Panadol 500." and message.tools_used == ["consultar_stock"]
    assert conversation.title == "Quanto Panadol tenho?"
    assert seen[1][1]["extra"] == {"reasoning_details": [{"type": "x"}]}  # sent back as it came
    assert "Panadol 500" in seen[1][2]["content"]  # the tool's result went to the AI
    assert [m.role for m in await list_messages(db, company_id, gestor.id, conversation.id)] == ["user", "assistant"]
    assert [c.id for c in await list_conversations(db, company_id, gestor.id)] == [conversation.id]

    # the same conversation goes on with its history; then the month's limit (2) is reached
    await ask(db, gestor, "E ontem?", conversation.id)
    assert seen[-2][0]["content"] == "Quanto Panadol tenho?"  # history sent first
    assert (await assistant_status(db, company_id))["used"] == 2
    with pytest.raises(AssistantError, match="Limite mensal de 2"):
        await ask(db, gestor, "Mais uma")

    # a provider failure keeps nothing and counts nothing (the session is rolled back: keep the ids first)
    gestor_id, conversation_id = gestor.id, conversation.id
    await update_company_ai_switches(db, company_id, True, False, False, False, 10)

    async def failing(*args, **kwargs):
        raise AiProviderError("Sem ligação ao fornecedor de IA - verifique a ligação à internet")
    monkeypatch.setattr(provider_client, "chat", failing)
    with pytest.raises(AssistantError, match="Sem ligação"):
        await ask(db, gestor, "Vendas de hoje?")
    assert (await db.execute(select(func.count(AiMessage.id)))).scalar_one() == 4
    assert (await db.execute(select(func.count(AiConversation.id)))).scalar_one() == 1

    # another company's user cannot open this conversation
    other = await _second_company(db)
    with pytest.raises(assistant_service.ConversationNotFoundError):
        await list_messages(db, other["company"].id, gestor_id, conversation_id)


def test_the_provider_formats():
    transcript = [
        {"role": "user", "content": "Stock?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "consultar_stock", "arguments": {"pesquisa": "x"}},
                                                            {"id": "b", "name": "caixas", "arguments": {}}],
         "extra": {"reasoning_details": [1]}},
        {"role": "tool", "tool_call_id": "a", "name": "consultar_stock", "content": "{}"},
        {"role": "tool", "tool_call_id": "b", "name": "caixas", "content": "{}"},
    ]
    openai = _openai_messages("SYS", transcript)
    assert openai[0] == {"role": "system", "content": "SYS"}
    assert openai[2]["tool_calls"][0]["function"] == {"name": "consultar_stock", "arguments": '{"pesquisa": "x"}'}
    assert openai[2]["reasoning_details"] == [1] and [m["role"] for m in openai[3:]] == ["tool", "tool"]
    anthropic = _anthropic_messages(transcript)
    assert [m["role"] for m in anthropic] == ["user", "assistant", "user"]  # both results in one user turn
    assert anthropic[1]["content"][0] == {"type": "tool_use", "id": "a", "name": "consultar_stock", "input": {"pesquisa": "x"}}
    assert [b["tool_use_id"] for b in anthropic[2]["content"]] == ["a", "b"]


@pytest.mark.asyncio
async def test_the_provider_replies_are_read(monkeypatch):
    answers = {
        "openrouter.ai": {"choices": [{"message": {"content": None, "reasoning_details": [9], "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "caixas", "arguments": "{}"}}]}}]},
        "api.anthropic.com": {"content": [{"type": "text", "text": "Vou ver."},
                                          {"type": "tool_use", "id": "u1", "name": "caixas", "input": {}}]},
    }
    real_client = httpx.AsyncClient

    def handler(request):
        return httpx.Response(200, json=answers[request.url.host])
    monkeypatch.setattr(provider_client.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    reply = await provider_client.chat("OPENROUTER", "m", "k", "s", [{"role": "user", "content": "?"}], [])
    assert (reply.text, reply.tool_calls, reply.extra) == ("", [{"id": "t1", "name": "caixas", "arguments": {}}],
                                                           {"reasoning_details": [9]})
    reply = await provider_client.chat("ANTHROPIC", "m", "k", "s", [{"role": "user", "content": "?"}], [])
    assert (reply.text, reply.tool_calls) == ("Vou ver.", [{"id": "u1", "name": "caixas", "arguments": {}}])
