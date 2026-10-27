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

    # --- Mode SaaS : une adresse par entreprise (<sous-domaine>.BASE_DOMAIN), la plateforme sur ADMIN_SUBDOMAIN ---
    # En developpement, <sous-domaine>.localhost fonctionne aussi (Chrome, sans DNS).
    BASE_DOMAIN: str = "rmsystem.co.ao"
    ADMIN_SUBDOMAIN: str = "admin"

    # --- Separation par secteur (voir app.core.capabilities) ---
    # False (defaut) : toutes les permissions d une entreprise fonctionnent, quels que soient ses modules.
    # True : une permission dont la fonction n est donnee par aucun module actif de l entreprise est
    # refusee (GESTOR compris) et retiree de /permissions/mine et de la matrice.
    ENFORCE_CAPABILITIES: bool = False

    # --- Base de donnees ---
    DATABASE_URL: str

    # --- Redis / Celery ---
    # Empty on the Windows installation (no Redis there: AGT_QUEUE=base).
    REDIS_URL: str | None = None

    # --- File d'envoi AGT ---
    # celery : Celery + Redis (Docker, SaaS). base : la base de donnees est la file - une boucle du serveur envoie les
    # documents dus et reessaie (installation Windows RMSOFT-Setup.exe, sans Redis). Voir app/services/agt_queue.py.
    AGT_QUEUE: str = "celery"

    # --- Ecrans servis par le backend lui-meme (installation Windows, sans Caddy) : le dossier du build du frontend ---
    FRONTEND_DIR: str | None = None

    # --- Site public (rmsystem.co.ao) : les routes /api/v1/public (plans, secteurs, contacts) - la plateforme SaaS
    # seulement ; sur le serveur d'un client elles n'existent pas (404).
    PUBLIC_SITE: bool = False

    # --- Authentification JWT (connexion par numero de telephone) ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Assistant IA sur Telegram ---
    # Mode local : l application lit elle-meme les messages du bot (aucune adresse publique necessaire).
    # Mode SaaS : Telegram appelle le webhook. False pour couper la lecture (un seul serveur par bot).
    TELEGRAM_POLLING: bool = True

    # --- Copies de securite des entreprises (company_backup_jobs) ---
    # Le dossier des copies : jamais sous uploads/ (servi par le web). En local, de preference un disque externe ou un
    # dossier reseau. BACKUP_LOOP=false : ce serveur ne fait pas les copies automatiques (un autre s'en charge).
    BACKUP_DIR: str = "backups"
    BACKUP_LOOP: bool = True

    # --- Notificacoes (app/services/notification_service.py) : false = ce serveur n'envoie pas la file des notifications
    NOTIFICATION_LOOP: bool = True

    # --- Licence (app/core/license.py) ---
    # Serveur d un client (installation locale) : LICENSE_REQUIRED=true - le plan, les limites et les dates viennent du
    # fichier de licence signe par RM SOFT (sans licence valide : 7 jours, puis lecture seule). False : le contrat de la
    # base (la plateforme, le developpement).
    LICENSE_REQUIRED: bool = False
    # La plateforme RM SOFT seulement : la cle privee qui signe les licences (python -m app.tools.license_keys).
    LICENSE_PRIVATE_KEY: str | None = None

    # --- Relé da API pública (app/services/relay_service.py) : la plateforme RM SOFT seulement - elle relaie l'API des
    # entreprises installees en local (leur serveur vient chercher les demandes). False partout ailleurs.
    RELAY_SERVER: bool = False
    # Le serveur d'un client : son agent du relais (Integracao API -> Ligacao ao rele). False : jamais lance ici.
    RELAY_AGENT_LOOP: bool = True

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
