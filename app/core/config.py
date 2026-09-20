"""
Configuration centrale de l'application.
Lit les variables d'environnement (.env) et les expose sous forme d'objet Settings.
Un seul point de verite pour DEPLOYMENT_MODE (local | saas) - voir cahier des charges v7, section 2.3.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    APP_NAME: str = "ERP Multisecteurs Angola"
    DEBUG: bool = False
    DEPLOYMENT_MODE: str = "local"  # "local" ou "saas"

    # --- Separation par secteur (voir app.core.capabilities) ---
    # False (defaut) : toutes les permissions d une entreprise fonctionnent, quels que soient ses modules.
    # True : une permission dont la fonction n est donnee par aucun module actif de l entreprise est
    # refusee (GESTOR compris) et retiree de /permissions/mine et de la matrice.
    ENFORCE_CAPABILITIES: bool = False

    # --- Base de donnees ---
    DATABASE_URL: str

    # --- Redis / Celery ---
    REDIS_URL: str

    # --- Authentification JWT (connexion par numero de telephone) ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Licence (mode local uniquement) ---
    LICENSE_NIF: str | None = None

    @property
    def is_saas(self) -> bool:
        return self.DEPLOYMENT_MODE == "saas"

    @property
    def is_local(self) -> bool:
        return self.DEPLOYMENT_MODE == "local"


@lru_cache
def get_settings() -> Settings:
    """Retourne une instance unique (mise en cache) des reglages de l'application."""
    return Settings()
