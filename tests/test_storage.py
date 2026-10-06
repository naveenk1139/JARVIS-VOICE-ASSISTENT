"""Persistence: notes, reminders, memory and history."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from jarvis.storage import History, JsonStore, MemoryStore, NoteStore, ReminderStore


@pytest.fixture()
def store(tmp_path: Path) -> NoteStore:
    return NoteStore(tmp_path)


def test_notes_round_trip(store: NoteStore) -> None:
    note = store.add("buy milk")
    assert note.id and note.created_at
    assert [n.text for n in store.all()] == ["buy milk"]
    assert [n.text for n in store.open_items()] == ["buy milk"]


def test_complete_by_position(store: NoteStore) -> None:
    store.add("first")
    store.add("second")
    completed = store.complete(2)
    assert completed is not None and completed.text == "second"
    assert [n.text for n in store.open_items()] == ["first"]
    assert store.complete(5) is None


def test_clear_behaviour(store: NoteStore) -> None:
    store.add("first")
    store.add("second")
    store.complete(1)

    assert store.clear() == 1  # completed only
    assert [n.text for n in store.open_items()] == ["second"]

    assert store.clear(include_open=True) == 1  # everything
    assert store.all() == []


def test_due_reminders(tmp_path: Path) -> None:
    reminders = ReminderStore(tmp_path)
    reminders.add("soon", due_at=dt.datetime.now() + dt.timedelta(minutes=5))
    reminders.add("later", due_at=dt.datetime.now() + dt.timedelta(days=3))
    reminders.add("undated")

    due = reminders.due(within_hours=1)
    assert [note.text for note in due] == ["soon"]


def test_writes_are_atomic(tmp_path: Path) -> None:
    """A leftover .tmp file must never be left behind or read as data."""
    store = NoteStore(tmp_path)
    store.add("hello")
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads((tmp_path / "notes.json").read_text(encoding="utf-8"))[0]["text"] == "hello"


def test_corrupt_file_degrades_gracefully(tmp_path: Path) -> None:
    (tmp_path / "notes.json").write_text("{ this is not json", encoding="utf-8")
    store = NoteStore(tmp_path)
    assert store.all() == []
    store.add("recovered")
    assert [n.text for n in store.all()] == ["recovered"]


def test_base_store_defaults(tmp_path: Path) -> None:
    class DictStore(JsonStore):
        filename = "dict.json"
        default = dict

    assert DictStore(tmp_path).read() == {}
    assert JsonStore(tmp_path).read() == []


def test_memory_find_and_forget(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path)
    memory.remember("the wifi password is hunter2", "the wifi password is hunter2")
    assert memory.recall("the wifi password is hunter2") is not None
    assert memory.find("wifi password") == "the wifi password is hunter2"
    assert memory.find("nothing here") is None
    assert memory.forget("wifi password") is True
    assert memory.everything() == {}


def test_history_is_bounded() -> None:
    history = History(limit=3)
    for index in range(5):
        history.add("user", f"message {index}")
    turns = history.recent()
    assert len(turns) == 3
    assert turns[-1].text == "message 4"
    assert history.last_user() == "message 4"
    history.clear()
    assert history.recent() == []
