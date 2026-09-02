"""Isolated FastAPI and SQLite fixtures; no external services are required."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.app.config import get_settings
from apps.api.app.database import Base, get_db
from apps.api.app.routes import router
from apps.api.app.seed import seed_demo_data


@pytest.fixture
def db_session_factory(tmp_path):
    database_path = tmp_path / "catalogops-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with factory() as db:
        seed_demo_data(db, get_settings())
    yield factory
    engine.dispose()


@pytest.fixture
def api_client(db_session_factory) -> Generator[TestClient, None, None]:
    application = FastAPI()
    application.include_router(router)

    def override_get_db() -> Generator[Session, None, None]:
        with db_session_factory() as db:
            yield db

    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture
def reviewer_headers() -> dict[str, str]:
    return {"X-Role": "reviewer", "X-Actor": "qa-reviewer"}


@pytest.fixture
def operator_headers() -> dict[str, str]:
    return {"X-Role": "operator", "X-Actor": "qa-operator"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"X-Role": "admin", "X-Actor": "qa-admin"}
