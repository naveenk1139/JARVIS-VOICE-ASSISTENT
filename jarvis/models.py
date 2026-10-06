"""Shared data structures passed between skills, the engine and the front doors."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Response kinds
# --------------------------------------------------------------------------- #
TEXT = "text"
LINK = "link"
ERROR = "error"
LIST = "list"
STATUS = "status"
EXIT = "exit"


@dataclass(frozen=True, slots=True)
class Pending:
    """A question the assistant asked that the next utterance should answer.

    ``data`` carries whatever the skill needs to keep the dialogue going, e.g.
    the partially filled draft of an email.
    """

    skill: str
    slot: str
    prompt: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    #: when True the slot always consumes the raw utterance (e.g. an email body),
    #: so a coincidental skill match must not steal the turn
    free_text: bool = False


@dataclass(slots=True)
class Response:
    """Everything a skill returns. Front doors decide how to present it."""

    text: str
    kind: str = TEXT
    speak: bool = True
    url: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    pending: Pending | None = None
    persona: str | None = None
    skill: str = "jarvis"

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        if self.pending is not None:
            payload["pending"] = dataclasses.asdict(self.pending)
        return payload

    # -- small constructors used all over the skills -------------------------
    @classmethod
    def ok(cls, text: str, **kwargs: Any) -> Response:
        return cls(text=text, **kwargs)

    @classmethod
    def link(cls, text: str, url: str, **kwargs: Any) -> Response:
        return cls(text=text, url=url, kind=LINK, **kwargs)

    @classmethod
    def error(cls, text: str, **kwargs: Any) -> Response:
        return cls(text=text, kind=ERROR, **kwargs)


@dataclass(frozen=True, slots=True)
class Match:
    """Result of matching an utterance against one of a skill's patterns."""

    skill: str
    pattern: str
    groups: dict[str, str]

    def group(self, name: str, default: str = "") -> str:
        return (self.groups.get(name) or default).strip()


class ServiceError(RuntimeError):
    """A remote service could not be reached or returned something unusable."""

    def __init__(self, message: str, *, service: str = "", status: int | None = None) -> None:
        super().__init__(message)
        self.service = service
        self.status = status


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
_WHITESPACE = re.compile(r"\s+")
_POLITE_PREFIX = re.compile(r"^(?:hey|hi|ok|okay|hello|yo|please|jarvis|friday)\b[\s,]*", re.IGNORECASE)
_POLITE_SUFFIX = re.compile(r"[\s,]*(?:please|for me|thanks|thank you)[.!?]*$", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace and trim conversational padding.

    Speech recognisers are noisy and users are polite; both add words that
    would otherwise defeat exact pattern matching.
    """
    cleaned = _WHITESPACE.sub(" ", (text or "").strip())
    if not cleaned:
        return ""
    # strip trailing punctuation but keep intra-word characters ('.', '-') intact
    cleaned = cleaned.strip(" \t\n\r.!?,;:\u2019\"'")
    # Strip conversational padding ("hey jarvis, ... please") but never strip the
    # utterance away entirely - "hello jarvis" must not normalise to "".
    for _ in range(3):
        candidate = _POLITE_PREFIX.sub("", cleaned).strip()
        candidate = _POLITE_SUFFIX.sub("", candidate).strip()
        if not candidate or candidate == cleaned:
            break
        cleaned = candidate
    return cleaned.lower()


def compile_patterns(patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)
