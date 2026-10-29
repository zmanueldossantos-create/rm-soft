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
            detail=f"O tipo de documento {rules.code} não pode ser emitido neste ecrã",
        )


async def ensure_may_bill_later(db: AsyncSession, user, invoice_type) -> None:
    """At the POS, a document that is not paid on issue (a Fatura billed later) needs the extra permission
    pos:checkout_ft on top of pos:checkout - so a company can let its cashiers sell Fatura/Recibo only."""
    rules = await get_document_rules(db, invoice_type)
    if rules.paid_on_issue:
        return
    if not await has_permission(db, user.company_id, user.role.value, "pos:checkout_ft"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Não tem permissão para faturar (FT) na caixa")


async def ensure_line_prices(db: AsyncSession, user, lines, pos_id=None) -> None:
    """«Preço 2 / Preço 3» and the free price of a line: the gestor always may; at the Caixa, the cashier only on a
    till that allows it (set by the gestor on the till, like the billetage - not a profile permission, whatever the
    plan); in the Faturas (no till) only the gestor. The prices themselves are always read / checked by the server."""
    levels = any((getattr(line, "price_level", 1) or 1) > 1 for line in lines or [])
    free = any(getattr(line, "free_price", None) is not None for line in lines or [])
    if not (levels or free):
        return
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role == "GESTOR":
        return
    if pos_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Só o gestor pode escolher o Preço 2 / Preço 3 ou um preço livre na fatura")
    from app.models.point_of_sale import PointOfSale
    pos = await db.get(PointOfSale, pos_id)
    if pos is None or pos.company_id != user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ponto de venda não encontrado")
    if levels and not pos.allow_price_levels:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Esta caixa não permite escolher o Preço 2 ou o Preço 3")
    if free and not pos.allow_free_price:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Esta caixa não permite alterar o preço")
