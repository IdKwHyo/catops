"""Environment-backed application configuration without extra settings dependencies."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote_plus


def _env(primary: str, *aliases: str, default: str | None = None) -> str | None:
    for name in (primary, *aliases):
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    direct = os.getenv("CATALOGOPS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if direct:
        if direct.startswith("postgres://"):
            return direct.replace("postgres://", "postgresql+psycopg://", 1)
        if direct.startswith("postgresql://") and "+" not in direct.split("://", 1)[0]:
            return direct.replace("postgresql://", "postgresql+psycopg://", 1)
        return direct

    host = os.getenv("DB_HOST")
    if host:
        user = quote_plus(os.getenv("DB_USER", "catalogops"))
        password = quote_plus(os.getenv("DB_PASSWORD", "catalogops"))
        port = os.getenv("DB_PORT", "5432")
        name = quote_plus(os.getenv("DB_NAME", "catalogops"))
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"

    return "sqlite:///./catalogops.db"


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = (
        _env("CATALOGOPS_APP_NAME", "APP_NAME", default="CatalogOps API") or "CatalogOps API"
    )
    environment: str = _env("CATALOGOPS_ENV", "APP_ENV", default="development") or "development"
    api_prefix: str = "/api/v1"
    database_url: str = _database_url()
    redis_url: str | None = _env("REDIS_URL")
    auto_seed: bool = _as_bool(os.getenv("CATALOGOPS_AUTO_SEED"), True)
    auto_match_threshold: float = float(
        _env("CATALOGOPS_AUTO_MATCH_THRESHOLD", "AUTO_MATCH_THRESHOLD", default="0.85") or "0.85"
    )
    review_threshold: float = float(
        _env("CATALOGOPS_REVIEW_THRESHOLD", "REVIEW_THRESHOLD", default="0.55") or "0.55"
    )
    model_version: str = (
        _env("CATALOGOPS_MODEL_VERSION", "MODEL_VERSION", default="catalogops-lexical-v1")
        or "catalogops-lexical-v1"
    )
    model_backend: str = _env("CATALOGOPS_MODEL_BACKEND", default="baseline") or "baseline"
    matcher_artifact_path: str | None = _env(
        "CATALOGOPS_MATCHER_ARTIFACT_PATH", "MATCHER_ARTIFACT_PATH"
    )
    cors_origins_raw: str = (
        _env(
            "CATALOGOPS_CORS_ORIGINS",
            "CORS_ORIGINS",
            default=(
                "http://localhost:8080,http://localhost:3000,http://localhost:5173,"
                "http://127.0.0.1:5173"
            ),
        )
        or ""
    )

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins_raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not 0 < settings.review_threshold < settings.auto_match_threshold <= 1:
        raise RuntimeError(
            "Threshold policy must satisfy 0 < REVIEW_THRESHOLD < AUTO_MATCH_THRESHOLD <= 1"
        )
    return settings
