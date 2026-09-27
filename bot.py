"""Compatibility entry point: uvicorn bot:app; from bot import compose."""
from vera.api import create_app
from vera.composer import compose
app = create_app()
__all__ = ["app", "compose"]
