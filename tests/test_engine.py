"""Engine-level behaviour: routing, follow-ups, errors and sessions."""

from __future__ import annotations

import asyncio

from jarvis.engine import Engine
from jarvis.models import Response, ServiceError
from jarvis.skills.base import Skill

from .conftest import run


def test_routes_to_the_right_skill(engine: Engine) -> None:
    response = run(engine.handle("what is your name"))
    assert response.skill == "smalltalk"
    assert "JARVIS" in response.text


def test_calculator_wins_over_wikipedia_for_arithmetic(engine: Engine) -> None:
    response = run(engine.handle("what is 12 times 9"))
    assert response.skill == "calculator"
    assert "108" in response.text


def test_unknown_input_hits_the_fallback_brain(engine: Engine) -> None:
    response = run(engine.handle("quantum entanglement in potatoes explained simply"))
    assert response.kind == "error"
    assert response.skill == "fallback"
    assert response.data["unmatched"]


def test_empty_utterance_is_rejected(engine: Engine) -> None:
    response = run(engine.handle("   "))
    assert response.kind == "error"


def test_persona_switch_updates_config_and_response(engine: Engine) -> None:
    response = run(engine.handle("switch to friday"))
    assert response.data["action"] == "set_persona"
    assert response.data["persona"] == "friday"
    assert engine.config.persona == "friday"
    assert response.persona == "friday"


def test_pending_slot_is_answered_by_the_same_skill(offline_engine: Engine, monkeypatch) -> None:
    """A pending question consumes the next utterance."""
    engine = offline_engine

    async def fake_headlines(*, limit: int = 5, force: bool = False):
        from jarvis.services.news import Headline

        return [Headline(title="First story", url="https://a.test/1", source="Test")]

    monkeypatch.setattr(type(engine.ctx.news), "headlines", staticmethod(fake_headlines))
    run(engine.handle("what are the headlines"))
    assert engine.get_session("default").pending is not None

    follow_up = run(engine.handle("open the first one"))
    assert follow_up.url == "https://a.test/1"


def test_new_command_interrupts_a_pending_question(engine: Engine) -> None:
    run(engine.handle("define serendipity"))
    assert engine.get_session("default").pending is not None

    response = run(engine.handle("what time is it"))
    assert response.skill == "time"
    assert engine.get_session("default").pending is None


def test_exit_signal_marks_the_session_ended(engine: Engine) -> None:
    response = run(engine.handle("go to sleep"))
    assert response.kind == "exit"
    assert engine.get_session("default").ended is True


def test_session_reset_clears_pending(engine: Engine) -> None:
    run(engine.handle("define serendipity"))
    engine.reset_session("default")
    assert engine.get_session("default").pending is None


def test_crashing_skill_is_contained(config, monkeypatch) -> None:
    class Boom(Skill):
        name = "boom"
        description = "always fails"
        priority = 1
        patterns = (r"(?P<boom>explode now)",)

        async def handle(self, match, text):  # type: ignore[override]
            raise RuntimeError("kaboom")

    engine = Engine(config, skills=[Boom])
    response = run(engine.handle("explode now"))
    assert response.kind == "error"
    assert "boom" in response.skill


def test_service_error_becomes_a_friendly_message(config) -> None:
    class Failing(Skill):
        name = "failing"
        description = "raises ServiceError"
        priority = 1
        patterns = (r"(?P<fail>trigger failure)",)

        async def handle(self, match, text):  # type: ignore[override]
            raise ServiceError("the weather API is down", service="weather")

    engine = Engine(config, skills=[Failing])
    response = run(engine.handle("trigger failure"))
    assert response.kind == "error"
    assert "weather API is down" in response.text


def test_slow_skill_times_out(config) -> None:
    class Slow(Skill):
        name = "slow"
        description = "never finishes in time"
        priority = 1
        patterns = (r"(?P<slow>take your time)",)

        async def handle(self, match, text):  # type: ignore[override]
            await asyncio.sleep(5)
            return Response.ok("finally")

    config.skill_timeout = 0.05
    engine = Engine(config, skills=[Slow])
    response = run(engine.handle("take your time"))
    assert response.kind == "error"
    assert "too long" in response.text


def test_history_records_both_sides(engine: Engine) -> None:
    run(engine.handle("what time is it"))
    turns = engine.ctx.history.recent()
    assert [turn.role for turn in turns] == ["user", "jarvis"]
    assert turns[0].text == "what time is it"


def test_suggestions_come_from_the_catalog(engine: Engine) -> None:
    suggestions = engine.suggestions(4)
    assert len(suggestions) == 4
    assert all(isinstance(item, str) for item in suggestions)


def test_describe_reports_state(engine: Engine) -> None:
    described = engine.describe()
    assert described["name"] == "JARVIS"
    assert described["skills"] >= 10
    assert described["brain"] in {"none", "llm"}


def test_custom_skill_can_be_registered(config) -> None:
    class Echo(Skill):
        name = "echo"
        description = "repeat the last words"
        priority = 1
        patterns = (r"^say (?P<text>.+)$",)

        async def handle(self, match, text):  # type: ignore[override]
            return Response.ok(f"You said {match.group('text')}")

    engine = Engine(config, skills=[Echo])
    assert run(engine.handle("say hello world")).text == "You said hello world"


def test_plugin_brain_is_used_when_available(engine: Engine) -> None:
    class AlwaysBrain:
        name = "llm"

        @property
        def available(self) -> bool:
            return True

        async def answer(self, question, history=()):  # type: ignore[no-untyped-def]
            return Response.ok(f"Think about {question}", skill="llm")

    engine.brain = AlwaysBrain()  # type: ignore[assignment]
    response = run(engine.handle("why is the sky blue"))
    assert response.skill == "llm"
    assert "sky blue" in response.text


def test_pending_free_text_slot_is_not_stolen(engine: Engine, monkeypatch) -> None:
    """Email bodies must reach the email skill even if they look like commands."""
    engine.config.smtp_user = "me@example.com"
    engine.config.smtp_password = "secret"

    sent: list[str] = []

    async def fake_send(self, message):  # noqa: ANN001
        sent.append(message["To"])

    from jarvis.skills.email import EmailSender

    monkeypatch.setattr(EmailSender, "send_async", fake_send)

    run(engine.handle("send an email to a@b.co about lunch"))
    run(engine.handle("what time is it"))  # subject: free-form, must not be hijacked
    run(engine.handle("meet me at 1 pm"))
    final = run(engine.handle("send"))

    assert sent == ["a@b.co"]
    assert "sent" in final.data
