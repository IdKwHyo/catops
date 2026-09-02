"""CatalogOps FastAPI application factory and ASGI object."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import SessionLocal, init_db
from .routes import router
from .seed import seed_demo_data

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    if settings.auto_seed:
        with SessionLocal() as db:
            seed_demo_data(db, settings)
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="CatalogOps API",
        summary="Auditable entity matching and human-review operations",
        description=(
            "Matches messy marketplace offers to canonical products, routes uncertain "
            "decisions to review, and gates operational actions behind approval. Demo "
            "authorization uses X-Role and X-Actor headers."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Role", "X-Actor"],
    )
    application.include_router(router)
    return application


app = create_app()
