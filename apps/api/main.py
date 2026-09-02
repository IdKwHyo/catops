"""Stable ASGI entrypoint used by Docker and local development."""

from .app.main import app

__all__ = ["app"]
