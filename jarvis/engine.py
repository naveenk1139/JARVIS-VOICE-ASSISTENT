"""The assistant engine: match an utterance, run a skill, return a Response.

Front doors (browser UI, desktop console, CLI) are thin; all behaviour lives
here so it can be unit-tested without a microphone, camera or browser.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .brains.base import Brain, NoBrain
from .brains.llm import build_brain
from .config import Config
from .context import AppContext
from .models import Pending, Response, ServiceError, normalize
from .services.http import HttpClient
from .skills import Skill, SkillRegistry, build_registry

log = logging.getLogger(__name__)

#: Skills at or below this priority are considered "explicit commands" and may
#: interrupt an open question owned by a *different* skill. Slots marked
#: ``free_text`` (an email body, for example) bypass this rule entirely.
NEW_COMMAND_PRIORITY = 60


@dataclass(slots=True)
class Session:
    """Per-conversation state."""

    id: str = "default"
    pending: Pending | None = None
    persona: str | None = None
    last_url: str | None = None
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    ended: bool = False

    def touch(self) -> None:
        self.last_seen = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "persona": self.persona,
            "pending": self.pending.slot if self.pending else None,
            "ended": self.ended,
        }


class Engine:
    """Owns configuration, services, skills and per-session state."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        http: HttpClient | None = None,
        brain: Brain | None = None,
        skills: Sequence[type[Skill]] | None = None,
    ) -> None:
        self.config = config or Config.from_env()
        self.config.ensure_dirs()
        self.http = http or HttpClient(
            timeout=self.config.http_timeout,
            retries=self.config.http_retries,
            user_agent=self.config.user_agent,
            offline=self.config.offline,
        )
        self.ctx = AppContext(config=self.config, http=self.http)
        self.registry: SkillRegistry = build_registry(self.ctx, extra=skills)
        self.ctx.registry = self.registry  # type: ignore[attr-defined]
        self.brain: Brain = brain or build_brain(self.config, self.http) or NoBrain(self.suggestions())
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ startup
    async def __aenter__(self) -> Engine:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.http.aclose()

    # ----------------------------------------------------------------- sessions
    def get_session(self, session_id: str = "default") -> Session:
        self._prune()
        session = self._sessions.get(session_id)
        if session is None:
            session = Session(id=session_id)
            self._sessions[session_id] = session
        session.touch()
        return session

    def reset_session(self, session_id: str = "default") -> Session:
        session = Session(id=session_id)
        self._sessions[session_id] = session
        return session

    def _prune(self) -> None:
        deadline = time.time() - self.config.session_ttl_seconds
        for key in [k for k, s in self._sessions.items() if s.last_seen < deadline]:
            del self._sessions[key]

    # -------------------------------------------------------------- main entry
    async def handle(self, text: str, *, session_id: str = "default") -> Response:
        """Interpret ``text`` and produce a response."""
        raw = (text or "").strip()
        cleaned = normalize(raw)
        session = self.get_session(session_id)
        history = self.ctx.history

        if not cleaned:
            return Response.error("I did not catch that. Could you say it again?")

        history.add("user", raw)

        response = await self._dispatch(cleaned, raw, session)
        response = self._apply_actions(response, session)

        history.add("jarvis", response.text, response.skill)
        if response.url:
            session.last_url = response.url
        if response.kind == "exit":
            session.ended = True
        return response

    async def _dispatch(self, cleaned: str, raw: str, session: Session) -> Response:
        match = self.registry.match(cleaned)

        # 1. Finish an open question first - unless the user clearly started a new
        #    command, or the slot explicitly wants free text (an email body).
        if session.pending is not None:
            skill = self.registry.get(session.pending.skill)
            if skill is not None:
                steals_turn = (
                    match is not None
                    and match[0].name != session.pending.skill
                    and match[0].priority <= NEW_COMMAND_PRIORITY
                )
                if session.pending.free_text or not steals_turn:
                    response = await self._safe_invoke(skill, "resume", session.pending, raw)
                    if response.kind != "error":
                        session.pending = None
                        return self._with_new_pending(response, session)
                    if match is None or session.pending.free_text:
                        return response
                session.pending = None

        # 2. Match a skill
        if match is not None:
            skill, skill_match = match
            response = await self._safe_invoke(skill, "handle", skill_match, raw)
            return self._with_new_pending(response, session)

        # 3. Fall back to the optional language model
        if self.brain.available:
            try:
                response = await asyncio.wait_for(
                    self.brain.answer(raw, self.ctx.history.recent(8)),
                    timeout=self.config.skill_timeout,
                )
                return response
            except asyncio.TimeoutError:
                return Response.error("The language model took too long to answer.", skill="llm")
            except Exception as exc:  # noqa: BLE001 - never crash the loop
                log.warning("Brain failed: %s", exc)
                return Response.error("I could not reach my language model just now.", skill="llm")

        return await self.brain.answer(raw, self.ctx.history.recent(8))

    async def _safe_invoke(self, skill: Skill, method: str, argument: Any, raw: str) -> Response:
        """Run a skill, converting any failure into a friendly Response."""
        try:
            return await self._run(skill, method, argument, raw)
        except ServiceError as exc:
            return Response.error(str(exc), skill=skill.name)
        except asyncio.TimeoutError:
            return Response.error(f"My {skill.name} skill took too long to respond.", skill=skill.name)
        except Exception:  # pragma: no cover - defensive
            log.exception("Skill %s failed during %s", skill.name, method)
            return Response.error(
                f"My {skill.name} skill hit an unexpected problem. Check the logs for details.",
                skill=skill.name,
            )

    async def _run(self, skill: Skill, method: str, argument: Any, raw: str) -> Response:
        """Invoke a skill with a hard timeout so a hung socket cannot freeze the UI."""
        coroutine = getattr(skill, method)(argument, raw)
        response: Response = await asyncio.wait_for(coroutine, timeout=self.config.skill_timeout)
        if not isinstance(response, Response):
            raise TypeError(f"skill {skill.name} returned {type(response)!r}, expected Response")
        if not response.skill or response.skill == "jarvis":
            response.skill = skill.name
        return response

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _with_new_pending(response: Response, session: Session) -> Response:
        if response.pending is not None:
            session.pending = response.pending
        return response

    def _apply_actions(self, response: Response, session: Session) -> Response:
        action = response.data.get("action") if isinstance(response.data, dict) else None
        if action == "set_persona":
            persona = str(response.data.get("persona", "jarvis"))
            self.config.persona = persona
            session.persona = persona
        elif action == "open_last_url":
            if session.last_url:
                response.url = session.last_url
                response.kind = "link"
                response.text = "Opening the article now."
            else:
                response.text = "I do not have a link to open yet."
        return response

    # --------------------------------------------------------------- discovery
    def catalog(self) -> list[dict[str, Any]]:
        return self.registry.catalog()

    def suggestions(self, limit: int = 6) -> list[str]:
        """A rotating set of example phrases, used by the UI and the fallback brain."""
        examples: list[str] = []
        for entry in self.registry.catalog():
            examples.extend(entry["examples"])
        if not examples:
            return []
        random.shuffle(examples)
        return examples[:limit]

    # ------------------------------------------------------------- integration
    def describe(self) -> dict[str, Any]:
        """Small status summary for UIs and the ``/api/health`` endpoint."""
        return {
            "name": self.config.assistant_name,
            "persona": self.config.persona,
            "user": self.config.display_name(),
            "skills": len(self.registry.all()),
            "brain": self.brain.name if self.brain.available else "none",
            "offline": self.config.offline,
            "email_configured": self.config.email_enabled,
            "dictionary_loaded": self.config.dictionary_available,
        }


async def run_once(text: str, config: Config | None = None) -> Response:
    """Convenience helper used by the CLI and tests."""
    engine = Engine(config)
    try:
        return await engine.handle(text)
    finally:
        await engine.aclose()
