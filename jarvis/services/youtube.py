"""YouTube helpers: search links and video metadata via the public oEmbed API."""

from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models import ServiceError

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..context import AppContext

OEMBED_URL = "https://www.youtube.com/oembed"
SEARCH_URL = "https://www.youtube.com/results?search_query="

_YOUTUBE_ID = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{6,})")


@dataclass(slots=True)
class Video:
    title: str
    author: str
    url: str

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "author": self.author, "url": self.url}


def search_url(query: str) -> str:
    """A deep link into YouTube search results for ``query``."""
    return SEARCH_URL + urllib.parse.quote_plus((query or "").strip())


def extract_video_id(url_or_id: str) -> str | None:
    candidate = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        return candidate
    match = _YOUTUBE_ID.search(candidate)
    return match.group(1) if match else None


class YouTubeService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def build_search(self, query: str) -> Video:
        query = (query or "").strip()
        if not query:
            raise ServiceError("what should I search for on YouTube?", service="youtube")
        return Video(
            title=f"YouTube results for {query}",
            author="YouTube",
            url=search_url(query),
        )

    async def video_details(self, url_or_id: str) -> Video:
        video_id = extract_video_id(url_or_id)
        if not video_id:
            raise ServiceError("that does not look like a YouTube link", service="youtube")
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        payload = await self.ctx.http.get_json(
            OEMBED_URL,
            params={"url": watch_url, "format": "json"},
            service="youtube",
        )
        payload = payload or {}
        return Video(
            title=str(payload.get("title") or "Unknown video"),
            author=str(payload.get("author_name") or "Unknown channel"),
            url=watch_url,
        )
