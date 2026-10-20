"""
The AI assistant, livraison 3: the actions it prepares and the application does - a Fatura, Pró-forma or Orçamento
shown first (computed by the real invoicing, nothing issued), issued on Confirmar / SIM or at once when the gestor
chose so; a document sent by email from the company's own account. Refusals come back as the invoicing's own words.
"""
import json
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.ai_pending_action import AiPendingAction
from app.models.invoice import Invoice, InvoiceType
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services import email_service
from app.services.ai import provider_client
from app.services.ai.actions import ActionContext, ActionError, decide_action, run_action_tool
from app.services.ai.assistant_service import ask, list_messages
from app.services.ai.provider_client import ProviderReply
from app.services.ai_settings_service import update_company_ai_confirmations, update_company_ai_switches, update_platform_ai
from app.services.customer_service import create_customer
from app.services.email_service import EmailError, get_email_settings, send_email, update_email_settings
from app.services.permission_service import seed_permission_catalog
from app.services.stock_service import receive_stock

ALL = {"invoices:issue", "invoices:proforma", "invoices:quote", "invoices:view"}


async def _setup(db, ctx):
    company_id = ctx["company"].id
    product = Product(company_id=company_id, code="BEN" + uuid.uuid4().hex[:4], name="Ben-u-ron 500", vat_id=ctx["vat_nor"].id,
                      price=1000, min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add(product)
    await db.commit()
    await receive_stock(db, company_id, product.id, 10, warehouse_id=ctx["activity_warehouse"].id)
    customer = await create_customer(db, company_id, "Hotel Presidente", "5417000001", email="compras@presidente.ao")
    return product, customer


def _ctx(ctx, confirm=True, permissions=ALL):
    return ActionContext(company_id=ctx["company"].id, user_id=ctx["gestor"].id, permissions=set(permissions),
                         conversation_id=None, confirm_documents=confirm, confirm_sends=confirm)


async def _stock(db, ctx, product_id):
    return float((await db.execute(select(Stock.quantity).where(
        Stock.product_id == product_id, Stock.warehouse_id == ctx["activity_warehouse"].id))).scalar_one())


async def _count(db, model, *where):
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


@pytest.mark.asyncio
async def test_a_document_prepared_then_confirmed(db, company_with_essentials):
    ctx = company_with_essentials
    product, customer = await _setup(db, ctx)
    action_ctx = _ctx(ctx)
    result = json.loads(await run_action_tool(db, action_ctx, "preparar_documento", {
        "tipo": "FATURA", "cliente": "presidente", "linhas": [{"artigo": "ben-u-ron", "quantidade": 2}]}))
    assert result["estado"] == "a_aguardar_confirmacao"
    summary = result["resumo"]
    assert (summary["cliente"], summary["linhas"][0]["quantidade"], summary["sem_iva"], summary["total"]) == (
        "Hotel Presidente", 2.0, 2000.0, 2280.0)  # 2 x 1 000 + 14 %
    # nothing issued yet: no document, the stock untouched
    assert await _count(db, Invoice, Invoice.company_id == ctx["company"].id) == 0
    assert await _stock(db, ctx, product.id) == 10.0

    action_id = action_ctx.actions[0]
    action, text = await decide_action(db, ctx["company"].id, ctx["gestor"].id, action_id, True)
    assert action.status == "FEITA" and action.result["total"] == 2280.0 and "emitido" in text
    invoice = (await db.execute(select(Invoice).where(Invoice.id == uuid.UUID(action.result["invoice_id"])))).scalar_one()
    assert (invoice.invoice_type, invoice.customer_id, invoice.created_by_user_id) == (
        InvoiceType.FACTURA, customer.id, ctx["gestor"].id)
    assert await _stock(db, ctx, product.id) == 8.0
    with pytest.raises(ActionError, match="já foi tratada"):
        await decide_action(db, ctx["company"].id, ctx["gestor"].id, action_id, True)


@pytest.mark.asyncio
async def test_refusals_come_back_to_the_assistant(db, company_with_essentials):
    ctx = company_with_essentials
    product, _ = await _setup(db, ctx)
    db.add(Product(company_id=ctx["company"].id, code="BEN2", name="Ben-u-ron xarope", vat_id=ctx["vat_nor"].id, price=800,
                   min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id))
    await db.commit()
    action_ctx = _ctx(ctx)

    async def tool(arguments, permissions=ALL):
        action_ctx.permissions = set(permissions)
        return json.loads(await run_action_tool(db, action_ctx, "preparar_documento", arguments))

    assert "Vários artigos" in (await tool({"tipo": "FATURA", "linhas": [{"artigo": "ben-u-ron", "quantidade": 1}]}))["erro"]
    assert "não encontrado" in (await tool({"tipo": "FATURA", "cliente": "Ninguém", "linhas": [{"artigo": product.code, "quantidade": 1}]}))["erro"]
    stock_refusal = await tool({"tipo": "FATURA", "linhas": [{"artigo": product.code, "quantidade": 50}]})
    assert "Stock insuficiente" in stock_refusal["erro"]  # the invoicing's own rule, before asking anything
    assert "Só posso" in (await tool({"tipo": "NOTA_CREDITO", "linhas": [{"artigo": product.code, "quantidade": 1}]}))["erro"]
    assert "permissão" in (await tool({"tipo": "FATURA", "linhas": [{"artigo": product.code, "quantidade": 1}]},
                                      {"invoices:proforma"}))["erro"]
    assert "cliente do orçamento" in (await tool({"tipo": "ORCAMENTO", "linhas": [{"artigo": product.code, "quantidade": 1}]}))["erro"]
    assert action_ctx.actions == [] and await _count(db, AiPendingAction) == 0
    assert await _count(db, Invoice, Invoice.company_id == ctx["company"].id) == 0


@pytest.mark.asyncio
async def test_without_confirmation_and_the_working_documents(db, company_with_essentials):
    ctx = company_with_essentials
    product, _ = await _setup(db, ctx)
    action_ctx = _ctx(ctx, confirm=False)
    done = json.loads(await run_action_tool(db, action_ctx, "preparar_documento", {
        "tipo": "PRO_FORMA", "cliente": "5417000001", "linhas": [{"artigo": product.code, "quantidade": 3}]}))
    assert done["estado"] == "feito" and done["resultado"]["documento"].startswith("FP ")
    quote = json.loads(await run_action_tool(db, action_ctx, "preparar_documento", {
        "tipo": "ORCAMENTO", "cliente": "Hotel Presidente", "linhas": [{"artigo": product.code, "quantidade": 1}]}))
    assert quote["resultado"]["documento"].startswith("OR ")
    assert await _stock(db, ctx, product.id) == 10.0  # working documents never move stock

    # another company cannot touch these actions
    from tests.test_multi_tenant.test_multi_tenant_isolation import _make_second_company
    other = await _make_second_company(db)
    with pytest.raises(ActionError, match="não encontrada"):
        await decide_action(db, other["company"].id, ctx["gestor"].id, action_ctx.actions[0], True)


@pytest.mark.asyncio
async def test_the_company_email_and_sending_a_document(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, gestor_id = ctx["company"].id, ctx["gestor"].id  # ids: a refused sending rolls the session back
    product, _ = await _setup(db, ctx)
    sent = []
    monkeypatch.setattr(email_service, "_deliver", lambda config, message: sent.append((config, message)))

    with pytest.raises(EmailError, match="não está configurado"):
        await send_email(db, company_id, "a@b.ao", "x", "y")
    with pytest.raises(EmailError, match="inválido"):
        await update_email_settings(db, company_id, "smtp.gmail.com", 587, "STARTTLS", "u", "p", "não-é-email", None)
    view = await update_email_settings(db, company_id, "smtp.gmail.com", 587, "STARTTLS", "farmacia@gmail.com",
                                       "app-password-1234", "farmacia@gmail.com", "Farmácia Teste")
    assert (view["configured"], view["password_hint"]) == (True, "•••• 1234") and "app-password" not in str(view)
    assert (await update_email_settings(db, company_id, "smtp.gmail.com", 465, "SSL", "farmacia@gmail.com", None,
                                        "farmacia@gmail.com", "Farmácia Teste"))["has_password"]  # kept when not sent

    # a sending address belongs to one company only
    from tests.test_multi_tenant.test_multi_tenant_isolation import _make_second_company
    other = await _make_second_company(db)
    with pytest.raises(EmailError, match="já é usado por outra empresa"):
        await update_email_settings(db, other["company"].id, "smtp.gmail.com", 587, "STARTTLS", "x", "p",
                                    "FARMACIA@gmail.com", None)

    # the assistant sends a Fatura it issued: prepared, then confirmed
    action_ctx = _ctx(ctx, confirm=False)
    issued = json.loads(await run_action_tool(db, action_ctx, "preparar_documento", {
        "tipo": "FATURA", "cliente": "Hotel Presidente", "linhas": [{"artigo": product.code, "quantidade": 1}]}))
    reference = issued["resultado"]["documento"]
    action_ctx.confirm_sends = True
    proposed = json.loads(await run_action_tool(db, action_ctx, "enviar_documento_email", {"numero": reference}))
    assert proposed["estado"] == "a_aguardar_confirmacao" and proposed["resumo"]["para"] == "compras@presidente.ao"
    assert sent == []
    action, _ = await decide_action(db, company_id, gestor_id, action_ctx.actions[-1], True)
    assert action.status == "FEITA"
    config, message = sent[0]
    assert (config["host"], config["port"], config["security"], config["password"]) == ("smtp.gmail.com", 465, "SSL", "app-password-1234")
    assert message["To"] == "compras@presidente.ao" and "Farmácia Teste" in message["From"]
    attachment = next(message.iter_attachments())
    assert attachment.get_content_type() == "application/pdf" and attachment.get_content().startswith(b"%PDF")

    # a failure of the mail server is recorded on the action, never lost
    def refusing(config, message):
        raise EmailError("O servidor de email recusou o utilizador ou a palavra-passe")
    monkeypatch.setattr(email_service, "_deliver", refusing)
    json.loads(await run_action_tool(db, action_ctx, "enviar_documento_email", {"numero": reference, "email": "x@y.ao"}))
    action, text = await decide_action(db, company_id, gestor_id, action_ctx.actions[-1], True)
    assert action.status == "FALHOU" and "recusou" in text
    assert "inválido" in json.loads(await run_action_tool(db, action_ctx, "enviar_documento_email",
                                                          {"numero": reference, "email": "nada"}))["erro"]

    # an action left unconfirmed expires
    json.loads(await run_action_tool(db, action_ctx, "enviar_documento_email", {"numero": reference}))
    stale = await db.get(AiPendingAction, action_ctx.actions[-1])
    stale.expires_at = datetime.now(stale.expires_at.tzinfo) - timedelta(minutes=1)
    await db.commit()
    with pytest.raises(ActionError, match="expirou"):
        await decide_action(db, company_id, gestor_id, stale.id, True)
    assert (await get_email_settings(db, company_id))["smtp_port"] == 465


@pytest.mark.asyncio
async def test_the_conversation_with_a_card_and_sim(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id, gestor = ctx["company"].id, ctx["gestor"]
    gestor_id = gestor.id
    await seed_permission_catalog(db)
    product, _ = await _setup(db, ctx)
    await update_platform_ai(db, "OPENROUTER", "google/gemini-3.8-flash", "sk-or-1234567890", 300)
    await update_company_ai_switches(db, company_id, True, False, False, False, None)

    async def fake_chat(provider, model, key, system, transcript, offered, **kwargs):
        assert "preparar_documento" in [t["name"] for t in offered]
        if transcript[-1]["role"] == "user":
            return ProviderReply("", [{"id": "p1", "name": "preparar_documento", "arguments": {
                "tipo": "FATURA", "cliente": "Hotel Presidente", "linhas": [{"artigo": product.code, "quantidade": 1}]}}])
        return ProviderReply("A fatura está pronta: confirme com o botão Confirmar.", [])
    monkeypatch.setattr(provider_client, "chat", fake_chat)

    conversation, message = await ask(db, gestor, "Faz uma fatura de 1 Ben-u-ron ao Hotel Presidente")
    assert message.action_id is not None
    action = await db.get(AiPendingAction, message.action_id)
    assert (action.status, action.conversation_id) == ("PENDENTE", conversation.id)
    conversation_id = conversation.id

    async def no_ai(*args, **kwargs):
        raise AssertionError("SIM is answered without the AI")
    monkeypatch.setattr(provider_client, "chat", no_ai)
    _, done = await ask(db, gestor, "Sim", conversation_id)
    assert "emitido" in done.content
    assert await _count(db, Invoice, Invoice.company_id == company_id, Invoice.invoice_type == InvoiceType.FACTURA) == 1
    assert [m.role for m in await list_messages(db, company_id, gestor_id, conversation_id)] == [
        "user", "assistant", "user", "assistant"]

    # the gestor's choice: no confirmation, the document is issued at once
    await update_company_ai_confirmations(db, company_id, False, True)
    monkeypatch.setattr(provider_client, "chat", fake_chat)
    _, message = await ask(db, gestor, "Outra igual", conversation_id)
    assert (await db.get(AiPendingAction, message.action_id)).status == "FEITA"
    assert await _count(db, Invoice, Invoice.company_id == company_id, Invoice.invoice_type == InvoiceType.FACTURA) == 2


@pytest.mark.asyncio
async def test_a_medicine_on_prescription_needs_its_receita(db, company_with_essentials):
    from datetime import date
    from app.models.prescription import Prescription
    ctx = company_with_essentials
    company_id = ctx["company"].id
    medicine = Product(company_id=company_id, code="CLX" + uuid.uuid4().hex[:4], name="Clamoxyl", vat_id=ctx["vat_ise"].id,
                       exemption_reason_id=ctx["exemption_m11"].id, price=2500, min_stock_threshold=0,
                       product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id, managed_by_batch=True,
                       managed_by_expiry=True, is_medicine=True, active_substance="Amoxicilina", dispensing_regime="RECEITA")
    db.add(medicine)
    await db.commit()
    await receive_stock(db, company_id, medicine.id, 5, lot_number="C1", expiry_date=date.today() + timedelta(days=200),
                        warehouse_id=ctx["activity_warehouse"].id)
    action_ctx = _ctx(ctx)
    lines = [{"artigo": "Clamoxyl", "quantidade": 1}]
    refused = json.loads(await run_action_tool(db, action_ctx, "preparar_documento", {"tipo": "FATURA", "linhas": lines}))
    assert "receita" in refused["erro"].lower()
    ready = json.loads(await run_action_tool(db, action_ctx, "preparar_documento", {
        "tipo": "FATURA", "linhas": lines, "receita": {"numero": "R-778", "medico": "Dr. Silva"}}))
    assert ready["resumo"]["receita"] == "R-778"
    action, _ = await decide_action(db, company_id, ctx["gestor"].id, action_ctx.actions[-1], True)
    assert action.status == "FEITA"
    recorded = (await db.execute(select(Prescription).where(
        Prescription.invoice_id == uuid.UUID(action.result["invoice_id"])))).scalar_one()
    assert (recorded.number, recorded.prescriber) == ("R-778", "Dr. Silva")
