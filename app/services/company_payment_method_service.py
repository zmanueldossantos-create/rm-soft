"""
Business logic for CompanyPaymentMethodPreference - which of the 12 AGT
PaymentMethodCatalog codes a company's Caixa screen offers. Managed by
GESTOR, not SUPER_ADMIN (see model docstring).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.company_payment_method_preference import CompanyPaymentMethodPreference


async def list_payment_method_preferences(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """
    Returns every active PaymentMethodCatalog code, each annotated with this
    company's available_at_pos preference (True/False - absence of a
    preference row defaults to False, see model docstring).
    """
    catalog_result = await db.execute(
        select(PaymentMethodCatalog).where(PaymentMethodCatalog.is_active.is_(True)).order_by(PaymentMethodCatalog.code)
    )
    catalog = list(catalog_result.scalars().all())

    prefs_result = await db.execute(
        select(CompanyPaymentMethodPreference).where(CompanyPaymentMethodPreference.company_id == company_id)
    )
    prefs_by_method_id = {p.payment_method_id: p.available_at_pos for p in prefs_result.scalars().all()}

    return [
        {
            "id": m.id,
            "code": m.code,
            "name": m.name,
            "allows_payment": m.allows_payment,
            "allows_receipt": m.allows_receipt,
            "is_cash": m.is_cash,
            "available_at_pos": prefs_by_method_id.get(m.id, False),
        }
        for m in catalog
    ]


async def set_payment_method_preference(
    db: AsyncSession, company_id: uuid.UUID, payment_method_id: uuid.UUID, available_at_pos: bool,
) -> None:
    result = await db.execute(
        select(CompanyPaymentMethodPreference).where(
            CompanyPaymentMethodPreference.company_id == company_id,
            CompanyPaymentMethodPreference.payment_method_id == payment_method_id,
        )
    )
    pref = result.scalar_one_or_none()
    if pref is not None:
        pref.available_at_pos = available_at_pos
    else:
        db.add(CompanyPaymentMethodPreference(
            company_id=company_id, payment_method_id=payment_method_id, available_at_pos=available_at_pos,
        ))
    await db.commit()
