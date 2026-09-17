"""
Connexion asynchrone a PostgreSQL via SQLAlchemy 2.0.
Un seul moteur, reutilise dans les deux modes de deploiement (local/saas) -
seule DATABASE_URL change selon l environnement (.env).
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Classe de base pour tous les modeles SQLAlchemy du projet."""
    pass


async def get_db():
    """Dependance FastAPI - fournit une session DB par requete, fermee automatiquement."""
    async with AsyncSessionLocal() as session:
        yield session
