"""Humour skill."""

from __future__ import annotations

from ..models import Match, Response
from .base import Skill


class JokeSkill(Skill):
    name = "jokes"
    description = "Tell a joke (bundled set, with an optional online source)."
    priority = 55
    examples = ("Tell me a joke", "Make me laugh", "Another one")
    patterns = (
        r"^(?P<joke>tell me a joke|say something funny|make me laugh|cheer me up|joke please)\b",
        r"^(?P<joke>another (?:one|joke)|one more joke|more jokes)\b",
        r"^(?P<joke>do you know (?:any )?jokes?)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        joke = await self.ctx.jokes.tell()
        return Response.ok(joke, kind="text", data={"joke": joke})
