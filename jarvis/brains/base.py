"""Pluggable "brain" used when no skill matches an utterance."""

from __future__ import annotations

import abc
from collections.abc import Iterable, Sequence

from ..models import Response


class Brain(abc.ABC):
    """A conversational fallback. Optional: JARVIS works without one."""

    name: str = "brain"

    @property
    def available(self) -> bool:
        return False

    @abc.abstractmethod
    async def answer(self, question: str, history: Sequence[object] = ()) -> Response:
        """Return a free-form answer to an unmatched question."""


class NoBrain(Brain):
    """Default: politely admit the gap and suggest what *is* supported."""

    name = "none"

    def __init__(self, suggestions: Iterable[str] = ()) -> None:
        self._suggestions = tuple(suggestions)

    async def answer(self, question: str, history: Sequence[object] = ()) -> Response:
        suggestions = list(self._suggestions[:3])
        hint = f" For example: {', '.join(suggestions)}." if suggestions else ""
        return Response.error(
            f"I do not have a skill for that yet.{hint} "
            "Add an LLM key (JARVIS_LLM_API_KEY) and I can answer open questions too.",
            data={"suggestions": suggestions, "unmatched": question},
            skill="fallback",
        )
