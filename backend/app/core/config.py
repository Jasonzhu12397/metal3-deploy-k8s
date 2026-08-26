"""
Application configuration.

All secrets (BMC credentials, SSH keys, CA keys, kubeconfigs, LDAP
passwords, etc.) MUST be supplied via environment variables or a secret
manager (Vault, k8s Secret, SOPS-encrypted file) -- never hard-coded or
committed to source control. The .env.example file documents the shape
of the required configuration without containing real values.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "metal3-deploy-k8s-backend"
    ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://metal3:metal3@localhost:5432/metal3_deploy"

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- Security ---
    SECRET_KEY: str = "CHANGE_ME_IN_ENV"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Seed admin account ---
    # Created automatically on first startup if no users exist yet. If
    # ADMIN_PASSWORD is left unset, a random one is generated and printed to
    # the startup logs ONCE -- there is deliberately no fixed default
    # password to look up. Set ADMIN_PASSWORD explicitly for anything beyond
    # a throwaway local run.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: Optional[str] = None

    # --- Metal3 / Kubernetes ---
    # Path to the kubeconfig for the *management* (bootstrap/ephemeral or
    # permanent CAPI management) cluster that hosts Metal3 + Cluster API.
    MGMT_KUBECONFIG_PATH: Optional[str] = None
    # Namespace where BareMetalHost / Cluster / Machine objects live.
    CAPI_NAMESPACE: str = "metal3"
    # How long to wait for a BMH to reach "available" before failing (s).
    BMH_READY_TIMEOUT: int = 1800
    CLUSTER_PROVISION_TIMEOUT: int = 7200

    # --- Templates ---
    TEMPLATES_DIR: str = "../templates"

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
