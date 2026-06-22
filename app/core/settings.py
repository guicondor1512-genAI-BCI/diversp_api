"""Configuração central do backend, carregada de variáveis de ambiente / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Postgres ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@db:5432/threads",
        alias="DATABASE_URL",
    )
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")

    # --- Redis (cache de leituras quentes) ---
    redis_url: str = Field(default="redis://cache:6379/0", alias="REDIS_URL")
    cache_ttl_feed: int = Field(default=30, alias="CACHE_TTL_FEED")
    cache_ttl_profile: int = Field(default=60, alias="CACHE_TTL_PROFILE")

    # --- Auth ---
    jwt_secret: str = Field(default="dev-secret-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")

    # --- Site ---
    site_url: str = Field(default="http://localhost:8000", alias="SITE_URL")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
