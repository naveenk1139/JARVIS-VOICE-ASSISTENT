"""The default skill set.

Import order matters only for readability: the registry resolves ties with each
skill's ``priority`` (lower wins), not with registration order.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .base import Skill, SkillRegistry
from .calculator import CalculatorSkill
from .clock import CountdownSkill, TimeSkill
from .email import EmailSkill
from .help import AboutSkill, HelpSkill
from .jokes import JokeSkill
from .knowledge import DictionarySkill, WikipediaSkill
from .news import NewsSkill
from .notes import NotesSkill
from .smalltalk import SmallTalkSkill
from .system import GoodbyeSkill, SystemSkill
from .weather import WeatherSkill
from .web import WebSkill

if TYPE_CHECKING:  # pragma: no cover
    from ..context import AppContext

DEFAULT_SKILLS: tuple[type[Skill], ...] = (
    HelpSkill,
    AboutSkill,
    GoodbyeSkill,
    CalculatorSkill,
    WeatherSkill,
    NewsSkill,
    TimeSkill,
    CountdownSkill,
    SmallTalkSkill,
    SystemSkill,
    NotesSkill,
    EmailSkill,
    WebSkill,
    WikipediaSkill,
    DictionarySkill,
    JokeSkill,
)


def build_registry(ctx: AppContext, extra: Sequence[type[Skill]] | None = None) -> SkillRegistry:
    """Create a registry with the default skills plus any extras."""
    registry = SkillRegistry(ctx)
    for skill_type in (*DEFAULT_SKILLS, *(extra or ())):
        registry.register(skill_type(ctx))
    return registry


__all__ = [
    "DEFAULT_SKILLS",
    "Skill",
    "SkillRegistry",
    "build_registry",
    "CalculatorSkill",
    "CountdownSkill",
    "DictionarySkill",
    "EmailSkill",
    "GoodbyeSkill",
    "HelpSkill",
    "JokeSkill",
    "NewsSkill",
    "NotesSkill",
    "SmallTalkSkill",
    "SystemSkill",
    "TimeSkill",
    "WeatherSkill",
    "WebSkill",
    "WikipediaSkill",
]
