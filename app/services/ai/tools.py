"""
What the AI assistant may look at: read-only tools, each one a question the application answers itself. The company
always comes from the signed-in user, never from the AI: a tool receives company_id from the server and every query is
filtered by it - the AI cannot reach another company's data, whatever it writes. A tool is offered only when the user's
role may see that part of the application (the same permission as its screen).
"""
import json
import uuid
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.customer import Customer
from app.models.document_type import DocumentType
from app.models.invoice import DocumentLifecycleStatus, Invoice, InvoiceType
from app.models.invoice_line import InvoiceLine
from app.models.payment import Payment
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.product import Product
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.stock import Stock
from app.models.stock_lot import StockLot
from app.models.supplier import Supplier
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.warehouse import Warehouse
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE

MAX_DAYS = 400  # a period longer than about a year is refused (the answer would be too long to be useful)


class ToolError(Exception):
    """A tool refused its arguments - the message goes back to the AI, which tells the user."""


def _money(value) -> float:
    return round(float(value or 0), 2)


def _qty(value) -> float:
    return round(float(value or 0), 3)


def _period(arguments: dict) -> tuple[date, date]:
    try:
        start = date.fromisoformat(str(arguments.get("data_inicio")))
        end = date.fromisoformat(str(arguments.get("data_fim") or arguments.get("data_inicio")))
    except ValueError:
        raise ToolError("Datas inválidas - use o formato AAAA-MM-DD")
    if end < start:
        raise ToolError("A data final é anterior à data inicial")
    if (end - start).days > MAX_DAYS:
        raise ToolError("Período demasiado longo - no máximo cerca de um ano")
    return start, end


def _reference(invoice: Invoice) -> str:
    return f"{DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, 'FT')} {invoice.series}/{invoice.number}"


async def _signs(db: AsyncSession) -> dict[InvoiceType, int]:
    """+1 a sale, -1 a credit note, 0 not a sale (pro-forma, receipt...) - from the document type catalog."""
    by_code = dict((await db.execute(select(DocumentType.code, DocumentType.revenue_sign))).all())
    return {InvoiceType(stored): int(by_code.get(code) or 0) for stored, code in DOC_CODE_BY_INVOICE_TYPE.items()}


# ---------- The tools

async def consultar_stock(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    search = " ".join(str(arguments.get("pesquisa") or "").split())
    if len(search) < 2:
        raise ToolError("Indique pelo menos 2 letras do nome, código ou substância")
    pattern = f"%{search}%"
    products = (await db.execute(
        select(Product, UnitOfMeasureCatalog.code)
        .outerjoin(UnitOfMeasureCatalog, UnitOfMeasureCatalog.id == Product.unit_of_measure_id)
        .where(Product.company_id == company_id,
               or_(Product.name.ilike(pattern), Product.code.ilike(pattern), Product.barcode == search,
                   Product.active_substance.ilike(pattern)))
        .order_by(Product.is_active.desc(), Product.name).limit(10)
    )).all()
    if not products:
        return {"produtos": [], "nota": f"Nenhum produto encontrado para «{search}»"}
    ids = [p.id for p, _ in products]
    levels: dict = {}
    for product_id, warehouse, quantity in (await db.execute(
        select(Stock.product_id, Warehouse.name, Stock.quantity)
        .join(Warehouse, Warehouse.id == Stock.warehouse_id)
        .where(Stock.company_id == company_id, Stock.product_id.in_(ids))
        .order_by(Warehouse.name)
    )).all():
        levels.setdefault(product_id, []).append({"armazem": warehouse, "quantidade": _qty(quantity)})
    lots: dict = {}
    for product_id, warehouse, number, expiry, quantity in (await db.execute(
        select(StockLot.product_id, Warehouse.name, StockLot.lot_number, StockLot.expiry_date, StockLot.quantity)
        .join(Warehouse, Warehouse.id == StockLot.warehouse_id)
        .where(StockLot.company_id == company_id, StockLot.product_id.in_(ids), StockLot.quantity > 0)
        .order_by(StockLot.expiry_date.nulls_last())
    )).all():
        lots.setdefault(product_id, []).append({"armazem": warehouse, "lote": number, "validade": expiry.isoformat() if expiry else None,
                                                "quantidade": _qty(quantity)})
    return {"produtos": [{
        "codigo": p.code, "nome": p.name, "ativo": p.is_active, "unidade": unit, "preco_venda": _money(p.price),
        "substancia_ativa": p.active_substance, "dosagem": p.dosage, "gerido_por_stock": p.managed_by_stock,
        "stock_minimo": _qty(p.min_stock_threshold),
        "stock_total": _qty(sum(l["quantidade"] for l in levels.get(p.id, []))),
        "por_armazem": levels.get(p.id, []), "lotes": lots.get(p.id, [])[:10],
    } for p, unit in products]}


async def resumo_vendas(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    start, end = _period(arguments)
    signs = await _signs(db)
    rows = (await db.execute(
        select(Invoice.invoice_type, Activity.name, func.count(Invoice.id), func.sum(Invoice.subtotal), func.sum(Invoice.vat_total),
               func.sum(Invoice.total))
        .join(Activity, Activity.id == Invoice.activity_id)
        .where(Invoice.company_id == company_id, Invoice.business_date >= start, Invoice.business_date <= end,
               Invoice.invoice_type.in_([t for t, s in signs.items() if s]))
        .group_by(Invoice.invoice_type, Activity.name)
    )).all()
    total = without_vat = vat = 0.0
    documents, credit_notes = 0, 0
    by_activity: dict = {}
    for invoice_type, activity, count, subtotal, vat_total, amount in rows:
        sign = signs[invoice_type]
        total += sign * float(amount or 0)
        without_vat += sign * float(subtotal or 0)
        vat += sign * float(vat_total or 0)
        by_activity[activity] = by_activity.get(activity, 0.0) + sign * float(amount or 0)
        if sign > 0:
            documents += count
        else:
            credit_notes += count
    received = (await db.execute(
        select(PaymentMethodCatalog.name, func.sum(Payment.amount))
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .where(Payment.company_id == company_id, Invoice.company_id == company_id,
               Invoice.business_date >= start, Invoice.business_date <= end)
        .group_by(PaymentMethodCatalog.name)
    )).all()
    return {
        "periodo": {"de": start.isoformat(), "ate": end.isoformat()},
        "total_vendas_com_iva": _money(total), "total_sem_iva": _money(without_vat), "iva": _money(vat),
        "documentos_de_venda": documents, "notas_de_credito": credit_notes,
        "por_atividade": [{"atividade": a, "total": _money(v)} for a, v in sorted(by_activity.items(), key=lambda x: -x[1])],
        "recebimentos_por_metodo": [{"metodo": m, "valor": _money(v)} for m, v in received],
        "nota": "Vendas = faturas, faturas/recibo e notas de débito, menos as notas de crédito (pró-formas e recibos não contam).",
    }


async def produtos_mais_vendidos(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    start, end = _period(arguments)
    limit = max(1, min(int(arguments.get("limite") or 10), 30))
    signs = await _signs(db)
    rows = (await db.execute(
        select(InvoiceLine.product_name_snapshot, Invoice.invoice_type,
               func.sum(InvoiceLine.quantity * InvoiceLine.unit_factor), func.sum(InvoiceLine.line_total))
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(Invoice.company_id == company_id, Invoice.business_date >= start, Invoice.business_date <= end,
               Invoice.invoice_type.in_([t for t, s in signs.items() if s]))
        .group_by(InvoiceLine.product_name_snapshot, Invoice.invoice_type)
    )).all()
    totals: dict = {}
    for name, invoice_type, quantity, amount in rows:
        sign = signs[invoice_type]
        entry = totals.setdefault(name, [0.0, 0.0])
        entry[0] += sign * float(quantity or 0)
        entry[1] += sign * float(amount or 0)
    ranked = sorted(totals.items(), key=lambda x: -x[1][1])[:limit]
    return {"periodo": {"de": start.isoformat(), "ate": end.isoformat()},
            "artigos": [{"artigo": n, "quantidade_unidade_base": _qty(q), "valor_com_iva": _money(v)} for n, (q, v) in ranked]}


async def alertas_stock(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    days = max(0, min(int(arguments.get("dias") or 30), 365))
    today = date.today()
    totals = (await db.execute(
        select(Product.code, Product.name, Product.min_stock_threshold, func.coalesce(func.sum(Stock.quantity), 0))
        .outerjoin(Stock, (Stock.product_id == Product.id) & (Stock.company_id == company_id))
        .where(Product.company_id == company_id, Product.is_active.is_(True), Product.managed_by_stock.is_(True),
               Product.min_stock_threshold > 0)
        .group_by(Product.id, Product.code, Product.name, Product.min_stock_threshold)
    )).all()
    low = [{"codigo": c, "nome": n, "stock": _qty(q), "minimo": _qty(m)} for c, n, m, q in totals if float(q) <= float(m)]
    expiring = (await db.execute(
        select(Product.code, Product.name, StockLot.lot_number, StockLot.expiry_date, StockLot.quantity, Warehouse.name)
        .join(Product, Product.id == StockLot.product_id)
        .join(Warehouse, Warehouse.id == StockLot.warehouse_id)
        .where(StockLot.company_id == company_id, StockLot.quantity > 0, StockLot.expiry_date.is_not(None),
               StockLot.expiry_date <= today + timedelta(days=days))
        .order_by(StockLot.expiry_date).limit(50)
    )).all()
    return {
        "abaixo_do_minimo": sorted(low, key=lambda r: r["nome"])[:50],
        "lotes_a_expirar": [{"codigo": c, "nome": n, "lote": l, "validade": e.isoformat(), "expirado": e < today,
                             "quantidade": _qty(q), "armazem": w} for c, n, l, e, q, w in expiring],
        "dias_considerados": days,
    }


async def clientes_em_divida(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    from app.services.invoice_service import attach_amount_due
    accepts = {code for code, ok in (await db.execute(select(DocumentType.code, DocumentType.accepts_receipt))).all() if ok}
    types = [InvoiceType(t) for t, code in DOC_CODE_BY_INVOICE_TYPE.items() if code in accepts]
    query = (select(Invoice, Customer.name).outerjoin(Customer, Customer.id == Invoice.customer_id)
             .where(Invoice.company_id == company_id, Invoice.invoice_type.in_(types),
                    Invoice.document_status != DocumentLifecycleStatus.ANULADO))
    search = " ".join(str(arguments.get("cliente") or "").split())
    if search:
        query = query.where(Customer.name.ilike(f"%{search}%"))
    rows = (await db.execute(query)).all()
    invoices = [inv for inv, _ in rows]
    await attach_amount_due(db, invoices)
    today = date.today()
    by_customer: dict = {}
    for inv, name in rows:
        if inv.amount_due <= 0.005:
            continue
        entry = by_customer.setdefault(name or "Consumidor final", {"cliente": name or "Consumidor final", "em_divida": 0.0,
                                                                    "vencido": 0.0, "documentos": []})
        entry["em_divida"] += inv.amount_due
        overdue = inv.due_date is not None and inv.due_date < today
        if overdue:
            entry["vencido"] += inv.amount_due
        entry["documentos"].append({"documento": _reference(inv), "data": inv.business_date.isoformat(),
                                    "vencimento": inv.due_date.isoformat() if inv.due_date else None,
                                    "por_receber": _money(inv.amount_due), "vencido": overdue})
    customers = sorted(by_customer.values(), key=lambda c: -c["em_divida"])
    for c in customers:
        c["em_divida"], c["vencido"] = _money(c["em_divida"]), _money(c["vencido"])
        c["documentos"] = sorted(c["documentos"], key=lambda d: d["data"])[:10]
    return {"total_por_receber": _money(sum(c["em_divida"] for c in customers)), "clientes": customers[:20],
            "numero_de_clientes": len(customers)}


async def fornecedores_a_pagar(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    from app.services.supplier_payment_service import invoice_balances
    invoices = (await db.execute(select(PurchaseInvoice).where(
        PurchaseInvoice.company_id == company_id, PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
        PurchaseInvoice.purchase_type == "FT"))).scalars().all()
    balances = await invoice_balances(db, invoices)
    names = dict((await db.execute(select(Supplier.id, Supplier.name).where(Supplier.company_id == company_id))).all())
    by_supplier: dict = {}
    for inv in invoices:
        b = balances[inv.id]
        if b["due"] <= 0.005:
            continue
        entry = by_supplier.setdefault(inv.supplier_id, {"fornecedor": names.get(inv.supplier_id, "?"), "a_pagar": 0.0,
                                                         "vencido": 0.0, "faturas": []})
        entry["a_pagar"] += b["due"]
        if b["overdue"]:
            entry["vencido"] += b["due"]
        entry["faturas"].append({"documento": inv.supplier_document, "data": inv.document_date.isoformat(),
                                 "vencimento": inv.due_date.isoformat() if inv.due_date else None,
                                 "a_pagar": _money(b["due"]), "vencido": b["overdue"]})
    suppliers = sorted(by_supplier.values(), key=lambda s: -s["a_pagar"])
    for s in suppliers:
        s["a_pagar"], s["vencido"] = _money(s["a_pagar"]), _money(s["vencido"])
        s["faturas"] = s["faturas"][:10]
    return {"total_a_pagar": _money(sum(s["a_pagar"] for s in suppliers)), "fornecedores": suppliers[:20]}


async def caixas(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    from app.services.treasury_overview_service import get_treasury_position
    position = await get_treasury_position(db, company_id)
    return {
        "caixas": [{"caixa": t["pos_name"], "atividade": t["activity_name"], "aberta": t["is_open"],
                    "aberta_por": t["opened_by"], "dia_comercial": t["business_date"].isoformat() if t["business_date"] else None,
                    "numerario": t["cash"]} for t in position["tills"]],
        "total_numerario": position["totals"]["cash"], "em_transito": position["totals"]["in_transit"],
    }


async def consultar_clientes(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    from app.services.invoice_service import attach_amount_due
    search = " ".join(str(arguments.get("pesquisa") or "").split())
    query = select(Customer).where(Customer.company_id == company_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Customer.name.ilike(pattern), Customer.nif == search, Customer.customer_code.ilike(pattern),
                                Customer.email.ilike(pattern), Customer.phone_number.ilike(pattern)))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    customers = (await db.execute(query.order_by(Customer.is_active.desc(), Customer.name).limit(30))).scalars().all()
    # what each one still owes (its open Faturas)
    due: dict = {}
    if customers:
        accepts = {code for code, ok in (await db.execute(select(DocumentType.code, DocumentType.accepts_receipt))).all() if ok}
        types = [InvoiceType(t) for t, code in DOC_CODE_BY_INVOICE_TYPE.items() if code in accepts]
        invoices = (await db.execute(select(Invoice).where(
            Invoice.company_id == company_id, Invoice.customer_id.in_([c.id for c in customers]),
            Invoice.invoice_type.in_(types), Invoice.document_status != DocumentLifecycleStatus.ANULADO))).scalars().all()
        await attach_amount_due(db, invoices)
        for inv in invoices:
            due[inv.customer_id] = due.get(inv.customer_id, 0.0) + inv.amount_due
    return {
        "total_encontrados": total, "mostrados": len(customers),
        "clientes": [{"codigo": c.customer_code, "nome": c.name, "nif": c.nif, "telefone": c.phone_number, "email": c.email,
                      "cidade": c.city, "ativo": c.is_active, "consumidor_final": c.is_final_consumer,
                      "entidade_comparticipante": bool(getattr(c, "is_insurer", False)),
                      "por_receber": _money(due.get(c.id))} for c in customers],
    }


async def consultar_documento(db: AsyncSession, company_id: uuid.UUID, arguments: dict) -> dict:
    from app.services.invoice_service import attach_amount_due
    text = " ".join(str(arguments.get("numero") or "").upper().split())
    if "/" not in text:
        raise ToolError("Indique o número completo do documento, por exemplo FT2026/2")
    series, _, number = text.rpartition("/")
    series = series.split(" ")[-1]
    try:
        number = int(number)
    except ValueError:
        raise ToolError("Número de documento inválido")
    invoice = (await db.execute(select(Invoice).where(
        Invoice.company_id == company_id, func.upper(Invoice.series) == series, Invoice.number == number))).scalars().first()
    if invoice is None:
        return {"nota": f"Documento {text} não encontrado"}
    await attach_amount_due(db, [invoice])
    customer = await db.get(Customer, invoice.customer_id) if invoice.customer_id else None
    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id).limit(40))).scalars().all()
    payments = (await db.execute(
        select(PaymentMethodCatalog.name, Payment.amount).join(PaymentMethodCatalog, PaymentMethodCatalog.id == Payment.payment_method_id)
        .where(Payment.invoice_id == invoice.id, Payment.company_id == company_id))).all()
    return {
        "documento": _reference(invoice), "data": invoice.business_date.isoformat(),
        "cliente": customer.name if customer and customer.company_id == company_id else "Consumidor final",
        "total": _money(invoice.total), "sem_iva": _money(invoice.subtotal), "iva": _money(invoice.vat_total),
        "estado": invoice.document_status.value, "envio_agt": invoice.status.value,
        "vencimento": invoice.due_date.isoformat() if invoice.due_date else None,
        "por_receber": _money(getattr(invoice, "amount_due", 0)),
        "linhas": [{"artigo": l.product_name_snapshot, "quantidade": _qty(l.quantity), "unidade": l.unit_code_snapshot,
                    "preco": _money(l.unit_price), "total": _money(l.line_total)} for l in lines],
        "pagamentos": [{"metodo": m, "valor": _money(v)} for m, v in payments],
        "observacoes": invoice.observations,
    }


# ---------- The catalog offered to the AI

_PERIOD = {
    "data_inicio": {"type": "string", "description": "Primeiro dia, AAAA-MM-DD"},
    "data_fim": {"type": "string", "description": "Último dia, AAAA-MM-DD (o mesmo dia para um só dia)"},
}

TOOLS = [
    ("consultar_stock", "stock:view", consultar_stock,
     "Stock de um produto (por nome, código, código de barras ou substância ativa): quantidade total e por armazém, "
     "lotes com validade, preço de venda e stock mínimo.",
     {"type": "object", "properties": {"pesquisa": {"type": "string", "description": "Nome, código ou substância"}},
      "required": ["pesquisa"]}),
    ("resumo_vendas", "invoices:view", resumo_vendas,
     "Vendas de um período: total com e sem IVA, número de documentos, por atividade e recebimentos por método de pagamento.",
     {"type": "object", "properties": _PERIOD, "required": ["data_inicio", "data_fim"]}),
    ("produtos_mais_vendidos", "invoices:view", produtos_mais_vendidos,
     "Os artigos mais vendidos de um período, por valor, com a quantidade.",
     {"type": "object", "properties": {**_PERIOD, "limite": {"type": "integer", "description": "Quantos (máx. 30)"}},
      "required": ["data_inicio", "data_fim"]}),
    ("alertas_stock", "stock:view", alertas_stock,
     "Produtos abaixo do stock mínimo e lotes expirados ou a expirar nos próximos N dias.",
     {"type": "object", "properties": {"dias": {"type": "integer", "description": "Dias à frente para as validades (30 por omissão)"}}}),
    ("clientes_em_divida", "invoices:view", clientes_em_divida,
     "Dinheiro por receber dos clientes: faturas não pagas por cliente, com o que está vencido.",
     {"type": "object", "properties": {"cliente": {"type": "string", "description": "Parte do nome de um cliente (opcional)"}}}),
    ("fornecedores_a_pagar", "purchases:view", fornecedores_a_pagar,
     "Dinheiro a pagar aos fornecedores: faturas de compra não pagas por fornecedor, com o que está vencido.",
     {"type": "object", "properties": {}}),
    ("caixas", "tesouraria:overview", caixas,
     "As caixas: abertas ou fechadas, quem abriu, e o numerário em cada gaveta.",
     {"type": "object", "properties": {}}),
    ("consultar_clientes", "customers:view", consultar_clientes,
     "Os clientes da empresa (todos, ou por nome, NIF, código, email ou telefone): contactos e o que cada um deve. "
     "Mostra no máximo 30 - com mais, indica o total e sugere uma pesquisa.",
     {"type": "object", "properties": {"pesquisa": {"type": "string", "description": "Parte do nome, NIF... (vazio = todos)"}}}),
    ("consultar_documento", "invoices:view", consultar_documento,
     "Um documento pelo seu número (ex.: FT2026/2, FR2026/6): cliente, linhas, totais, pagamentos e o que falta receber.",
     {"type": "object", "properties": {"numero": {"type": "string", "description": "Número, ex.: FT2026/2"}},
      "required": ["numero"]}),
]


def tools_for(permissions: set[str]) -> list[dict]:
    """The tools the user's role may use, in the provider-neutral format."""
    return [{"name": name, "description": description, "parameters": parameters}
            for name, permission, _, description, parameters in TOOLS if permission in permissions]


async def run_tool(db: AsyncSession, company_id: uuid.UUID, permissions: set[str], name: str, arguments: dict) -> str:
    """Runs one tool for the signed-in user's company and returns its result as JSON text for the AI. A tool the role may
    not use, unknown or refused, answers with an error the AI can explain - never an exception."""
    entry = next((t for t in TOOLS if t[0] == name), None)
    if entry is None or entry[1] not in permissions:
        return json.dumps({"erro": "Ferramenta não disponível para este utilizador"}, ensure_ascii=False)
    try:
        result = await entry[2](db, company_id, arguments or {})
    except ToolError as e:
        result = {"erro": str(e)}
    except (ValueError, TypeError):
        result = {"erro": "Argumentos inválidos"}
    return json.dumps(result, ensure_ascii=False, default=str)
