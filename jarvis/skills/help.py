"""Help / capability discovery."""

from __future__ import annotations

from ..models import Match, Response
from .base import Skill


class HelpSkill(Skill):
    name = "help"
    description = "List what the assistant can do, with example phrases."
    priority = 5  # answers first: it is unambiguous
    examples = ("What can you do?", "Help", "Show me the commands", "What are your skills?")
    patterns = (
        r"^(?P<help>help|commands|what can i (?:say|ask)|show me (?:the )?(?:commands|skills))\b",
        r"^(?P<help>what can you do|what are your (?:skills|capabilities)|list (?:your )?skills|capabilities)\b",
        r"^(?P<help>how (?:do|can) i use you)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        registry = self.ctx.registry  # type: ignore[attr-defined]
        skills = [entry for entry in registry.catalog() if entry["examples"]]
        skills.sort(key=lambda entry: entry["name"])

        highlights = ", ".join(entry["name"].replace("-", " ") for entry in skills[:8])
        spoken = (
            f"I have {len(skills)} skills online, including {highlights}. "
            "Try 'what is the weather', 'tell me the news', 'take a note' or 'define serendipity'. "
            "Say 'what can you do' any time to hear this again."
            if skills
            else "No skills are registered."
        )

        return Response.ok(
            spoken,
            kind="list",
            data={"skills": skills, "count": len(skills)},
        )


class AboutSkill(Skill):
    name = "about"
    description = "Explain what JARVIS is, how it is built and what it needs to run."
    priority = 12
    examples = ("What is this project?", "How were you built?", "What do you need to run?")
    patterns = (
        r"^(?P<about>what is this project|tell me about (?:the )?project|about this project)\b",
        r"^(?P<about>how (?:were|are) you built|what are you built with|what is your stack)\b",
        r"^(?P<about>what do you need to run|what are your requirements)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        if "requirements" in match.pattern:
            return Response.ok(
                "The core needs only Python 3.10 or newer. Optional extras add the desktop voice, "
                "microphone, face unlock and email features. Say 'system status' for a check.",
                data={"python": ">=3.10", "extras": ["voice", "mic", "vision", "email", "dev"]},
            )
        return Response.ok(
            "I am JA.R.V.I.S, rebuilt as a modular Python assistant: a skill registry matches your "
            "requests, services wrap the public APIs, and both a browser UI and a desktop console "
            "talk to the same engine.",
            data={"architecture": ["engine", "skills", "services", "web", "desktop"]},
        )
