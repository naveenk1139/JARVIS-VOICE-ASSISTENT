"""Application context handed to every skill."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Config
from .services.dictionary import DictionaryService
from .services.http import HttpClient
from .services.jokes import JokeService
from .services.news import NewsService
from .services.system import SystemService
from .services.weather import WeatherService
from .services.wikipedia import WikipediaService
from .services.youtube import YouTubeService
from .storage import History, MemoryStore, NoteStore, ReminderStore

if TYPE_CHECKING:  # pragma: no cover
    pass


@dataclass(slots=True)
class AppContext:
    """Everything a skill may need: config, HTTP client, services and stores.

    Services and stores are created lazily and cached, so a skill that never
    touches the network never pays for it - important for CLI one-shots and for
    the offline mode used in tests.
    """

    config: Config
    http: HttpClient
    session_id: str = field(default_factory=lambda: secrets.token_hex(8))
    _services: dict[str, object] = field(default_factory=dict, init=False, repr=False)
    _stores: dict[str, object] = field(default_factory=dict, init=False, repr=False)
    _history: History | None = field(default=None, init=False, repr=False)
    #: set by :class:`~jarvis.engine.Engine` so skills can introspect each other
    registry: object | None = field(default=None, init=False, repr=False)

    # ----------------------------------------------------------------- helpers
    @property
    def data_dir(self) -> Path:
        path = Path(self.config.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def store(self, filename: str) -> Path:
        return self.data_dir / filename

    # ---------------------------------------------------------------- services
    def _service(self, key: str, factory):  # type: ignore[no-untyped-def]
        if key not in self._services:
            self._services[key] = factory(self)
        return self._services[key]

    @property
    def weather(self) -> WeatherService:
        return self._service("weather", WeatherService)  # type: ignore[return-value]

    @property
    def news(self) -> NewsService:
        return self._service("news", NewsService)  # type: ignore[return-value]

    @property
    def wikipedia(self) -> WikipediaService:
        return self._service("wikipedia", WikipediaService)  # type: ignore[return-value]

    @property
    def dictionary(self) -> DictionaryService:
        return self._service("dictionary", DictionaryService)  # type: ignore[return-value]

    @property
    def jokes(self) -> JokeService:
        return self._service("jokes", JokeService)  # type: ignore[return-value]

    @property
    def system(self) -> SystemService:
        return self._service("system", SystemService)  # type: ignore[return-value]

    @property
    def youtube(self) -> YouTubeService:
        return self._service("youtube", YouTubeService)  # type: ignore[return-value]

    # ------------------------------------------------------------------- stores
    def _store(self, key: str, factory):  # type: ignore[no-untyped-def]
        if key not in self._stores:
            self._stores[key] = factory(self.data_dir)
        return self._stores[key]

    @property
    def notes(self) -> NoteStore:
        return self._store("notes", NoteStore)  # type: ignore[return-value]

    @property
    def reminders(self) -> ReminderStore:
        return self._store("reminders", ReminderStore)  # type: ignore[return-value]

    @property
    def memory(self) -> MemoryStore:
        return self._store("memory", MemoryStore)  # type: ignore[return-value]

    @property
    def history(self) -> History:
        if self._history is None:
            self._history = History(self.config.history_limit)
        return self._history
