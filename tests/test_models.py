from __future__ import annotations

import dataclasses

import pytest

from jarvis.models import Pending, Response, compile_patterns, normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  WHAT   is the Weather?  ", "what is the weather"),
        ("Hey Jarvis, tell me the news please", "tell me the news"),
        ("jarvis, what time is it", "what time is it"),
        ("Hello Jarvis", "jarvis"),  # never normalise to an empty string
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_response_factories() -> None:
    ok = Response.ok("hello", skill="smalltalk")
    link = Response.link("opening", "https://example.com")
    error = Response.error("nope")

    assert ok.kind == "text" and ok.speak is True
    assert link.kind == "link" and link.url == "https://example.com"
    assert error.kind == "error"


def test_response_to_dict_serialises_pending() -> None:
    response = Response.ok(
        "which one?",
        pending=Pending(skill="news", slot="select", data={"draft": {"to": "a@b.co"}}),
    )
    payload = response.to_dict()
    assert payload["pending"]["skill"] == "news"
    assert payload["pending"]["data"]["draft"]["to"] == "a@b.co"
    assert payload["text"] == "which one?"


def test_compile_patterns_matches_case_insensitively() -> None:
    (pattern,) = compile_patterns([r"^(?P<greet>hello|hi)\b"])
    match = pattern.search("Hello there")
    assert match is not None
    assert match.group("greet") == "Hello"


def test_pending_is_frozen_but_carries_data() -> None:
    pending = Pending("email", "body", data={"to": "a@b.co"}, free_text=True)
    with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
        pending.slot = "other"  # type: ignore[misc]
    assert pending.free_text is True
