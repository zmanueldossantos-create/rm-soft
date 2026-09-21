"""A document type can only be issued from the screens the catalog allows (issuable_in_invoices / issuable_at_pos)."""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_rules import DocumentRulesNotFoundError, get_document_rules


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