"""SQLAlchemy engine, session, and schema initialization."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Imported lazily so model metadata is populated before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        # The application never exposes update/delete operations for audit rows, and
        # these triggers also protect the invariant from accidental direct ORM writes.
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                    BEFORE UPDATE ON audit_events
                    BEGIN
                      SELECT RAISE(ABORT, 'audit events are immutable');
                    END
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                    BEFORE DELETE ON audit_events
                    BEGIN
                      SELECT RAISE(ABORT, 'audit events are immutable');
                    END
                    """
                )
            )
    elif engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION catalogops_reject_audit_mutation()
                    RETURNS trigger AS $$
                    BEGIN
                      RAISE EXCEPTION 'audit events are immutable';
                    END;
                    $$ LANGUAGE plpgsql
                    """
                )
            )
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'audit_events_no_mutation'
                          AND tgrelid = 'audit_events'::regclass
                      ) THEN
                        CREATE TRIGGER audit_events_no_mutation
                        BEFORE UPDATE OR DELETE ON audit_events
                        FOR EACH ROW EXECUTE FUNCTION catalogops_reject_audit_mutation();
                      END IF;
                    END
                    $$
                    """
                )
            )
