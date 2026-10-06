"""Greetings, identity, persona switching and capability questions.

Intent dispatch convention used by every skill in this project: each pattern
carries a distinct *named group* (``?P<greet>``, ``?P<identity>`` ...). The
handler then dispatches on ``match.groups`` instead of re-parsing the regex
string, which keeps the code readable and testable.
"""

from __future__ import annotations

import random

from ..models import Match, Response
from .base import Skill

GREETINGS = (
    "At your service.",
    "Online and listening.",
    "Right here. What do you need?",
    "Systems nominal. How can I help?",
)

STATUS_LINES = (
    "All subsystems are nominal and I am ready for your next instruction.",
    "Running smoothly. My reactor is at full power, metaphorically speaking.",
    "I am well, thank you. Ready when you are.",
)


class SmallTalkSkill(Skill):
    name = "smalltalk"
    description = "Greetings, identity and general chat about the assistant itself."
    priority = 40
    examples = (
        "Jarvis, are you there?",
        "Hello Jarvis",
        "What is your name?",
        "What can you do?",
        "Who made you?",
    )
    patterns = (
        r"^(?P<alive>are you (?:there|awake|online|listening)|you there|you awake)\b",
        r"^(?P<alive>jarvis|friday)[.!,]?$",
        r"^(?P<greet>hello|hi|hey|good (?:morning|afternoon|evening))\b",
        r"^(?P<mood>how are you(?: doing)?)\b",
        r"^(?P<identity>what(?:'s| is) your name|who are you|introduce yourself)\b",
        r"^(?P<acronym>what does (?:jarvis|friday|your name) stand for)\b",
        r"^(?P<creator>who (?:made|created|built|programmed) you|who is your (?:creator|maker|master|boss))\b",
        r"^(?P<thanks>thank you|thanks|nice work|well done|good job)\b",
        r"^(?P<nature>are you (?:a )?(?:robot|human|real|ai)|what are you)\b",
        r"^(?P<bye>good ?night|goodbye|bye|see you)\b",
        r"^(?P<voice>switch|change|use) (?:to |your )?(?P<persona>friday|jarvis|female|male)(?: voice)?\b",
        r"^(?P<voice>be|become|switch to) (?P<persona>friday|jarvis)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        cfg = self.ctx.config
        groups = match.groups

        if "acronym" in groups:
            return Response.ok(
                f"{cfg.assistant_name.upper()} stands for Just A Rather Very Intelligent System."
            )
        if "identity" in groups:
            return Response.ok(
                f"I am {cfg.assistant_name}, your personal assistant. I handle weather, news, "
                "Wikipedia, the dictionary, notes, reminders and more."
            )
        if "creator" in groups:
            return Response.ok(
                "I began as an open source hobby project and have been rebuilt here into a "
                f"proper assistant with a real engine, skills and tests. {cfg.display_name()} runs me."
            )
        if "nature" in groups:
            return Response.ok(
                "I am software, not a person. I run on your machine and only touch the network "
                "for the services you explicitly ask for."
            )
        if "voice" in groups:
            wanted = match.group("persona").lower()
            target = "friday" if wanted in {"friday", "female"} else "jarvis"
            if target == cfg.persona:
                return Response.ok(f"I am already using the {target.upper()} voice.")
            return Response.ok(
                f"Switching to the {target.upper()} voice. How does this sound?",
                data={"action": "set_persona", "persona": target},
                persona=target,
            )
        if "thanks" in groups:
            return Response.ok(random.choice(("Any time.", "My pleasure.", "That is what I am here for.")))
        if "bye" in groups:
            return Response.ok(f"Goodbye, {cfg.display_name()}. Call me whenever you need me.")
        if "mood" in groups:
            return Response.ok(random.choice(STATUS_LINES))
        if "alive" in groups:
            return Response.ok("Yes, I am here and listening.")
        if "greet" in groups:
            hour = _hour_now()
            part = "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")
            return Response.ok(f"Good {part}, {cfg.display_name()}. {random.choice(GREETINGS)}")
        return Response.ok(random.choice(GREETINGS))


def _hour_now() -> int:
    import datetime

    return int(datetime.datetime.now().hour)
