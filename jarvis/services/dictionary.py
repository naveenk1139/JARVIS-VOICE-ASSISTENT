"""Dictionary lookups: bundled offline corpus first, free web API as a fallback."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import ServiceError

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..context import AppContext

FREE_DICTIONARY_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"


@dataclass(slots=True)
class Definition:
    word: str
    meanings: list[str]
    part_of_speech: str = ""
    source: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "meanings": self.meanings,
            "part_of_speech": self.part_of_speech,
            "source": self.source,
        }

    def spoken(self) -> str:
        joined = "; ".join(m.rstrip(".") for m in self.meanings[:2])
        return (
            f"{self.word}, {self.part_of_speech}: {joined}."
            if self.part_of_speech
            else f"{self.word}: {joined}"
        )


class DictionaryService:
    """Loads the 4 MB bundled corpus lazily so startup stays instant."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._entries: dict[str, Any] | None = None

    # ------------------------------------------------------------------ corpus
    @property
    def entries(self) -> dict[str, Any]:
        if self._entries is None:
            self._entries = self._load()
        return self._entries

    def _load(self) -> dict[str, Any]:
        path = Path(self.ctx.config.dictionary_path)
        if not path.is_file():
            log.warning("Dictionary corpus missing at %s; web fallback only", path)
            return {}
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load dictionary corpus: %s", exc)
            return {}
        return data if isinstance(data, dict) else {}

    # ----------------------------------------------------------------- lookups
    async def define(self, word: str) -> Definition:
        cleaned = normalize_word(word)
        if not cleaned:
            raise ServiceError("which word should I look up?", service="dictionary")

        local = self._local_definition(cleaned)
        if local is not None:
            return local

        return await self._web_definition(cleaned)

    def suggest(self, word: str, limit: int = 3) -> list[str]:
        """Spelling suggestions from the local corpus."""
        if not self.entries:
            return []
        return get_close_matches(word.lower(), self.entries.keys(), n=limit, cutoff=0.7)

    def _local_definition(self, word: str) -> Definition | None:
        entries = self.entries
        if not entries:
            return None
        key = word.lower()
        if key not in entries:
            return None
        raw = entries[key]
        meanings: Iterable[str]
        if isinstance(raw, list):
            meanings = [str(item) for item in raw]
        elif isinstance(raw, dict):
            meanings = [str(raw.get("definition", ""))]
        else:
            meanings = [str(raw)]
        meanings = [m for m in (m.strip() for m in meanings) if m]
        if not meanings:
            return None
        return Definition(word=word, meanings=meanings, source="local")

    async def _web_definition(self, word: str) -> Definition:
        try:
            payload = await self.ctx.http.get_json(
                FREE_DICTIONARY_URL.format(word=word), service="dictionary"
            )
        except ServiceError as exc:
            raise ServiceError(f"I could not find {word} in my dictionary", service="dictionary") from exc

        if not isinstance(payload, list) or not payload:
            raise ServiceError(f"I could not find {word} in my dictionary", service="dictionary")

        entry = payload[0] or {}
        meanings: list[str] = []
        part_of_speech = ""
        for meaning in entry.get("meanings", []) or []:
            part_of_speech = part_of_speech or (meaning.get("partOfSpeech") or "")
            for definition in meaning.get("definitions", [])[:2]:
                text = (definition.get("definition") or "").strip()
                if text:
                    meanings.append(text)
            if len(meanings) >= 2:
                break
        if not meanings:
            raise ServiceError(f"I could not find {word} in my dictionary", service="dictionary")
        return Definition(
            word=entry.get("word", word),
            meanings=meanings[:2],
            part_of_speech=part_of_speech,
            source="dictionaryapi.dev",
        )


def normalize_word(word: str) -> str:
    return " ".join((word or "").strip().strip("?.!,;:'\"").split()).lower()
