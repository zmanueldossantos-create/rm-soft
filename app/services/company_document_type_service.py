"""
Business logic for CompanyDocumentTypePreference - per-company override of requires_payment_term
(see DocumentType and CompanyDocumentTypePreference docstrings). Managed by each company's own GESTOR.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_type import DocumentType
from app.models.company_document_type_preference import CompanyDocumentTypePreference


async def list_document_type_preferences(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """
    Returns every active DocumentType whose platform catalog sets requires_payment_term (today: FT only),
    each annotated with this company's own override (True/False - absence of a preference row means "follow
    the platform default", i.e. requires_payment_term from the catalog).
    """
    catalog_result = await db.execute(
        select(DocumentType).where(DocumentType.is_active.is_(True), DocumentType.requires_payment_term.is_(True)).order_by(DocumentType.code)
    )
    catalog = list(catalog_result.scalars().all())

    prefs_result = await db.execute(
        select(CompanyDocumentTypePreference).where(CompanyDocumentTypePreference.company_id == company_id)
    )
    prefs_by_type_id = {p.document_type_id: p.requires_payment_term for p in prefs_result.scalars().all()}

    return [
        {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            # No preference row: the company follows the platform catalog (effective_requires_payment_term).
            "requires_payment_term": prefs_by_type_id.get(d.id, d.requires_payment_term),
        }
        for d in catalog
    ]


async def effective_requires_payment_term(db: AsyncSession, company_id: uuid.UUID) -> dict[str, bool]:
    """Document type code -> is the payment term mandatory for this company: its own preference when it set one, else
    the platform catalog. The one rule read by the screens (/document-rules) and by the server on issue."""
    types = (await db.execute(select(DocumentType))).scalars().all()
    prefs = {
        p.document_type_id: p.requires_payment_term
        for p in (await db.execute(
            select(CompanyDocumentTypePreference).where(CompanyDocumentTypePreference.company_id == company_id)
        )).scalars().all()
    }
    return {d.code: prefs.get(d.id, d.requires_payment_term) for d in types}


async def set_document_type_preference(
    db: AsyncSession, company_id: uuid.UUID, document_type_id: uuid.UUID, requires_payment_term: bool,
) -> None:
    result = await db.execute(
        select(CompanyDocumentTypePreference).where(
            CompanyDocumentTypePreference.company_id == company_id,
            CompanyDocumentTypePreference.document_type_id == document_type_id,
        )
    )
    pref = result.scalar_one_or_none()
    if pref is not None:
        pref.requires_payment_term = requires_payment_term
    else:
        db.add(CompanyDocumentTypePreference(
            company_id=company_id, document_type_id=document_type_id, requires_payment_term=requires_payment_term,
        ))
    await db.commit()