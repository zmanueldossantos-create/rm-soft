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
            "requires_payment_term": prefs_by_type_id.get(d.id, False),
        }
        for d in catalog
    ]


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