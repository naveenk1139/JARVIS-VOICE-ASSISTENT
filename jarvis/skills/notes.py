"""Notes, to-dos and long-term memory."""

from __future__ import annotations

import re

from ..models import Match, Pending, Response
from .base import Skill

_INDEX_WORDS = {
    "first": 1,
    "one": 1,
    "1": 1,
    "second": 2,
    "two": 2,
    "2": 2,
    "third": 3,
    "three": 3,
    "3": 3,
    "fourth": 4,
    "four": 4,
    "4": 4,
    "fifth": 5,
    "five": 5,
    "5": 5,
}


class NotesSkill(Skill):
    name = "notes"
    description = "Keep notes and to-dos, and remember facts between runs."
    priority = 45
    examples = (
        "Add buy milk to my to-do list",
        "What are my notes?",
        "Mark the first task as done",
        "Remember that my wifi password is hunter2",
        "What do you remember?",
    )
    patterns = (
        r"^(?P<remember>remember (?:that )?)(?P<fact>.+)$",
        r"^(?P<recall>what (?:did i (?:ask|tell) you to remember|do you remember(?: anything)?|do you know about me))\b",
        r"^(?P<recall>read (?:me )?my (?:notes|to-?dos?|tasks)|what are my (?:notes|to-?dos?|tasks))\b",
        r"^(?P<recall>list (?:my )?(?:notes|to-?dos?|tasks))\b",
        r"^(?P<add>add|note|note down|write down|make a note)(?: that| this)?\s+(?P<text>.+?)(?:\s+to my (?:to-?do list|notes|list))?$",
        r"^(?P<add>add)\s+(?P<text>.+?)\s+to my (?:to-?do list|notes|list)$",
        r"^(?P<complete>mark|complete|finish|tick off|i(?:'ve| have) finished)\s+"
        r"(?:the\s+|task\s+|item\s+|number\s+)?(?P<index>first|second|third|fourth|fifth|one|two|three|four|five|\d{1,2})"
        r"(?:\s+(?:task|item))?(?:\s+(?:as\s+)?(?:done|complete|completed))?$",
        r"^(?P<clear>clear|delete|remove)\s+(?:all\s+)?(?:my\s+)?(?P<scope>completed notes|completed tasks|finished notes|notes|to-?dos?|tasks)\b",
        r"^(?P<forget>forget)\s+(?:that\s+|about\s+)?(?P<key>.+)$",
    )

    async def handle(self, match: Match, text: str) -> Response:
        groups = match.groups
        if "remember" in groups:
            return self._remember(match.group("fact"))
        if "recall" in groups:
            return self._read_notes()
        if "add" in groups:
            return self._add(match.group("text"))
        if "complete" in groups:
            return self._complete(match.group("index"))
        if "clear" in groups:
            return self._clear(match.group("scope"))
        if "forget" in groups:
            return self._forget(match.group("key"))
        return Response.error("I did not understand that note command.")

    # ---------------------------------------------------------------- handlers
    def _remember(self, fact: str) -> Response:
        cleaned = fact.strip(" .")
        if not cleaned:
            return Response.error("What should I remember?")
        key = " ".join(cleaned.split()[:6]).lower()
        self.ctx.memory.remember(key, cleaned)
        return Response.ok(
            f"Noted. I will remember that {cleaned}.",
            data={"remembered": {"key": key, "value": cleaned}},
        )

    def _read_notes(self) -> Response:
        notes = self.ctx.notes.open_items()
        facts = self.ctx.memory.everything()

        if not notes and not facts:
            return Response.ok("Your notes are empty. Say 'add buy milk to my to-do list' to start.")

        parts: list[str] = []
        if notes:
            listing = "; ".join(f"{index}. {note.text}" for index, note in enumerate(notes, 1))
            parts.append(f"You have {len(notes)} open item{'s' if len(notes) != 1 else ''}: {listing}")
        if facts:
            remembered = "; ".join(f"{value}" for value in list(facts.values())[:5])
            parts.append(f"Things you asked me to remember: {remembered}")

        return Response.ok(
            ". ".join(parts) + ".",
            kind="list",
            data={
                "notes": [note.to_dict() for note in notes],
                "memories": facts,
            },
        )

    def _add(self, raw_text: str) -> Response:
        cleaned = raw_text.strip(" .")
        cleaned = re.sub(r"\s+to my (?:to-?do list|notes|list)$", "", cleaned, flags=re.IGNORECASE)
        if not cleaned:
            return Response.error("What should I add?")
        note = self.ctx.notes.add(cleaned)
        return Response.ok(
            f"Added '{cleaned}' to your list. You now have {len(self.ctx.notes.open_items())} open items.",
            data={"note": note.to_dict()},
        )

    def _complete(self, raw_index: str) -> Response:
        key = (raw_index or "").strip().lower()
        index = int(key) if key.isdigit() else _INDEX_WORDS.get(key, 0)
        if index <= 0:
            return Response.error("Which item should I mark as done?")
        note = self.ctx.notes.complete(index)
        if note is None:
            return Response.error(f"There is no open item number {index}.")
        return Response.ok(f"Marked '{note.text}' as done.", data={"note": note.to_dict()})

    def _clear(self, scope: str) -> Response:
        include_open = "completed" not in scope.lower() and "finished" not in scope.lower()
        removed = self.ctx.notes.clear(include_open=include_open)
        if not removed:
            return Response.ok("There was nothing to clear.")
        label = "items" if include_open else "completed items"
        return Response.ok(f"Cleared {removed} {label}.")

    def _forget(self, key: str) -> Response:
        cleaned = key.strip(" .").lower()
        if self.ctx.memory.forget(cleaned):
            return Response.ok("Forgotten.")
        return Response.ok("I had nothing stored under that name.")

    # --------------------------------------------------------------- follow-ups
    async def resume(self, pending: Pending, text: str) -> Response:
        if pending.slot == "confirm_note":
            note = self.ctx.notes.add(text.strip())
            return Response.ok(f"Added '{note.text}'.", data={"note": note.to_dict()})
        return Response.error("I did not understand that.")
