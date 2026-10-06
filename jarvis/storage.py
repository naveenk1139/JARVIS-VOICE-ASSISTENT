"""Small JSON-backed stores: notes, reminders, remembered facts and history.

Every store writes atomically (temp file + ``os.replace``) so a crash mid-write
can never corrupt the user's data, which was a real risk in the legacy scripts.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now()


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


class JsonStore:
    """Base class for a single-file JSON collection."""

    filename = "store.json"
    default: Any = list

    def __init__(self, directory: Path) -> None:
        self._path = Path(directory) / self.filename
        self._lock = RLock()

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> Any:
        with self._lock:
            if not self._path.is_file():
                return self.default()
            try:
                return json.loads(self._path.read_text(encoding="utf-8") or "null") or self.default()
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Could not read %s: %s", self._path, exc)
                return self.default()

    def write(self, payload: Any) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path)


# --------------------------------------------------------------------------- #
# Notes / to-dos
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Note:
    id: str
    text: str
    created_at: str
    done: bool = False
    due_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Note:
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex[:8]),
            text=str(payload.get("text", "")),
            created_at=str(payload.get("created_at") or _iso(_now())),
            done=bool(payload.get("done", False)),
            due_at=payload.get("due_at"),
        )


class NoteStore(JsonStore):
    filename = "notes.json"

    def add(self, text: str, *, due_at: datetime | None = None) -> Note:
        note = Note(
            id=uuid.uuid4().hex[:8],
            text=text.strip(),
            created_at=_iso(_now()),
            due_at=_iso(due_at) if due_at else None,
        )
        items = self.all()
        items.append(note)
        self.write([item.to_dict() for item in items])
        return note

    def all(self) -> list[Note]:
        return [Note.from_dict(item) for item in self.read() if isinstance(item, dict)]

    def open_items(self) -> list[Note]:
        return [note for note in self.all() if not note.done]

    def complete(self, index: int) -> Note | None:
        items = self.all()
        open_items = [note for note in items if not note.done]
        if not (1 <= index <= len(open_items)):
            return None
        target = open_items[index - 1]
        for item in items:
            if item.id == target.id:
                item.done = True
        self.write([item.to_dict() for item in items])
        return target

    def clear(self, *, include_open: bool = False) -> int:
        """Drop completed items; with ``include_open`` drop everything."""
        items = self.all()
        kept = [] if include_open else [item for item in items if not item.done]
        removed = len(items) - len(kept)
        self.write([item.to_dict() for item in kept])
        return removed

    def due(self, within_hours: int = 24) -> list[Note]:
        horizon = _now() + timedelta(hours=within_hours)
        out: list[Note] = []
        for note in self.open_items():
            if not note.due_at:
                continue
            try:
                due = datetime.fromisoformat(note.due_at)
            except ValueError:
                continue
            if due <= horizon:
                out.append(note)
        return out


class ReminderStore(NoteStore):
    filename = "reminders.json"


# --------------------------------------------------------------------------- #
# Remembered facts
# --------------------------------------------------------------------------- #
class MemoryStore(JsonStore):
    filename = "memory.json"
    default = dict

    def remember(self, key: str, value: str) -> None:
        data = dict(self.read())
        data[key.strip().lower()] = value.strip()
        self.write(data)

    def recall(self, key: str) -> str | None:
        return dict(self.read()).get(key.strip().lower())

    def everything(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in dict(self.read()).items()}

    def find(self, query: str) -> str | None:
        """Best-effort key lookup: exact, then substring in either direction."""
        needle = query.strip().lower()
        if not needle:
            return None
        data = dict(self.read())
        if needle in data:
            return needle
        for key in data:
            if needle in key or key in needle:
                return key
        return None

    def forget(self, key: str) -> bool:
        data = dict(self.read())
        found = self.find(key)
        if found is not None:
            del data[found]
            self.write(data)
            return True
        return False


# --------------------------------------------------------------------------- #
# Conversation history (in-memory, per session)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Turn:
    role: str  # "user" | "jarvis"
    text: str
    at: str = field(default_factory=lambda: _iso(_now()))
    skill: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class History:
    """Bounded rolling transcript for the UI."""

    def __init__(self, limit: int = 50) -> None:
        self.limit = max(1, limit)
        self._turns: list[Turn] = []
        self._lock = RLock()

    def add(self, role: str, text: str, skill: str = "") -> Turn:
        turn = Turn(role=role, text=text, skill=skill)
        with self._lock:
            self._turns.append(turn)
            if len(self._turns) > self.limit:
                self._turns = self._turns[-self.limit :]
        return turn

    def recent(self, count: int | None = None) -> list[Turn]:
        with self._lock:
            turns = list(self._turns)
        return turns[-count:] if count else turns

    def last_user(self) -> str:
        with self._lock:
            for turn in reversed(self._turns):
                if turn.role == "user":
                    return turn.text
        return ""

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def extend(self, turns: Iterable[Turn]) -> None:
        for turn in turns:
            self.add(turn.role, turn.text, turn.skill)
