from __future__ import annotations

from pathlib import Path

from jarvis.config import Config, load_dotenv


def test_defaults_are_safe() -> None:
    config = Config()
    assert config.assistant_name == "JARVIS"
    assert config.offline is False
    assert config.email_enabled is False  # never send mail until configured
    assert config.require_face_unlock is False  # never block startup on a camera
    assert config.display_name() == "Sir"


def test_env_overrides_and_type_coercion(monkeypatch) -> None:
    env = {
        "JARVIS_NAME": "FRIDAY",
        "JARVIS_PERSONA": "friday",
        "JARVIS_OFFLINE": "true",
        "JARVIS_WEB_PORT": "9123",
        "JARVIS_UNITS": "imperial",
        "JARVIS_VOICE_RATE": "200",
        "JARVIS_NEWS_FEEDS": "https://a.test/rss, https://b.test/rss",
    }
    config = Config.from_env(env)
    assert config.assistant_name == "FRIDAY"
    assert config.persona == "friday"
    assert config.offline is True
    assert config.web_port == 9123
    assert config.voice_rate == 200
    assert config.news_feeds == ("https://a.test/rss", "https://b.test/rss")


def test_port_alias_is_honoured() -> None:
    assert Config.from_env({"PORT": "7000"}).web_port == 7000


def test_email_enabled_requires_both_fields() -> None:
    assert Config(smtp_user="me@example.com").email_enabled is False
    assert Config(smtp_user="me@example.com", smtp_password="secret").email_enabled is True


def test_load_dotenv_parses_quotes_and_comments(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nJARVIS_LOCATION=\"New Delhi\"\nJARVIS_USER_TITLE='Captain'\n\nJARVIS_UNITS=metric\n",
        encoding="utf-8",
    )
    values = load_dotenv(env_file)
    assert values["JARVIS_LOCATION"] == "New Delhi"
    assert values["JARVIS_USER_TITLE"] == "Captain"
    assert values["JARVIS_UNITS"] == "metric"


def test_missing_dotenv_is_not_an_error(tmp_path: Path) -> None:
    assert load_dotenv(tmp_path / "nope.env") == {}


def test_ensure_dirs_and_store_paths(tmp_path: Path) -> None:
    config = Config(data_dir=tmp_path / "nested" / "data")
    config.ensure_dirs()
    assert (tmp_path / "nested" / "data").is_dir()


def test_dictionary_available_flag(tmp_path: Path) -> None:
    corpus = tmp_path / "dict.json"
    corpus.write_text('{"word": ["a definition"]}', encoding="utf-8")
    assert Config(dictionary_path=corpus).dictionary_available is True
    assert Config(dictionary_path=tmp_path / "missing.json").dictionary_available is False
