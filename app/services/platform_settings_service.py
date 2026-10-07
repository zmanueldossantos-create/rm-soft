"""
Business logic for platform-wide settings (single row, SUPER_ADMIN only).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_settings import PlatformSettings


async def get_or_create_platform_settings(db: AsyncSession) -> PlatformSettings:
    """Returns the single settings row, creating it on first access."""
    result = await db.execute(select(PlatformSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = PlatformSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def update_platform_settings(
    db: AsyncSession,
    software_validation_number: str | None,
    vendor_tax_id: str | None,
    product_id: str | None,
    product_version: str | None,
) -> PlatformSettings:
    """Updates the platform-wide SAF-T vendor identification fields."""
    settings = await get_or_create_platform_settings(db)
    settings.software_validation_number = software_validation_number
    settings.vendor_tax_id = vendor_tax_id
    settings.product_id = product_id
    settings.product_version = product_version
    await db.commit()
    await db.refresh(settings)
    return settings
