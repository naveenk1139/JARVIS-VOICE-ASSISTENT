"""Time, date, timers and reminders."""

from __future__ import annotations

import datetime as dt
import re

from ..models import Match, Response
from .base import Skill

_ORDINALS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "forty five": 45,
    "fifty": 50,
    "an": 1,
    "a": 1,
    "half": 0.5,
}

_DURATION = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|fifty|an|a|half)"
    r"\s+(?:an?\s+)?(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)",
    re.IGNORECASE,
)


def parse_duration(text: str) -> tuple[int, str] | None:
    """Parse ``"5 minutes"``/``"in half an hour"`` -> ``(seconds, human_label)``."""
    found = _DURATION.search(text or "")
    if not found:
        return None
    raw = found.group("amount").lower()
    amount = float(_ORDINALS.get(raw, 0)) if not raw.replace(".", "").isdigit() else float(raw)
    unit = found.group("unit").lower()
    if amount <= 0:
        return None
    if unit.startswith(("sec",)):
        seconds, label = amount, f"{_pretty(amount)} seconds"
    elif unit.startswith(("min",)):
        seconds, label = amount * 60, f"{_pretty(amount)} minutes"
    else:
        seconds, label = amount * 3600, f"{_pretty(amount)} hours"
    return int(seconds), label


def _pretty(amount: float) -> str:
    return str(int(amount)) if float(amount).is_integer() else str(amount)


class TimeSkill(Skill):
    name = "time"
    description = "Report the current time and date, and set reminders."
    priority = 30
    examples = ("What time is it?", "What is today's date?", "Remind me in 10 minutes to stretch")
    patterns = (
        r"^(?:(?:what(?:'s| is)?|tell me|got the)\s+)?(?:the\s+)?time(?:\s+(?:is it|now|right now|today))*?(?P<time>)$",
        r"^(?P<time>time)\b",
        r"^(?:(?:what(?:'s| is)|tell me)\s+)?(?:the\s+|today'?s?\s+)*(?:date|day)(?:\s+(?:today|is it|now))*?(?P<date>)$",
        r"^(?:what|which)\s+day\s+is\s+it(?P<date>)$",
        r"^(?P<reminder>remind me|set (?:a )?reminder|reminder)\b",
        r"^(?P<timer>set (?:a )?timer|start (?:a )?timer|timer)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        groups = match.groups
        now = dt.datetime.now()

        if "reminder" in groups or "timer" in groups:
            return self._schedule(match, text, now)
        if "date" in groups:
            return Response.ok(
                f"Today is {now.strftime('%A, %d %B %Y')}.",
                data={"date": now.date().isoformat(), "weekday": now.strftime("%A")},
            )
        return Response.ok(
            f"It is {now.strftime('%I:%M %p').lstrip('0')} on {now.strftime('%A')}.",
            data={"time": now.strftime("%H:%M:%S")},
        )

    # --------------------------------------------------------------- reminders
    def _schedule(self, match: Match, text: str, now: dt.datetime) -> Response:
        parsed = parse_duration(text)
        if parsed is None:
            return Response.ok(
                "How long should I wait? Say something like 'remind me in 10 minutes to stretch'.",
                pending=None,
            )
        seconds, label = parsed
        subject = _extract_subject(text)
        due = now + dt.timedelta(seconds=seconds)
        store = self.ctx.reminders
        note = store.add(subject or "Reminder", due_at=due)
        spoken = f"Reminder set for {label} from now"
        spoken += f": {subject}." if subject else "."
        return Response.ok(
            spoken,
            data={
                "reminder": {
                    "id": note.id,
                    "text": note.text,
                    "due_at": note.due_at,
                    "in_seconds": seconds,
                }
            },
        )


class CountdownSkill(Skill):
    """``jarvis ask "how long until 6pm"`` style questions."""

    name = "countdown"
    description = "Count the time remaining until a clock time."
    priority = 35
    examples = ("How long until 6 pm?",)
    patterns = (
        r"^(?:how (?:long|much time) (?:until|till|to) )(?P<when>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)(?P<countdown>)",
    )

    async def handle(self, match: Match, text: str) -> Response:
        target_text = match.group("when")
        target = _parse_clock(target_text)
        if target is None:
            return Response.error(f"I could not understand the time {target_text}.")
        now = dt.datetime.now()
        target_dt = now.replace(hour=target[0], minute=target[1], second=0, microsecond=0)
        if target_dt < now:
            target_dt += dt.timedelta(days=1)
        delta = target_dt - now
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        spoken = (
            f"That is in {hours} hours and {minutes} minutes." if hours else f"That is in {minutes} minutes."
        )
        return Response.ok(spoken, data={"seconds_remaining": int(delta.total_seconds())})


def _parse_clock(text: str) -> tuple[int, int] | None:
    cleaned = text.strip().lower().replace(".", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", cleaned)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour, minute


_SUBJECT_HINTS = (
    " to ",
    " that ",
    " about ",
    " for ",
    " saying ",
)


def _extract_subject(text: str) -> str:
    lowered = f" {text.strip()} "
    for hint in _SUBJECT_HINTS:
        if hint in lowered:
            subject = lowered.split(hint, 1)[1].strip(" .")
            if subject:
                return subject
    return ""
