"""
Farmácia, livraison 4 - insurers and agreements (comparticipação).

An insurer is a customer marked is_insurer (ENSA, Fidelidade, a company with a convénio), with its default share
(insurer_coverage_pct) and whether it covers the medicines only (insurer_medicines_only - the parapharmacy is then the
patient's alone). A sale at the counter shared with it gives two ordinary fiscal documents, in one transaction:

- the patient's document (the Fatura-Recibo chosen at the counter): every line at the patient's part of its price - a
  line the insurer does not cover at its full price. It hands the goods over (the stock leaves with it) and carries
  the receita; the counter's global discount is the patient's;
- the insurer's Fatura: the covered lines at the insurer's part (price x share, to the cent), paid later by a receipt
  (Recibo); it moves no stock. With a 100 % share the insurer's Fatura is the only document, and it moves the stock.

Each document names the other in its observations; an InsuranceShare row links them with the beneficiary's card - the
monthly statement per insurer is built from it.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.insurance_share import InsuranceShare
from app.models.invoice import Invoice
from app.models.product import Product
from app.models.service import Service
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
from app.services.pharmacy_service import MedicineError, pharmacy_enabled


class InsuranceError(MedicineError):
    """A shared sale or an insurer's sheet that cannot be saved (a 422, see main.py)."""


def _reference(invoice: Invoice) -> str:
    return f"{DOC_CODE_BY_INVOICE_TYPE.get(invoice.invoice_type.value, 'FT')} {invoice.series}/{invoice.number}"


async def insurer_fields(db: AsyncSession, company_id: uuid.UUID, insurer: dict | None, is_final_consumer: bool) -> dict:
    """The insurer fields of a customer sheet, checked: only for a company with the Farmácia, never the Consumidor
    final, a share between 0 (excluded) and 100 %."""
    if not insurer or not insurer.get("is_insurer"):
        return {"is_insurer": False, "insurer_coverage_pct": None, "insurer_medicines_only": True}
    if not await pharmacy_enabled(db, company_id):
        raise InsuranceError("A empresa não tem o setor Farmácia: um cliente não pode ser uma entidade comparticipante")
    if is_final_consumer:
        raise InsuranceError("O Consumidor final não pode ser uma entidade comparticipante")
    pct = insurer.get("insurer_coverage_pct")
    if pct is None or not 0 < float(pct) <= 100:
        raise InsuranceError("A taxa de comparticipação deve estar entre 0 e 100 %")
    return {"is_insurer": True, "insurer_coverage_pct": round(float(pct), 2),
            "insurer_medicines_only": bool(insurer.get("insurer_medicines_only", True))}


def split_price(price: float, pct: float) -> tuple[float, float]:
    """(insurer's part, patient's part) of a unit price - the insurer's to the cent, the patient's the rest: the two
    always add up to the price."""
    insurer = round(price * pct / 100, 2)
    return insurer, round(price - insurer, 2)


async def _line_prices(db: AsyncSession, company_id: uuid.UUID, lines_input: list[dict]) -> list[tuple[float, bool]]:
    """(unit price, is a medicine) of each sale line - the price the invoice would charge (its sale unit's)."""
    from app.services.invoice_service import ProductNotFoundError, _sale_unit_for_line
    out = []
    for line in lines_input:
        if line.get("service_id"):
            service = (await db.execute(select(Service).where(
                Service.id == line["service_id"], Service.company_id == company_id))).scalar_one_or_none()
            if service is None:
                raise ProductNotFoundError("Serviço não encontrado ou inativo")
            out.append((float(service.price or 0), False))
            continue
        product = (await db.execute(select(Product).where(
            Product.id == line.get("product_id"), Product.company_id == company_id))).scalar_one_or_none()
        if product is None:
            raise ProductNotFoundError("Produto não encontrado ou inativo")
        price, *_ = await _sale_unit_for_line(db, company_id, product, line.get("sale_unit_id"), float(line["quantity"]))
        out.append((float(price), bool(product.is_medicine)))
    return out


async def get_insurer(db: AsyncSession, company_id: uuid.UUID, insurer_id: uuid.UUID) -> Customer:
    insurer = (await db.execute(select(Customer).where(
        Customer.id == insurer_id, Customer.company_id == company_id))).scalar_one_or_none()
    if insurer is None or not insurer.is_insurer:
        raise InsuranceError("Entidade comparticipante não encontrada")
    if not insurer.is_active:
        raise InsuranceError(f"A entidade comparticipante {insurer.name} está inativa")
    return insurer


async def shared_sale(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, cash_session_id: uuid.UUID,
    customer_id: uuid.UUID | None, invoice_type: str, lines_input: list[dict], payments: list[dict] | None,
    insurance: dict, discount_global_percent: float = 0, prescription: dict | None = None,
    observations: str | None = None,
) -> tuple[Invoice | None, Invoice]:
    """
    A counter sale shared with an insurer (see the module docstring). insurance: {insurer_id, card_number,
    beneficiary_name, coverage_pct (empty = the insurer's)}. payments: what the patient pays, his part. Returns
    (the patient's document - None when the insurer pays everything, the insurer's Fatura), both committed.
    """
    from app.services import invoice_service
    from app.services.agt_queue import queue_for_agt

    insurer = await get_insurer(db, company_id, insurance.get("insurer_id"))
    card = " ".join((insurance.get("card_number") or "").split())
    if not card:
        raise InsuranceError("Indique o n.º do cartão do beneficiário")
    beneficiary = " ".join((insurance.get("beneficiary_name") or "").split()) or None
    pct = insurance.get("coverage_pct")
    pct = float(insurer.insurer_coverage_pct or 0) if pct in (None, "") else float(pct)
    if not 0 < pct <= 100:
        raise InsuranceError("A taxa de comparticipação deve estar entre 0 e 100 %")

    prices = await _line_prices(db, company_id, lines_input)
    insurer_lines, patient_lines = [], []
    for line, (price, is_medicine) in zip(lines_input, prices):
        covered = is_medicine or not insurer.insurer_medicines_only
        insurer_part, patient_part = split_price(price, pct) if covered else (0.0, price)
        base = {k: line.get(k) for k in ("product_id", "service_id", "sale_unit_id", "quantity", "discount_percent")}
        if insurer_part > 0:
            insurer_lines.append({**base, "unit_price": insurer_part})
        patient_lines.append({**base, "unit_price": patient_part})
    if not insurer_lines:
        raise InsuranceError(f"Nenhum artigo desta venda é comparticipado por {insurer.name}"
                             + (" (só comparticipa medicamentos)" if insurer.insurer_medicines_only else ""))
    patient_pays = any(l["unit_price"] > 0 for l in patient_lines)

    share_text = f"Comparticipação {insurer.name} {pct:g} % · Cartão n.º {card}" + (f" · {beneficiary}" if beneficiary else "")
    try:
        # the insurer's Fatura: covered lines at its part, paid later; it moves the stock only when it is alone
        insurer_invoice = await invoice_service.create_invoice(
            db, company_id, activity_id, insurer.id, invoice_type="FACTURA", lines_input=insurer_lines,
            business_date=date.today(), payment_term_id=insurer.payment_term_id,
            payment_method_id=insurer.payment_method_id, observations=share_text[:500],
            deduct_stock=not patient_pays, keep_line_prices=True, commit=False,
            prescription=None if patient_pays else prescription,
        )
        patient_invoice = None
        if patient_pays:
            patient_invoice = await invoice_service.create_invoice(
                db, company_id, activity_id, customer_id, invoice_type=invoice_type, lines_input=patient_lines,
                business_date=date.today(), cash_session_id=cash_session_id, payments=payments or None,
                discount_global_percent=discount_global_percent, keep_line_prices=True, commit=False,
                prescription=prescription,
                observations=(((observations + " · ") if observations else "") + share_text
                              + f" · {_reference(insurer_invoice)}")[:500],
            )
            insurer_invoice.observations = (share_text + f" · Utente: {_reference(patient_invoice)}")[:500]
        db.add(InsuranceShare(
            company_id=company_id, insurer_id=insurer.id, insurer_invoice_id=insurer_invoice.id,
            patient_invoice_id=patient_invoice.id if patient_invoice else None, coverage_pct=pct,
            card_number=card[:60], beneficiary_name=beneficiary[:150] if beneficiary else None,
        ))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    for invoice in (insurer_invoice, patient_invoice):
        if invoice is not None:
            await db.refresh(invoice)
            await queue_for_agt(db, invoice)
    return patient_invoice, insurer_invoice


# ---------- The monthly statement per insurer

async def list_shares(db: AsyncSession, company_id: uuid.UUID, date_from: date, date_to: date,
                      insurer_id: uuid.UUID | None = None) -> list[dict]:
    """The shared sales of a period (the insurer's Fatura date), oldest first: the patient's and the insurer's
    documents, the beneficiary and his card, the receita, the patient's part of the covered articles, the insurer's
    amount and what it still owes."""
    from app.models.prescription import Prescription
    from app.services.invoice_service import attach_amount_due
    from app.services.pharmacy_register_service import RegisterError
    if date_to < date_from:
        raise RegisterError("A data final não pode ser anterior à data inicial")
    query = (
        select(InsuranceShare, Invoice, Customer.name)
        .join(Invoice, Invoice.id == InsuranceShare.insurer_invoice_id)
        .join(Customer, Customer.id == InsuranceShare.insurer_id)
        .where(InsuranceShare.company_id == company_id, Invoice.business_date >= date_from, Invoice.business_date <= date_to)
        .order_by(Invoice.business_date, Invoice.number)
    )
    if insurer_id is not None:
        query = query.where(InsuranceShare.insurer_id == insurer_id)
    rows = (await db.execute(query)).all()
    if not rows:
        return []
    await attach_amount_due(db, [inv for _, inv, _ in rows])
    patient_ids = [share.patient_invoice_id for share, _, _ in rows if share.patient_invoice_id]
    patients = {inv.id: inv for inv in (await db.execute(select(Invoice).where(Invoice.id.in_(patient_ids)))).scalars().all()} if patient_ids else {}
    invoice_ids = [*patient_ids, *[share.insurer_invoice_id for share, _, _ in rows]]
    prescriptions = {p.invoice_id: p.number for p in (await db.execute(
        select(Prescription).where(Prescription.invoice_id.in_(invoice_ids)))).scalars().all()}
    # the patient's part of the covered articles only (what the insurer shares), not the rest of his purchase
    from app.models.invoice_line import InvoiceLine
    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id.in_(invoice_ids)))).scalars().all()
    covered_items: dict[uuid.UUID, set] = {}
    for line in lines:
        covered_items.setdefault(line.invoice_id, set()).add((line.product_id, line.service_id))
    covered_patient: dict[uuid.UUID, float] = {}
    for share, _, _ in rows:
        if share.patient_invoice_id:
            items = covered_items.get(share.insurer_invoice_id, set())
            covered_patient[share.patient_invoice_id] = sum(
                float(l.line_total) for l in lines
                if l.invoice_id == share.patient_invoice_id and (l.product_id, l.service_id) in items)
    out = []
    for share, insurer_invoice, insurer_name in rows:
        patient = patients.get(share.patient_invoice_id)
        out.append({
            "id": share.id, "date": insurer_invoice.business_date, "insurer_id": share.insurer_id, "insurer": insurer_name,
            "insurer_invoice_id": insurer_invoice.id, "insurer_reference": _reference(insurer_invoice),
            "patient_invoice_id": patient.id if patient else None, "patient_reference": _reference(patient) if patient else None,
            "patient_amount": covered_patient.get(patient.id, 0.0) if patient else 0.0,
            "card_number": share.card_number, "beneficiary_name": share.beneficiary_name,
            "coverage_pct": float(share.coverage_pct),
            "prescription": prescriptions.get(share.patient_invoice_id) or prescriptions.get(insurer_invoice.id),
            "insurer_amount": float(insurer_invoice.total), "amount_due": float(getattr(insurer_invoice, "amount_due", 0) or 0),
        })
    return out
