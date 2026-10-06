"""Configuration for J.A.R.V.I.S.

Configuration comes from three places, in increasing order of precedence:

1. Built-in defaults (safe, no secrets, cross-platform).
2. A ``.env`` file in the project root (optional, never committed).
3. Real environment variables.

Keeping this dependency-free means the core engine installs and runs anywhere,
even before the desktop extras (pyttsx3 / PyAudio / OpenCV) are present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

DEFAULT_NEWS_FEEDS: tuple[str, ...] = (
    "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    "https://www.thehindu.com/news/national/feeder/default.rss",
)

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _as_bool(value: str | bool, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in _TRUTHY


def _as_list(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return tuple(part.strip() for part in value.split(",") if part.strip())


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Minimal ``.env`` reader (no python-dotenv dependency)."""
    path = path or PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


@dataclass(slots=True)
class Config:
    """Runtime configuration for the assistant."""

    # --- identity -----------------------------------------------------------
    assistant_name: str = "JARVIS"
    user_title: str = "Sir"
    user_name: str = ""
    persona: str = "jarvis"  # "jarvis" (masculine) or "friday" (feminine)

    # --- location & weather -------------------------------------------------
    location: str = ""  # blank -> auto-detect from IP, then fall back to default
    fallback_location: str = "Bengaluru"
    units: str = "metric"  # "metric" or "imperial"

    # --- news ---------------------------------------------------------------
    news_feeds: tuple[str, ...] = DEFAULT_NEWS_FEEDS
    news_source: str = "Google News India"
    news_api_key: str = ""  # optional; when set, newsapi.org is used instead of RSS
    news_country: str = "in"

    # --- dictionary ---------------------------------------------------------
    dictionary_path: Path = PACKAGE_ROOT / "data" / "dictionary.json"

    # --- storage ------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"

    # --- email (optional; skill explains itself when unset) ------------------
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_default_to: str = ""

    # --- media --------------------------------------------------------------
    music_dir: str = ""

    # --- optional language-model fallback -----------------------------------
    llm_provider: str = "openai"  # "openai" (chat/completions) or "anthropic"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""  # blank -> provider default
    llm_max_tokens: int = 300
    llm_temperature: float = 0.4
    llm_system_prompt: str = ""

    # --- networking ---------------------------------------------------------
    http_timeout: float = 10.0
    http_retries: int = 2
    user_agent: str = "JARVIS-Voice-Assistant/2.0 (+https://github.com/naveenk1139/JARVIS-VOICE-ASSISTENT)"

    # --- desktop front door -------------------------------------------------
    chrome_path: str = ""  # blank -> auto-detect per platform
    voice_rate: int = 180
    voice_index_masculine: int = 0
    voice_index_feminine: int = 1
    wake_word: str = ""  # optional; blank -> always listening

    # --- face unlock (desktop only, optional) -------------------------------
    require_face_unlock: bool = False
    face_model_path: str = "Face-Recognition/trainer/trainer.yml"
    face_cascade_path: str = "Face-Recognition/haarcascade_frontalface_default.xml"
    face_owner_name: str = ""

    # --- server -------------------------------------------------------------
    web_host: str = "0.0.0.0"
    #: optional shared secret; when set, API calls must send X-JARVIS-Token
    api_token: str = ""
    web_port: int = 8000
    session_ttl_seconds: int = 60 * 60 * 4
    history_limit: int = 50

    # --- misc ---------------------------------------------------------------
    skill_timeout: float = 25.0
    log_level: str = "INFO"
    offline: bool = False  # when true, network skills answer from local data only

    #: Fields whose env names differ from the attribute name.
    _ALTERNATES: dict[str, str] = field(
        default_factory=lambda: {"assistant_name": "JARVIS_NAME", "web_port": "PORT"},
        repr=False,
    )

    # ------------------------------------------------------------------ public
    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        """Build a config from ``os.environ`` merged with an optional ``.env``."""
        merged: dict[str, str] = dict(load_dotenv())
        merged.update(os.environ if env is None else env)

        aliases = {"JARVIS_NAME": "assistant_name", "PORT": "web_port"}
        kwargs: dict[str, object] = {}
        for f in fields(cls):
            if f.name.startswith("_") or f.name in {"news_feeds"}:
                continue
            env_key = f"JARVIS_{f.name.upper()}"
            raw = merged.get(env_key)
            if raw is None:
                raw = next(
                    (merged[k] for k, target in aliases.items() if target == f.name and k in merged),
                    None,
                )
            if raw is None or raw == "":
                continue
            kwargs[f.name] = cls._coerce(f.type, raw)

        # news feeds are a list, handled separately to allow comma separation
        raw_feeds = merged.get("JARVIS_NEWS_FEEDS")
        if raw_feeds:
            kwargs["news_feeds"] = _as_list(raw_feeds)

        if merged.get("JARVIS_DICTIONARY_PATH"):
            kwargs["dictionary_path"] = Path(merged["JARVIS_DICTIONARY_PATH"]).expanduser()
        if merged.get("JARVIS_DATA_DIR"):
            kwargs["data_dir"] = Path(merged["JARVIS_DATA_DIR"]).expanduser()

        return cls(**kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _coerce(declared: object, raw: str) -> object:
        name = str(declared)
        if name in {"bool", "Optional[bool]"}:
            return _as_bool(raw)
        if name in {"int", "Optional[int]"}:
            return int(raw)
        if name in {"float", "Optional[float]"}:
            return float(raw)
        if name in {"Path"}:
            return Path(raw).expanduser()
        return raw.strip()

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_user and self.smtp_password)

    @property
    def dictionary_available(self) -> bool:
        return Path(self.dictionary_path).is_file()

    def ensure_dirs(self) -> None:
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)

    def display_name(self) -> str:
        """How the assistant addresses the user."""
        if self.user_name:
            return self.user_name
        return self.user_title or "there"
