"""
Ecrã do cliente (option ECRA_CLIENTE): the settings of the customer's screen of each activity - the welcome message,
how long each picture stays, and its pictures (up to MAX_IMAGES, files under uploads/ecra/<company>/). The screen
reads them (any till user of the company); the gestor changes them (company:manage, Configurações → Atividades).
"""
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.company import Company
from app.models.customer_display import CustomerDisplayImage, CustomerDisplaySettings

OPTION = "ECRA_CLIENTE"
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SLIDE_SECONDS = (3, 60)
DEFAULT_SLIDE_SECONDS = 8
UPLOAD_ROOT = "uploads"


class CustomerDisplayError(Exception):
    """A setting or picture refused - the message is shown to the gestor as it is."""


async def _activity_or_raise(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID) -> Activity:
    activity = await db.get(Activity, activity_id)
    if activity is None or activity.company_id != company_id:
        raise LookupError("Atividade não encontrada")
    return activity


async def read(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID) -> dict:
    """Everything the screen shows when no sale is going on (defaults when the gestor never set anything)."""
    activity = await _activity_or_raise(db, company_id, activity_id)
    company = await db.get(Company, company_id)
    settings = await db.get(CustomerDisplaySettings, activity_id)
    images = (await db.execute(
        select(CustomerDisplayImage).where(CustomerDisplayImage.activity_id == activity_id)
        .order_by(CustomerDisplayImage.created_at, CustomerDisplayImage.id)
    )).scalars().all()
    return {
        "activity_id": str(activity.id),
        "activity_name": activity.name,
        "company_name": company.short_name or company.name,
        "logo": company.logo_path,
        "welcome_message": settings.welcome_message if settings else None,
        "slide_seconds": settings.slide_seconds if settings else DEFAULT_SLIDE_SECONDS,
        "images": [{"id": str(image.id), "url": image.path} for image in images],
        "max_images": MAX_IMAGES,
    }


async def update_settings(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID,
                          welcome_message: str | None, slide_seconds: int) -> dict:
    await _activity_or_raise(db, company_id, activity_id)
    low, high = SLIDE_SECONDS
    if not low <= slide_seconds <= high:
        raise CustomerDisplayError(f"Cada imagem fica entre {low} e {high} segundos")
    message = (welcome_message or "").strip() or None
    if message and len(message) > 200:
        raise CustomerDisplayError("A mensagem tem no máximo 200 caracteres")
    settings = await db.get(CustomerDisplaySettings, activity_id)
    if settings is None:
        settings = CustomerDisplaySettings(activity_id=activity_id, company_id=company_id)
        db.add(settings)
    settings.welcome_message, settings.slide_seconds = message, slide_seconds
    await db.commit()
    return await read(db, company_id, activity_id)


async def add_image(db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, filename: str | None,
                    contents: bytes) -> dict:
    await _activity_or_raise(db, company_id, activity_id)
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise CustomerDisplayError("Formato de imagem inválido - use PNG, JPG ou WEBP")
    if len(contents) > MAX_IMAGE_BYTES:
        raise CustomerDisplayError("Imagem demasiado grande - máximo 2MB")
    count = (await db.execute(select(func.count()).select_from(CustomerDisplayImage)
                              .where(CustomerDisplayImage.activity_id == activity_id))).scalar_one()
    if count >= MAX_IMAGES:
        raise CustomerDisplayError(f"No máximo {MAX_IMAGES} imagens por atividade - apague uma primeiro")
    image_id = uuid.uuid4()
    # the stored name comes from ids only - the sender's file name (accents, spaces...) is never used
    folder = os.path.join(UPLOAD_ROOT, "ecra", str(company_id))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{image_id}{ext}"), "wb") as f:
        f.write(contents)
    db.add(CustomerDisplayImage(id=image_id, company_id=company_id, activity_id=activity_id,
                                path=f"/uploads/ecra/{company_id}/{image_id}{ext}"))
    await db.commit()
    return await read(db, company_id, activity_id)


async def delete_image(db: AsyncSession, company_id: uuid.UUID, image_id: uuid.UUID) -> dict:
    image = await db.get(CustomerDisplayImage, image_id)
    if image is None or image.company_id != company_id:
        raise LookupError("Imagem não encontrada")
    activity_id = image.activity_id
    file_path = os.path.join(UPLOAD_ROOT, *image.path.removeprefix("/uploads/").split("/"))
    await db.delete(image)
    await db.commit()
    if os.path.exists(file_path):
        os.remove(file_path)
    return await read(db, company_id, activity_id)
