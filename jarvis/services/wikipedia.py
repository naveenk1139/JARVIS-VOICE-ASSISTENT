"""Wikipedia lookups (search + summary) using the public REST API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models import ServiceError

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..context import AppContext

SEARCH_URL = "https://en.wikipedia.org/w/api.php"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

_STOPWORDS = {
    "who",
    "what",
    "where",
    "when",
    "is",
    "are",
    "was",
    "were",
    "the",
    "a",
    "an",
    "tell",
    "me",
    "about",
    "of",
    "for",
    "on",
    "in",
    "to",
    "do",
    "you",
    "know",
    "wikipedia",
    "search",
    "look",
    "up",
    "please",
    "give",
    "info",
    "information",
}


@dataclass(slots=True)
class WikipediaAnswer:
    title: str
    extract: str
    url: str

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "extract": self.extract, "url": self.url}


class WikipediaService:
    """Search Wikipedia and return a spoken-friendly extract."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._cache: dict[str, WikipediaAnswer] = {}

    async def lookup(self, query: str, *, sentences: int = 2) -> WikipediaAnswer:
        topic = clean_topic(query)
        if not topic:
            raise ServiceError("you did not tell me what to look up", service="wikipedia")
        key = topic.lower()
        if key in self._cache:
            return self._cache[key]

        title = await self._best_title(topic)
        answer = await self._summary(title)
        self._cache[key] = answer
        return answer

    async def _best_title(self, topic: str) -> str:
        payload = await self.ctx.http.get_json(
            SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": topic,
                "srlimit": 1,
                "format": "json",
            },
            service="wikipedia",
        )
        hits = (((payload or {}).get("query") or {}).get("search")) or []
        if not hits:
            raise ServiceError(f"I could not find anything about {topic} on Wikipedia", service="wikipedia")
        return str(hits[0]["title"])

    async def _summary(self, title: str) -> WikipediaAnswer:
        encoded = title.replace(" ", "_")
        payload = await self.ctx.http.get_json(SUMMARY_URL.format(title=encoded), service="wikipedia")
        payload = payload or {}
        extract = (payload.get("extract") or "").strip()
        if not extract:
            raise ServiceError(f"Wikipedia has no summary for {title}", service="wikipedia")
        canonical = (payload.get("title") or title).strip()
        urls = payload.get("content_urls") or {}
        page_url = ((urls.get("desktop") or {}).get("page")) or f"https://en.wikipedia.org/wiki/{encoded}"
        return WikipediaAnswer(title=canonical, extract=shorten(extract, 2), url=page_url)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def clean_topic(query: str) -> str:
    """Turn ``"tell me about the mars rover"`` into ``"mars rover"``."""
    words = [w for w in (query or "").replace("?", " ").split() if w]
    while words and words[0].lower().strip(",") in _STOPWORDS:
        words.pop(0)
    while words and words[-1].lower().strip(",.") in _STOPWORDS:
        words.pop()
    return " ".join(words).strip()


def shorten(text: str, sentences: int) -> str:
    """Keep the first ``sentences`` sentences, without breaking abbreviations."""
    cleaned = " ".join((text or "").split())
    if sentences <= 0:
        return cleaned
    out: list[str] = []
    current = ""
    for char in cleaned:
        current += char
        if char in ".!?" and len(current.strip()) > 3:
            out.append(current.strip())
            current = ""
            if len(out) >= sentences:
                break
    if current.strip() and len(out) < sentences:
        out.append(current.strip())
    return " ".join(out) if out else cleaned
