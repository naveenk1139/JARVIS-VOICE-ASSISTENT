"""Skill base class, registry and matching.

A *skill* owns one capability (weather, notes, email, ...). It declares regex
intents, and receives an :class:`~jarvis.models.Match` plus the original
utterance. Skills are async so network work never blocks the event loop, which
is what the legacy single-threaded script failed to do.
"""

from __future__ import annotations

import abc
import logging
import re
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from ..models import Match, Pending, Response

if TYPE_CHECKING:  # pragma: no cover
    from ..context import AppContext

log = logging.getLogger(__name__)


class Skill(abc.ABC):
    """Base class for every capability."""

    name: str = "skill"
    description: str = ""
    patterns: Sequence[str] = ()
    examples: Sequence[str] = ()
    requires_network: bool = False
    priority: int = 100  # lower number wins ties
    settings: Sequence[str] = ()  # config keys that unlock richer behaviour

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._compiled: tuple[re.Pattern[str], ...] = tuple(
            re.compile(pattern, re.IGNORECASE) for pattern in self.patterns
        )

    # ------------------------------------------------------------------ match
    def match(self, text: str) -> Match | None:
        """Return the first matching intent for ``text``."""
        for pattern in self._compiled:
            found = pattern.search(text)
            if found is None:
                continue
            groups = {k: v for k, v in found.groupdict().items() if v is not None}
            return Match(skill=self.name, pattern=pattern.pattern, groups=groups)
        return None

    # ----------------------------------------------------------------- handle
    @abc.abstractmethod
    async def handle(self, match: Match, text: str) -> Response:
        """Fulfil a matched intent."""

    async def resume(self, pending: Pending, text: str) -> Response:
        """Answer a question this skill previously asked (``pending.slot``)."""
        return Response.error(f"I am not sure how to answer that for {self.name}.")

    # ------------------------------------------------------------------- meta
    def help_text(self) -> str:
        return self.description or self.name

    def example(self) -> str:
        return self.examples[0] if self.examples else ""

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "examples": list(self.examples[:3]),
            "requires_network": self.requires_network,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Skill {self.name}>"


class SkillRegistry:
    """Holds the registered skills and resolves utterances to them."""

    def __init__(self, ctx: AppContext, skills: Iterable[Skill] | None = None) -> None:
        self.ctx = ctx
        self._skills: dict[str, Skill] = {}
        for skill in skills or ():
            self.register(skill)

    def register(self, skill: Skill) -> Skill:
        if skill.name in self._skills:
            raise ValueError(f"duplicate skill name: {skill.name}")
        self._skills[skill.name] = skill
        return skill

    # ----------------------------------------------------------------- lookups
    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: (s.priority, s.name))

    def catalog(self) -> list[dict[str, Any]]:
        return [skill.catalog_entry() for skill in self.all()]

    def match(self, text: str) -> tuple[Skill, Match] | None:
        """Pick the best skill for ``text`` (declaration order, then priority)."""
        best: tuple[Skill, Match] | None = None
        for skill in self.all():
            found = skill.match(text)
            if found is None:
                continue
            if best is None or skill.priority < best[0].priority:
                best = (skill, found)
            if skill.priority == 0:  # reserved for exact, unambiguous intents
                break
        return best

    def contains(self, name: str) -> bool:
        return name in self._skills


def as_awaitable(value: Any) -> Any:
    """Normalise skill return values: sync skills may return bare Responses."""
    return value
