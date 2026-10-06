"""Headline briefing skill, with follow-up navigation ("open the second one")."""

from __future__ import annotations

import re

from ..models import Match, Pending, Response, ServiceError
from .base import Skill

_INDEX = r"\d{1,2}|first|second|third|fourth|fifth|sixth|last|one|two|three|four|five|six"

_ORDINALS = {
    "first": 1,
    "1st": 1,
    "one": 1,
    "second": 2,
    "2nd": 2,
    "two": 2,
    "third": 3,
    "3rd": 3,
    "three": 3,
    "fourth": 4,
    "4th": 4,
    "four": 4,
    "fifth": 5,
    "5th": 5,
    "five": 5,
    "sixth": 6,
    "6th": 6,
    "six": 6,
    "last": 5,
}

_SELECT = re.compile(
    rf"(?:\b(?:open|read|show|play|give me|tell me about|details?(?: of| about)?|more (?:on|about))\s+"
    rf"(?:the\s+|number\s+|headline\s+)?|\bnumber\s+|\bthe\s+)(?P<index>{_INDEX})\b",
    re.IGNORECASE,
)


class NewsSkill(Skill):
    name = "news"
    description = "Top headlines from public RSS feeds, read aloud or opened in the browser."
    requires_network = True
    priority = 25
    examples = ("What are the headlines?", "Read the news", "Open the second headline")
    patterns = (
        r"^(?P<brief>(?:what(?:'s| are) )?(?:the )?(?:today'?s? )?(?:news|headlines)"
        r"(?: today)?(?:\s+(?:about|on)\s+(?P<topic>[a-z ]+))?)\b",
        r"^(?P<brief>read (?:me )?(?:the )?(?:news|headlines))\b",
        r"^(?P<brief>brief(?:ing)?|catch me up)\b",
        r"^(?P<site>open (?:the )?(?:news|headlines? site|news site))\b",
        r"^(?P<select>open|read|show|play|give me|tell me about|details?(?: of| about)?|more (?:on|about))\s+"
        r"(?:the\s+|number\s+|headline\s+)?(?P<open_index>\d{1,2}|first|second|third|fourth|fifth|sixth|last)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        groups = match.groups
        if "select" in groups:
            return await self._open_selected(match.group("open_index"))
        if "site" in groups:
            return await self._open_article(0)

        try:
            headlines = await self.ctx.news.headlines(limit=5, force=True)
        except ServiceError as exc:
            return Response.error(str(exc), data={"service": "news"})

        topic = match.group("topic").strip() if "topic" in groups else ""
        if topic:
            headlines = [h for h in headlines if topic.lower() in h.title.lower()] or headlines

        spoken = "Here are the top headlines. " + " Next, ".join(item.sentence() for item in headlines[:5])
        spoken += " Say 'open the second headline' if you want the full story."
        return Response.ok(
            spoken,
            kind="list",
            data={
                "headlines": [item.to_dict() for item in headlines],
                "source": self.ctx.config.news_source,
            },
            pending=Pending(skill=self.name, slot="select", prompt="Which headline should I open?"),
        )

    # ---------------------------------------------------------------- follow-up
    async def resume(self, pending: Pending, text: str) -> Response:
        match = _SELECT.search(text)
        if match:
            return await self._open_selected(match.group("index"))
        if re.search(r"\b(yes|yeah|sure|ok|okay|please do)\b", text, re.IGNORECASE):
            return await self._open_article(0)
        if re.search(r"\b(no|nope|nah|later|nothing)\b", text, re.IGNORECASE):
            return Response.ok("Understood. Just ask if you want the headlines again.")
        return Response.error("Tell me which headline to open, for example 'open the second one'.")

    async def _open_selected(self, raw_index: str) -> Response:
        key = (raw_index or "").strip().lower()
        index = int(key) if key.isdigit() else _ORDINALS.get(key, 0)
        if index <= 0:
            return Response.error("I could not work out which headline you meant.")
        return await self._open_article(index - 1)

    async def _open_article(self, offset: int) -> Response:
        try:
            headlines = await self.ctx.news.headlines(limit=5)
        except ServiceError as exc:
            return Response.error(str(exc), data={"service": "news"})
        if not headlines:
            return Response.error("I have no headlines cached right now.")
        item = headlines[min(offset, len(headlines) - 1)]
        return Response.link(
            f"Opening {item.title} from {item.source}.",
            url=item.url,
            data={"headline": item.to_dict()},
        )
