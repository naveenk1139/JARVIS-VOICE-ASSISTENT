"""FastAPI application: the browser front door.

The server is a thin adapter over :class:`jarvis.engine.Engine`. Speech
recognition and synthesis happen in the browser (Web Speech API), so the server
only exchanges text/JSON - which keeps it usable from any phone or laptop on the
same network, with no microphone drivers to install.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import Config
from ..engine import Engine
from ..models import Response, ServiceError

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    session_id: str = Field(default="web", max_length=64)


class SessionRequest(BaseModel):
    session_id: str = Field(default="web", max_length=64)


def create_app(config: Config | None = None, engine: Engine | None = None) -> FastAPI:
    settings = config or Config.from_env()
    assistant = engine or Engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log.info(
            "%s online: %d skills, brain=%s, offline=%s",
            settings.assistant_name,
            len(assistant.registry.all()),
            assistant.brain.name if assistant.brain.available else "none",
            settings.offline,
        )
        try:
            yield
        finally:
            await assistant.aclose()

    app = FastAPI(
        title=f"{settings.assistant_name} API",
        version="2.0.0",
        description="Voice-assistant engine exposed over HTTP for the browser UI.",
        lifespan=lifespan,
    )
    app.state.engine = assistant
    app.state.config = settings

    # ------------------------------------------------------------------ helpers
    def guard(request: Request) -> None:
        """Optional shared-secret check for exposed deployments."""
        token = settings.api_token.strip()
        if not token:
            return
        provided = request.headers.get("x-jarvis-token", "")
        if provided != token:
            raise HTTPException(status_code=401, detail="Invalid or missing X-JARVIS-Token header")

    # -------------------------------------------------------------------- routes
    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        guard(request)
        return {"status": "ok", "assistant": assistant.describe(), "version": app.version}

    @app.get("/api/skills")
    async def skills(request: Request) -> dict[str, Any]:
        guard(request)
        catalog = [entry for entry in assistant.catalog() if entry["examples"]]
        return {
            "skills": catalog,
            "count": len(catalog),
            "suggestions": assistant.suggestions(8),
        }

    @app.post("/api/command")
    async def command(payload: CommandRequest, request: Request) -> dict[str, Any]:
        guard(request)
        response: Response = await assistant.handle(payload.text, session_id=payload.session_id)
        return response.to_dict()

    @app.get("/api/session")
    async def session(request: Request, session_id: str = "web") -> dict[str, Any]:
        guard(request)
        current = assistant.get_session(session_id)
        return {
            "session": current.to_dict(),
            "history": [turn.to_dict() for turn in assistant.ctx.history.recent(20)],
        }

    @app.post("/api/reset")
    async def reset(payload: SessionRequest, request: Request) -> dict[str, Any]:
        guard(request)
        assistant.reset_session(payload.session_id)
        assistant.ctx.history.clear()
        return {"status": "reset", "session_id": payload.session_id}

    @app.get("/api/weather")
    async def weather(request: Request, location: str = "") -> dict[str, Any]:
        guard(request)
        try:
            current = await assistant.ctx.weather.current(location or None)
        except ServiceError as exc:
            return JSONResponse(status_code=502, content={"error": str(exc)})
        return current.to_dict()

    @app.get("/api/reminders/due")
    async def due_reminders(request: Request, within_hours: int = 24) -> dict[str, Any]:
        guard(request)
        due = assistant.ctx.reminders.due(within_hours=within_hours)
        return {"due": [note.to_dict() for note in due], "count": len(due)}

    @app.get("/api/notes")
    async def notes(request: Request) -> dict[str, Any]:
        guard(request)
        return {
            "open": [note.to_dict() for note in assistant.ctx.notes.open_items()],
            "memories": assistant.ctx.memory.everything(),
        }

    # -------------------------------------------------------------------- static
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    return app


def run(host: str | None = None, port: int | None = None, reload: bool = False) -> None:  # pragma: no cover
    """Start the API with uvicorn (used by ``jarvis serve``)."""
    import uvicorn

    settings = Config.from_env()
    uvicorn.run(
        "jarvis.server.app:default_app",
        host=host or settings.web_host,
        port=port or settings.web_port,
        reload=reload,
        log_level=settings.log_level.lower(),
    )


default_app = create_app()
