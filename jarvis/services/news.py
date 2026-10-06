"""Headlines from public RSS feeds (with an optional newsapi.org backend)."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import unescape
from typing import TYPE_CHECKING, Any

from ..models import ServiceError

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..context import AppContext

CACHE_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class Headline:
    title: str
    url: str
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "source": self.source}

    def sentence(self) -> str:
        return f"{self.title}." if not self.title.endswith((".", "!", "?")) else self.title


class NewsService:
    """Fetches top headlines, preferring free RSS feeds.

    The legacy project shipped a hardcoded ``newsapi.org`` key placeholder which
    always failed. Here the key is optional: without it we parse Google News and
    other public RSS feeds, which need no credentials at all.
    """

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._cache: tuple[float, list[Headline]] = (0.0, [])

    async def headlines(self, limit: int = 5, *, force: bool = False) -> list[Headline]:
        limit = max(1, min(limit, 20))
        cached_at, cached = self._cache
        if not force and cached and (time.monotonic() - cached_at) < CACHE_TTL_SECONDS:
            return cached[:limit]

        items: list[Headline] = []
        errors: list[str] = []

        if self.ctx.config.news_api_key:
            try:
                items = await self._from_newsapi(limit)
            except ServiceError as exc:
                errors.append(str(exc))
        if not items:
            items = await self._from_feeds(limit)
        if not items:
            detail = f" ({errors[0]})" if errors else ""
            raise ServiceError(f"I could not reach any news source{detail}", service="news")

        self._cache = (time.monotonic(), items)
        return items[:limit]

    # ------------------------------------------------------------------ feeds
    async def _from_feeds(self, limit: int) -> list[Headline]:
        collected: list[Headline] = []
        seen: set[str] = set()
        for feed in self.ctx.config.news_feeds:
            try:
                raw = await self.ctx.http.get_text(feed, service="news")
            except ServiceError as exc:
                log.info("News feed %s unavailable: %s", feed, exc)
                continue
            for headline in self._parse_feed(raw, feed):
                fingerprint = headline.title.lower()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                collected.append(headline)
                if len(collected) >= limit:
                    return collected
        return collected

    @staticmethod
    def _parse_feed(raw: str, feed_url: str) -> list[Headline]:
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            log.info("Could not parse feed %s: %s", feed_url, exc)
            return []

        default_source = _feed_title(root) or _hostname(feed_url)
        headlines: list[Headline] = []

        # RSS 2.0 uses <item>, Atom uses <entry>
        for node in list(root.iter("item")) + list(root.iter("entry")):
            title = _first_text(node, "title")
            if not title:
                continue
            link = _first_text(node, "link")
            if not link:
                link_node = node.find("link")
                link = (link_node.get("href", "") if link_node is not None else "") or ""
            source = _first_text(node, "source") or _nested_text(node, "source") or default_source
            headlines.append(Headline(title=title, url=link.strip(), source=source.strip()))
        return headlines

    # ---------------------------------------------------------------- newsapi
    async def _from_newsapi(self, limit: int) -> list[Headline]:
        payload = await self.ctx.http.get_json(
            "https://newsapi.org/v2/top-headlines",
            params={
                "country": self.ctx.config.news_country or "in",
                "pageSize": limit,
                "apiKey": self.ctx.config.news_api_key,
            },
            service="news",
        )
        articles = (payload or {}).get("articles") or []
        return [
            Headline(
                title=(article.get("title") or "").strip(),
                url=article.get("url") or "",
                source=(article.get("source") or {}).get("name", "NewsAPI"),
            )
            for article in articles
            if article.get("title")
        ]


# --------------------------------------------------------------------------- #
# XML helpers
# --------------------------------------------------------------------------- #
def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def _first_text(node: ET.Element, tag: str) -> str:
    for child in node:
        if _strip_ns(child.tag) == tag.lower():
            return unescape((child.text or "").strip())
    return ""


def _nested_text(node: ET.Element, tag: str) -> str:
    for child in node.iter():
        if _strip_ns(child.tag) == tag.lower() and (child.text or "").strip():
            return unescape((child.text or "").strip())
    return ""


def _feed_title(root: ET.Element) -> str:
    for channel in root.iter():
        if _strip_ns(channel.tag) == "channel":
            return _first_text(channel, "title")
    return _first_text(root, "title")


def _hostname(url: str) -> str:
    parts = url.split("/")
    return parts[2] if len(parts) > 2 else "News"
