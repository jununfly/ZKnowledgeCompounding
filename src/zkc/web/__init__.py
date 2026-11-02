"""ZKC · 本地 web 层（P2.1 起，遵循 ADR-0001：FastAPI + SSR，localhost:8000）。"""
from zkc.web.app import create_app, capture_note, build_routers

__all__ = ["create_app", "capture_note", "build_routers"]
