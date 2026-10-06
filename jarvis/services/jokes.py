"""Jokes: a bundled, family-friendly set plus an optional online source."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from ..models import ServiceError

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..context import AppContext

JOKE_API = "https://v2.jokeapi.dev/joke/Programming,Miscellaneous?blacklistFlags=nsfw,religious,political,racist,sexist&type=single"

LOCAL_JOKES: tuple[str, ...] = (
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "There are only two hard problems in computer science: cache invalidation, naming things, and off-by-one errors.",
    "A SQL query walks into a bar, approaches two tables and asks: may I join you?",
    "Why did the developer go broke? Because he used up all his cache.",
    "I would tell you a UDP joke, but you might not get it.",
    "Why do Java developers wear glasses? Because they do not C sharp.",
    "How many programmers does it take to change a light bulb? None, that is a hardware problem.",
    "A byte walks into a bar looking miserable. The bartender asks what is wrong. Parity error, the byte says.",
    "Why was the function sad after a successful first call? It did not get a callback.",
    "Debugging: being the detective in a crime movie where you are also the murderer.",
    "I have a joke about time travel, but you did not like it.",
    "Why did the robot go on a diet? It had too many bytes.",
    "What is a robot's favourite kind of music? Heavy metal.",
    "My computer beat me at chess, but it was no match for me at kickboxing.",
    "Why do mathematicians confuse Halloween and Christmas? Because oct 31 equals dec 25.",
    "I told my computer I needed a break, and it said: no problem, I will go to sleep.",
    "Artificial intelligence is no match for natural stupidity.",
    "Why was the smartphone wearing glasses? It lost its contacts.",
    "A programmer's wife says: buy a loaf of bread, and if they have eggs, get a dozen. He came back with twelve loaves of bread.",
    "What do you call eight hobbits? A hob-byte.",
    "Why did the developer quit his job? Because he did not get arrays.",
    "Algorithm: a word used by programmers when they do not want to explain what they did.",
    "Why is it so hard to find a good robot doctor? They all lack patients.",
    "I would love to change the world, but they will not give me the source code.",
    "To understand recursion, you must first understand recursion.",
    "The best thing about a boolean is that even if you are wrong, you are only off by a bit.",
    "Why did the computer go to the doctor? Because it had a virus.",
    "There is no place like 127.0.0.1.",
    "Why do robots never panic? Because they have nerves of steel.",
    "What is the object's favourite movie? The Matrix, obviously.",
)


class JokeService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._recent: list[str] = []

    async def tell(self, *, online: bool = True) -> str:
        """Return one joke. Online is best-effort; local jokes always work."""
        if online and not self.ctx.config.offline:
            try:
                payload = await self.ctx.http.get_json(JOKE_API, service="jokes")
                joke = (payload or {}).get("joke")
                if joke:
                    return str(joke).strip()
            except ServiceError as exc:
                log.info("Online joke source unavailable: %s", exc)

        unused = [j for j in LOCAL_JOKES if j not in self._recent]
        if not unused:
            self._recent.clear()
            unused = list(LOCAL_JOKES)
        choice = random.choice(unused)
        self._recent.append(choice)
        if len(self._recent) > 5:
            self._recent.pop(0)
        return choice
