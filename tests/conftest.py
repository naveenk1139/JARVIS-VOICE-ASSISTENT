"""Shared fixtures.

Tests run fully offline: no microphone, no camera, no network. Network-backed
skills are exercised against a stubbed HTTP layer, so the suite is deterministic
and safe to run in CI.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from jarvis.config import Config
from jarvis.engine import Engine
from jarvis.services.http import HttpClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DICTIONARY = PROJECT_ROOT / "jarvis" / "data" / "dictionary.json"


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute a coroutine without requiring pytest-asyncio."""
    return asyncio.run(coro)


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    return Config(
        offline=False,
        data_dir=tmp_path,
        dictionary_path=DICTIONARY,
        location="Bengaluru",
        news_feeds=("https://example.test/rss",),
    )


class StubHttp:
    """Replacement for :class:`~jarvis.services.http.HttpClient` with canned replies."""

    def __init__(
        self, responses: dict[str, Any] | None = None, *, text_responses: dict[str, str] | None = None
    ):
        self.responses = responses or {}
        self.text_responses = text_responses or {}
        self.calls: list[tuple[str, str]] = []

    def _match(self, table: dict[str, Any], url: str) -> Any:
        for fragment, payload in table.items():
            if fragment in url:
                self.calls.append((fragment, url))
                if callable(payload):
                    return payload()
                return payload
        raise AssertionError(f"unexpected HTTP call: {url}")

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None, service: str = "http") -> Any:
        payload = self._match(self.responses, url)
        if isinstance(payload, Exception):
            raise payload
        return payload

    async def get_text(self, url: str, *, params: dict[str, Any] | None = None, service: str = "http") -> str:
        return self._match(self.text_responses, url)

    async def post_json(self, url: str, **kwargs: Any) -> Any:
        return self._match(self.responses, url)

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def stub_http() -> Callable[..., StubHttp]:
    return StubHttp


@pytest.fixture()
def engine(config: Config, stub_http: Callable[..., StubHttp]) -> Engine:
    """Engine wired to canned API data."""
    from tests.fixtures import RESPONSES, TEXT_RESPONSES  # local import keeps the fixture cheap

    http = stub_http(RESPONSES, text_responses=TEXT_RESPONSES)
    eng = Engine(config, http=http)  # type: ignore[arg-type]
    yield eng
    run(eng.aclose())


@pytest.fixture()
def offline_engine(config: Config) -> Engine:
    eng = Engine(config, http=HttpClient(offline=True))  # type: ignore[arg-type]
    yield eng
    run(eng.aclose())


def load_json(name: str) -> dict[str, Any]:
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8"))
