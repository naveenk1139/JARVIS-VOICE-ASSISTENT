"""Host telemetry and local file helpers."""

from __future__ import annotations

import asyncio
import datetime as dt
import platform

from ..models import Match, Response
from .base import Skill


class SystemSkill(Skill):
    name = "system"
    description = "Report CPU, memory, battery, disk and host information."
    priority = 42
    examples = ("CPU status", "How much memory is free?", "System status", "What platform are you on?")
    patterns = (
        r"^(?P<status>cpu|processor|system status|system info|status report|battery|memory|ram|disk)\b",
        r"^(?P<status>how much (?:memory|ram|disk)(?: is)? (?:free|left|used)?)\b",
        r"^(?P<platform>what (?:platform|os|operating system) (?:are you|is this))\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        if "platform" in match.groups:
            return Response.ok(
                f"I am running on {platform.system()} {platform.release()} with Python {platform.python_version()}.",
                data={"platform": platform.platform(), "python": platform.python_version()},
            )
        status = await asyncio.to_thread(self.ctx.system.status)
        return Response.ok(status.spoken(), kind="status", data=status.to_dict())


class GoodbyeSkill(Skill):
    """Ends the session. Deliberately does not power off the host machine."""

    name = "goodbye"
    description = "End the assistant session or stop listening."
    priority = 10
    examples = ("Goodbye Jarvis", "Go to sleep", "Shut down")
    patterns = (
        r"^(?P<exit>exit|quit|shut ?down|power off|stop listening|go to sleep|sleep now|that(?:'s| is) all)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        now = dt.datetime.now().strftime("%I:%M %p").lstrip("0")
        return Response.ok(
            f"Standing down at {now}. Say my name when you need me again.",
            kind="exit",
            data={
                "action": "exit",
                "note": "JARVIS never powers off your computer; it only ends the session.",
            },
        )
