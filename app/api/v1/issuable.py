"""A document type can only be issued from the screens the catalog allows (issuable_in_invoices / issuable_at_pos)."""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_rules import DocumentRulesNotFoundError, get_document_rules
from app.services.permission_service import has_permission


async def ensure_issuable(db: AsyncSession, invoice_type, channel: str) -> None:
    """channel: "invoices" (Nova Fatura / Faturas) or "pos" (Caixa). Raises a 422 when the type is not allowed there."""
    try:
        rules = await get_document_rules(db, invoice_type)
    except DocumentRulesNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    allowed = rules.issuable_in_invoices if channel == "invoices" else rules.issuable_at_pos
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"O tipo de documento {rules.code} nao pode ser emitido neste ecra",
        )


async def ensure_may_bill_later(db: AsyncSession, user, invoice_type) -> None:
    """At the POS, a document that is not paid on issue (a Fatura billed later) needs the extra permission
    pos:checkout_ft on top of pos:checkout - so a company can let its cashiers sell Fatura/Recibo only."""
    rules = await get_document_rules(db, invoice_type)
    if rules.paid_on_issue:
        return
    if not await has_permission(db, user.company_id, user.role.value, "pos:checkout_ft"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nao tem permissao para faturar (FT) na caixa")
