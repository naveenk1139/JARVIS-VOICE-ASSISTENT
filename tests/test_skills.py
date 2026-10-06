"""Behavioural tests for individual skills."""

from __future__ import annotations

import datetime as dt

import pytest

from jarvis.engine import Engine
from jarvis.models import Match, Pending
from jarvis.skills.calculator import CalculatorSkill, evaluate, verbal_to_symbols
from jarvis.skills.clock import TimeSkill, parse_duration
from jarvis.skills.news import NewsSkill
from jarvis.skills.smalltalk import SmallTalkSkill
from jarvis.skills.weather import WeatherSkill

from .conftest import run


# --------------------------------------------------------------------------- #
# smalltalk
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "utterance",
    ["hello jarvis", "are you there", "jarvis", "hey jarvis", "good morning"],
)
def test_greetings_are_recognised(engine: Engine, utterance: str) -> None:
    response = run(engine.handle(utterance))
    assert response.kind == "text"
    assert response.text


def test_identity_questions(engine: Engine) -> None:
    assert "JARVIS" in run(engine.handle("what is your name")).text
    assert "Intelligent System" in run(engine.handle("what does jarvis stand for")).text
    assert "software" in run(engine.handle("are you a robot")).text.lower()


# --------------------------------------------------------------------------- #
# calculator
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("expression", "expected"),
    [("2 + 2", 4), ("12 * 9", 108), ("100 / 8", 12.5), ("2 ** 10", 1024), ("17 % 5", 2)],
)
def test_safe_evaluation(expression: str, expected: float) -> None:
    assert evaluate(expression) == expected


@pytest.mark.parametrize(
    "hostile",
    ["__import__('os').system('echo hi')", "open('/etc/passwd')", "1 +", "9/0", "lambda: 1"],
)
def test_hostile_expressions_are_rejected(hostile: str) -> None:
    with pytest.raises(ValueError):
        evaluate(hostile)


@pytest.mark.parametrize(
    ("spoken", "symbolic"),
    [
        ("12 times 9", "12 * 9"),
        ("15 divided by 3", "15 / 3"),
        ("7 plus 8", "7 + 8"),
        ("2 to the power of 5", "2 ** 5"),
        ("10 squared", "10 **2"),
    ],
)
def test_verbal_maths(spoken: str, symbolic: str) -> None:
    assert verbal_to_symbols(spoken) == symbolic


def test_percentages(engine: Engine) -> None:
    response = run(engine.handle("what is 15% of 240"))
    assert "36" in response.text


def test_calculator_reports_division_by_zero(engine: Engine) -> None:
    response = run(engine.handle("calculate 5 divided by 0"))
    assert response.kind == "error"


# --------------------------------------------------------------------------- #
# time & reminders
# --------------------------------------------------------------------------- #
def test_time_and_date(engine: Engine) -> None:
    time_response = run(engine.handle("what time is it"))
    assert any(char.isdigit() for char in time_response.text)

    date_response = run(engine.handle("what is the date"))
    assert dt.datetime.now().strftime("%Y") in date_response.text


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("in 30 seconds", 30), ("in 5 minutes", 300), ("in 2 hours", 7200), ("in half an hour", 1800)],
)
def test_parse_duration(text: str, seconds: int) -> None:
    parsed = parse_duration(text)
    assert parsed is not None
    assert parsed[0] == seconds


def test_reminder_is_persisted(engine: Engine) -> None:
    response = run(engine.handle("remind me in 5 minutes to stretch"))
    assert "stretch" in response.text.lower()
    stored = engine.ctx.reminders.open_items()
    assert stored and stored[0].due_at is not None


def test_reminder_without_duration_asks_for_one(engine: Engine) -> None:
    response = run(engine.handle("set a reminder"))
    assert "how long" in response.text.lower()


def test_countdown_skill(engine: Engine) -> None:
    response = run(engine.handle("how long until 11:59 pm"))
    assert "in" in response.text.lower()


# --------------------------------------------------------------------------- #
# weather
# --------------------------------------------------------------------------- #
def test_weather_uses_configured_location(engine: Engine) -> None:
    response = run(engine.handle("what is the weather"))
    assert "Bengaluru" in response.text
    assert "27" in response.text  # from the canned forecast
    assert response.data["humidity"] == 62
    assert response.data["unit_symbol"] == "\u00b0C"


def test_weather_for_named_city(engine: Engine) -> None:
    response = run(engine.handle("weather in Mumbai"))
    assert response.kind == "text"
    assert response.skill == "weather"


def test_weather_network_failure_is_explained(offline_engine: Engine) -> None:
    response = run(offline_engine.handle("what is the weather"))
    assert response.kind == "error"
    assert "offline" in response.text.lower()


def test_location_question_returns_coordinates(engine: Engine) -> None:
    response = run(engine.handle("where am i"))
    assert "latitude" in response.text.lower()


# --------------------------------------------------------------------------- #
# news
# --------------------------------------------------------------------------- #
def test_headlines_are_read_and_pending_is_set(engine: Engine) -> None:
    response = run(engine.handle("what are the headlines"))
    assert response.kind == "list"
    assert len(response.data["headlines"]) == 3
    assert "ISRO" in response.text
    assert response.pending is not None


@pytest.mark.parametrize("follow_up", ["open the second one", "read the second headline", "number 2"])
def test_follow_up_opens_the_requested_headline(engine: Engine, follow_up: str) -> None:
    run(engine.handle("read the news"))
    response = run(engine.handle(follow_up))
    assert response.url == "https://example.test/monsoon"


def test_follow_up_yes_opens_the_first(engine: Engine) -> None:
    run(engine.handle("read the news"))
    assert run(engine.handle("yes")).url == "https://example.test/isro"


def test_follow_up_no_is_polite(engine: Engine) -> None:
    run(engine.handle("read the news"))
    response = run(engine.handle("no thanks"))
    assert response.kind == "text"
    assert "headlines" in response.text


def test_news_by_topic_filters(engine: Engine) -> None:
    response = run(engine.handle("what are the headlines about chess"))
    assert "chess" in response.text.lower()


# --------------------------------------------------------------------------- #
# knowledge
# --------------------------------------------------------------------------- #
def test_wikipedia_question(engine: Engine) -> None:
    response = run(engine.handle("who is Ada Lovelace"))
    assert "mathematician" in response.text
    assert response.url == "https://en.wikipedia.org/wiki/Ada_Lovelace"


def test_wikipedia_article_follow_up(engine: Engine) -> None:
    run(engine.handle("tell me about Ada Lovelace"))
    response = run(engine.handle("yes please"))
    assert response.data["action"] == "open_last_url"
    assert response.url == "https://en.wikipedia.org/wiki/Ada_Lovelace"


def test_dictionary_defines_offline_words(engine: Engine) -> None:
    response = run(engine.handle("define serendipity"))
    assert response.data["word"] == "serendipity"
    assert response.text


def test_dictionary_unknown_word_offline(offline_engine: Engine) -> None:
    response = run(offline_engine.handle("define zzzqqq"))
    assert response.kind == "error"


def test_spelling(engine: Engine) -> None:
    response = run(engine.handle("spell jarvis"))
    assert response.data["spelling"] == list("JARVIS")


# --------------------------------------------------------------------------- #
# web / notes / jokes / system / help
# --------------------------------------------------------------------------- #
def test_known_site_opens(engine: Engine) -> None:
    assert run(engine.handle("open youtube")).url == "https://www.youtube.com"


def test_unknown_site_falls_back_to_search(engine: Engine) -> None:
    response = run(engine.handle("open flibbertigibbet"))
    assert "google.com/search" in (response.url or "")


def test_web_search(engine: Engine) -> None:
    response = run(engine.handle("search for isro chandrayaan"))
    assert response.url and "chandrayaan" in response.url


def test_youtube_search(engine: Engine) -> None:
    response = run(engine.handle("search youtube for lo-fi beats"))
    assert "youtube.com/results" in (response.url or "")


def test_maps_lookup(engine: Engine) -> None:
    response = run(engine.handle("where is cubbon park on the map"))
    assert "google.com/maps" in (response.url or "")


def test_notes_lifecycle(engine: Engine) -> None:
    added = run(engine.handle("add buy milk to my to-do list"))
    assert "buy milk" in added.text
    listing = run(engine.handle("what are my notes"))
    assert "buy milk" in listing.text
    done = run(engine.handle("mark the first task as done"))
    assert "buy milk" in done.text
    assert engine.ctx.notes.open_items() == []


def test_memory_round_trip(engine: Engine) -> None:
    run(engine.handle("remember that the wifi password is hunter2"))
    response = run(engine.handle("what do you remember"))
    assert "hunter2" in response.text

    run(engine.handle("forget the wifi password"))
    assert "hunter2" not in run(engine.handle("what do you remember")).text


def test_notes_clear(engine: Engine) -> None:
    run(engine.handle("add water the plants to my list"))
    response = run(engine.handle("clear my notes"))
    assert "cleared" in response.text.lower()


def test_jokes_are_local_and_varied() -> None:
    from jarvis.services.jokes import LOCAL_JOKES

    assert len(set(LOCAL_JOKES)) >= 20
    assert all(joke[0].isupper() for joke in LOCAL_JOKES)


def test_help_lists_skills(engine: Engine) -> None:
    response = run(engine.handle("what can you do"))
    assert response.kind == "list"
    assert response.data["count"] >= 10
    names = {skill["name"] for skill in response.data["skills"]}
    assert {"weather", "news", "notes", "calculator"} <= names


def test_music_without_configuration_explains_itself(engine: Engine) -> None:
    response = run(engine.handle("play music"))
    assert response.kind == "error"
    assert "JARVIS_MUSIC_DIR" in response.text


# --------------------------------------------------------------------------- #
# email
# --------------------------------------------------------------------------- #
def test_email_is_gated_until_configured(engine: Engine) -> None:
    response = run(engine.handle("send an email to someone@example.com"))
    assert response.kind == "error"
    assert "JARVIS_SMTP_USER" in response.text
    assert response.data["configured"] is False


def test_email_slot_filling_and_delivery(engine: Engine, monkeypatch) -> None:
    engine.config.smtp_user = "me@example.com"
    engine.config.smtp_password = "app-password"
    delivered: list[dict[str, str]] = []

    async def fake_send(self, message):  # noqa: ANN001
        delivered.append(
            {"to": message["To"], "subject": message["Subject"], "body": message.get_content().strip()}
        )

    from jarvis.skills.email import EmailSender

    monkeypatch.setattr(EmailSender, "send_async", fake_send)

    first = run(engine.handle("send an email to priya@example.com about the release"))
    assert first.pending is not None and first.pending.slot == "body"

    run(engine.handle("the build is green, ship it"))
    confirmed = run(engine.handle("send"))

    assert confirmed.data["sent"]["to"] == "priya@example.com"
    assert delivered == [
        {"to": "priya@example.com", "subject": "the release", "body": "the build is green, ship it"}
    ]


def test_email_can_be_cancelled(engine: Engine) -> None:
    engine.config.smtp_user = "me@example.com"
    engine.config.smtp_password = "secret"
    run(engine.handle("send an email to a@b.co"))
    run(engine.handle("quarterly numbers"))
    run(engine.handle("hello"))
    response = run(engine.handle("cancel"))
    assert "nothing was sent" in response.text.lower()


# --------------------------------------------------------------------------- #
# unit-level skill checks
# --------------------------------------------------------------------------- #
def test_skill_matching_carries_named_groups(config) -> None:
    from jarvis.context import AppContext
    from jarvis.services.http import HttpClient

    ctx = AppContext(config, HttpClient(offline=True))
    skill = WeatherSkill(ctx)
    match = skill.match("weather in delhi")
    assert isinstance(match, Match)
    assert match.group("location") == "delhi"


def test_unknown_site_is_still_a_valid_match(config) -> None:
    from jarvis.context import AppContext
    from jarvis.services.http import HttpClient

    ctx = AppContext(config, HttpClient(offline=True))
    assert SmallTalkSkill(ctx).match("hello there") is not None
    assert CalculatorSkill(ctx).match("calculate 2+2") is not None
    assert NewsSkill(ctx).match("what are the headlines") is not None
    assert TimeSkill(ctx).match("what time is it") is not None


def test_resume_without_context_is_handled(engine: Engine) -> None:
    """A stale pending shouldn't crash when the slot is unknown."""
    skill = engine.registry.get("time")
    response = run(skill.resume(Pending(skill="time", slot="unknown"), "hello"))  # type: ignore[union-attr]
    assert response.kind == "error"


def test_offline_wikipedia_returns_a_friendly_error(offline_engine: Engine) -> None:
    """ServiceError is converted into a speakable message, never a traceback."""
    skill = offline_engine.registry.get("wikipedia")
    match = skill.match("who is Ada Lovelace")  # type: ignore[union-attr]
    response = run(skill.handle(match, "who is Ada Lovelace"))  # type: ignore[union-attr]
    assert response.kind == "error"
    assert "offline" in response.text.lower()
