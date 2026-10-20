"""
The PDF of a sales document (A4 or 80 mm ticket), as the Faturas and Caixa screens print it - shared by the download
route and the AI assistant's sending by email. Every print counts (the "Original" / "2.ª via" mention).
"""
import uuid

from num2words import num2words
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from app.models.company import Company
from app.models.company_bank_account import CompanyBankAccount
from app.models.customer import Customer
from app.models.document_type import DocumentType
from app.models.invoice import Invoice
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.payment_term import PaymentTerm
from app.models.product import Product
from app.models.service import Service
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.user import User
from app.services.invoice_service import get_invoice_with_lines
from app.utils.pdf_generator import generate_invoice_pdf_a4, generate_invoice_pdf_thermal


def _line_lots(line, doc_lots: dict, guide_lots: dict, printed: set) -> list[str]:
    """The lots printed under one line of the document - once per product (and guide)."""
    if not line.product_id:
        return []
    source = guide_lots.get(line.goods_movement_id, {}) if getattr(line, "goods_movement_id", None) else doc_lots
    key = (line.product_id, getattr(line, "goods_movement_id", None))
    if key in printed:
        return []
    printed.add(key)
    return source.get(line.product_id, [])


async def render_invoice_pdf(db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID,
                             format: str = "thermal") -> tuple[bytes, str]:
    """(the PDF, its file name) - format a4 or thermal. Raises InvoiceNotFoundError."""
    invoice, lines = await get_invoice_with_lines(db, company_id, invoice_id)  # InvoiceNotFoundError for another company's

    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one()

    customer = None
    if invoice.customer_id:
        customer_result = await db.execute(select(Customer).where(Customer.id == invoice.customer_id))
        customer_obj = customer_result.scalar_one_or_none()
        if customer_obj:
            customer = {"name": customer_obj.name, "nif": customer_obj.nif, "address": customer_obj.address}

    payment_method_name = None
    if invoice.payment_method_id:
        pm_result = await db.execute(select(PaymentMethodCatalog).where(PaymentMethodCatalog.id == invoice.payment_method_id))
        pm = pm_result.scalar_one_or_none()
        payment_method_name = pm.name if pm else None

    payment_term_name = None
    if invoice.payment_term_id:
        pt_result = await db.execute(select(PaymentTerm).where(PaymentTerm.id == invoice.payment_term_id))
        pt = pt_result.scalar_one_or_none()
        payment_term_name = pt.name if pt else None

    # Show ALL of the company's active bank accounts, not just the one chosen for this
    # specific invoice - matches the Kiami reference, where the footer always lists every
    # known account regardless of which one the customer is expected to use.
    bank_accounts_result = await db.execute(
        select(CompanyBankAccount, Bank)
        .join(Bank, Bank.id == CompanyBankAccount.bank_id)
        .where(CompanyBankAccount.company_id == company_id, CompanyBankAccount.is_active == True)
    )
    bank_accounts_list = [
        {"acronym": bank.acronym, "account_number": ba.account_number, "iban": ba.iban}
        for ba, bank in bank_accounts_result.all()
    ]

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.id == invoice.document_type_id))
    doc_type_row = doc_type_result.scalar_one_or_none()
    is_fiscal_doc = doc_type_row.is_fiscal if doc_type_row else True

    # Amount in words (Kiami-style "Total: SEIS MILHOES E ...") - integer part only, since
    # AOA has no minor-unit convention commonly spelled out on these documents.
    # the whole amount in words, centimos included: 615,60 -> SEISCENTOS E QUINZE KWANZAS E SESSENTA CENTIMOS
    kwanzas, centimos = divmod(int(round(float(invoice.total) * 100)), 100)
    try:
        amount_in_words = num2words(kwanzas, lang="pt").upper() + (" KWANZA" if kwanzas == 1 else " KWANZAS")
        if centimos:
            amount_in_words += " E " + num2words(centimos, lang="pt").upper() + (" CÊNTIMO" if centimos == 1 else " CÊNTIMOS")
    except Exception:
        amount_in_words = None

    # Increment BEFORE building the "via" label so this very printout gets the correct
    # ordinal - the 1st ever call prints "Original", every one after that "Nº via" (see
    # print_count comment on the Invoice model for the legal requirement behind this).
    invoice.print_count = (invoice.print_count or 0) + 1
    await db.commit()


    INVOICE_TYPE_CODE = {
        "FACTURA": "FT", "FACTURA_RECIBO": "FR", "NOTA_CREDITO": "NC",
        "NOTA_DEBITO": "ND", "RECIBO": "RC", "PRO_FORMA": "FP", "ORCAMENTO": "OR",
    }

    # The referenced original invoice - RC/NC/ND all point back to one via reference_invoice_id.
    # RC (Recibo) needs it to render its own table row (it carries no product/service lines of its
    # own - see create_receipt docstring); NC/ND already had document_reference free text, but
    # fetching it directly here is more reliable than depending on that optional field.
    reference_invoice_dict = None
    if invoice.reference_invoice_id:
        ref_result = await db.execute(select(Invoice).where(Invoice.id == invoice.reference_invoice_id))
        ref_invoice = ref_result.scalar_one_or_none()
        if ref_invoice is not None:
            reference_invoice_dict = {
                "invoice_type": INVOICE_TYPE_CODE.get(ref_invoice.invoice_type.value, ref_invoice.invoice_type.value),
                "series": ref_invoice.series,
                "number": ref_invoice.number,
                "business_date": str(ref_invoice.business_date),
                "subtotal": float(ref_invoice.subtotal),
                "vat_total": float(ref_invoice.vat_total),
                "total": float(ref_invoice.total),
            }

    # The payments actually recorded on the document (a mixed payment has several), with the official AGT name
    # of their method - shown on the A4 invoice under "Meios de pagamento".
    from app.models.payment import Payment
    payment_rows = await db.execute(
        select(PaymentMethodCatalog.name, Payment.amount)
        .join(Payment, Payment.payment_method_id == PaymentMethodCatalog.id)
        .where(Payment.invoice_id == invoice.id)
        .order_by(Payment.created_at)
    )
    payments_list = [{"name": name, "amount": float(amount)} for name, amount in payment_rows.all()]

    created_by_name = None
    if invoice.created_by_user_id is not None:
        created_by_name = (await db.execute(select(User.full_name).where(User.id == invoice.created_by_user_id))).scalar_one_or_none()

    invoice_dict = {
        "invoice_type": INVOICE_TYPE_CODE.get(invoice.invoice_type.value, invoice.invoice_type.value),
        "series": invoice.series,
        "number": invoice.number,
        "business_date": str(invoice.business_date),
        "due_date": str(invoice.due_date) if invoice.due_date else None,
        "valid_until": invoice.valid_until,  # an orçamento
        "payment_date": str(invoice.payment_date) if invoice.payment_date else None,
        "subtotal": float(invoice.subtotal),
        "vat_total": float(invoice.vat_total),
        "total": float(invoice.total),
        "retention_total": float(invoice.retention_total or 0),
        "discount_global_percent": float(invoice.discount_global_percent or 0),
        "document_reference": invoice.document_reference,
        "credit_note_reason": invoice.credit_note_reason.value if invoice.credit_note_reason else None,
        "credit_note_cause": invoice.credit_note_cause,
        "observations": invoice.observations,
        "payment_method_name": payment_method_name,
        "payment_term_name": payment_term_name,
        "print_count": invoice.print_count,
        "is_fiscal_doc": is_fiscal_doc,
        "amount_in_words": amount_in_words,
        "atcud": invoice.atcud,
        "invoice_hash": invoice.invoice_hash,
        "qr_code_data": invoice.qr_code_data,
        "reference_invoice": reference_invoice_dict,
        "created_at": invoice.created_at,  # the time of recording: "Data de emissao: 08/10/2026 - 15h45"
        "payments": payments_list,
        "created_by_name": created_by_name,  # the ticket's "Atendido por"
    }
    # Farmácia: the receita the sale was dispensed against, printed under the lines.
    from app.models.prescription import Prescription
    from app.services.pharmacy_service import prescription_text
    invoice_dict["prescription"] = prescription_text((await db.execute(
        select(Prescription).where(Prescription.invoice_id == invoice.id))).scalar_one_or_none())
    # The lots the goods left in, printed under each line of a product followed by lot: the sale's own exits, or the
    # guides the invoice bills (their goods left with the guide).
    from app.services.stock_lot_service import lots_of_document
    doc_lots = await lots_of_document(db, company_id, f"{invoice_dict['invoice_type']} {invoice.series}/{invoice.number}")
    guide_ids = {l.goods_movement_id for l in lines if getattr(l, "goods_movement_id", None)}
    guide_lots: dict = {}
    if guide_ids:
        from app.models.goods_movement import GoodsMovement
        from app.services.goods_movement_service import reference as guide_reference
        for guide in (await db.execute(select(GoodsMovement).where(GoodsMovement.id.in_(guide_ids)))).scalars().all():
            guide_lots[guide.id] = await lots_of_document(db, company_id, guide_reference(guide), guide.origin_warehouse_id)
    lots_printed: set = set()  # a product on two lines: its lots under the first one
    product_ids = [l.product_id for l in lines if l.product_id]
    service_ids = [l.service_id for l in lines if l.service_id]
    products_by_id = {}
    if product_ids:
        products_result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
        products_by_id = {p.id: p for p in products_result.scalars().all()}
    services_by_id = {}
    if service_ids:
        services_result = await db.execute(select(Service).where(Service.id.in_(service_ids)))
        services_by_id = {s.id: s for s in services_result.scalars().all()}
    # Products AND services carry a unit of measure (a service line used to print "-").
    unit_ids = [x.unit_of_measure_id for x in [*products_by_id.values(), *services_by_id.values()] if getattr(x, "unit_of_measure_id", None)]
    units_by_id = {}
    if unit_ids:
        units_result = await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.id.in_(unit_ids)))
        units_by_id = {u.id: u for u in units_result.scalars().all()}

    lines_dict = []
    for l in lines:
        code = "-"
        unit = "-"
        if l.product_id and l.product_id in products_by_id:
            p = products_by_id[l.product_id]
            code = p.code
            if p.unit_of_measure_id and p.unit_of_measure_id in units_by_id:
                unit = units_by_id[p.unit_of_measure_id].code
        elif l.service_id and l.service_id in services_by_id:
            svc = services_by_id[l.service_id]
            code = svc.code
            svc_unit_id = getattr(svc, "unit_of_measure_id", None)
            if svc_unit_id and svc_unit_id in units_by_id:
                unit = units_by_id[svc_unit_id].code
        lines_dict.append({
            "code": code,
            "unit": unit,
            "service_line": l.service_id is not None,  # the A4's Tipo column: S for a service, P for a product (as the SAF-T)
            "product_name_snapshot": l.product_name_snapshot,
            "quantity": float(l.quantity), "unit_code": l.unit_code_snapshot,
            "unit_price": float(l.unit_price),
            "discount_percent": float(l.discount_percent or 0),
            "vat_rate_snapshot": float(l.vat_rate_snapshot),
            "line_subtotal": float(l.line_subtotal),
            "line_total": float(l.line_total),
            "exemption_code": l.exemption_code, "exemption_reason": l.exemption_reason_snapshot,
            "iec_amount": float(l.iec_amount or 0),
            "iselo_amount": float(l.iselo_amount or 0),
            "lots": _line_lots(l, doc_lots, guide_lots, lots_printed),
        })
    company_dict = {"name": company.name, "nif": company.nif, "address": company.address, "phone_number": company.phone_number, "phone_number_2": company.phone_number_2, "email": company.email, "website": company.website, "logo_path": company.logo_path, "bank_accounts": bank_accounts_list}

    if format == "a4":
        pdf_bytes = generate_invoice_pdf_a4(invoice_dict, lines_dict, company_dict, customer)
    else:
        pdf_bytes = generate_invoice_pdf_thermal(invoice_dict, lines_dict, company_dict, customer)

    return pdf_bytes, f"{invoice.series}-{invoice.number}-{format}.pdf"
