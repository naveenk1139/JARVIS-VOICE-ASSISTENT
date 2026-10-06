"""Desktop extras: speakers, listeners, the assistant loop and face unlock.

Everything here is import-guarded so the suite passes on a machine without
audio devices, a camera or the optional dependencies installed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from jarvis.config import Config
from jarvis.desktop import DesktopAssistant
from jarvis.engine import Engine
from jarvis.models import Response
from jarvis.security.face_unlock import FaceUnlock, UnlockResult, UnlockStatus, unlock_if_enabled
from jarvis.services.http import HttpClient
from jarvis.voice.listener import TextListener, WakeWordListener, build_listener
from jarvis.voice.speaker import NullSpeaker, build_speaker

from .conftest import run


# --------------------------------------------------------------------------- #
# Speakers & listeners
# --------------------------------------------------------------------------- #
def test_null_speaker_is_the_safe_default(config: Config) -> None:
    speaker = build_speaker(config, prefer="null")
    assert isinstance(speaker, NullSpeaker)
    speaker.speak("hello")  # must not raise
    speaker.set_persona("friday")
    speaker.close()


def test_speaker_builder_never_crashes_without_optional_deps(config: Config) -> None:
    speaker = build_speaker(config)
    speaker.speak("testing")  # falls back to the console when pyttsx3 is absent
    speaker.close()


def test_text_listener_reads_stdin(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": "what time is it")
    assert TextListener().listen() == "what time is it"


def test_text_listener_exits_on_eof(monkeypatch) -> None:
    def boom(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    assert TextListener().listen() == "exit"


def test_build_listener_prefers_text_when_asked(config: Config) -> None:
    assert build_listener(config, prefer="text").name == "text"


def test_build_listener_falls_back_from_missing_microphone(config: Config) -> None:
    listener = build_listener(config, prefer="auto")
    assert listener.name in {"microphone", "text"}


class ScriptedListener:
    name = "scripted"

    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)

    def listen(self) -> str:
        return self.lines.pop(0) if self.lines else "exit"

    def close(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# Wake word
# --------------------------------------------------------------------------- #
def test_wake_word_filters_and_strips() -> None:
    listener = WakeWordListener(ScriptedListener(["what's the weather", "jarvis open youtube"]), ["jarvis"])
    assert listener.listen() == "open youtube"


def test_wake_word_passes_bare_command_when_only_the_word_was_said() -> None:
    listener = WakeWordListener(ScriptedListener(["jarvis"]), ["jarvis"])
    assert listener.listen() == "jarvis"


def test_wake_word_returns_empty_for_silence() -> None:
    listener = WakeWordListener(ScriptedListener([""]), ["jarvis"])
    assert listener.listen() == ""


# --------------------------------------------------------------------------- #
# Desktop loop
# --------------------------------------------------------------------------- #
def test_desktop_loop_runs_commands_and_exits(config: Config) -> None:
    listener = ScriptedListener(["what time is it", "what is your name", "exit"])
    speaker = NullSpeaker(echo=False)
    engine = Engine(config, http=HttpClient(offline=True))
    assistant = DesktopAssistant(config, engine=engine, speaker=speaker, listener=listener)

    async def scenario() -> None:
        # greet() and the main loop share the same listener queue
        await assistant.run()

    run(scenario())
    assert len(listener.lines) == 0  # every scripted line was consumed


def test_turn_returns_false_on_exit(config: Config) -> None:
    listener = ScriptedListener(["goodbye"])
    engine = Engine(config, http=HttpClient(offline=True))
    assistant = DesktopAssistant(
        config, engine=engine, speaker=NullSpeaker(echo=False), listener=ScriptedListener(["goodbye"])
    )

    async def scenario() -> bool:
        return await assistant._turn()

    assert run(scenario()) is False
    run(engine.aclose())
    del listener


def test_present_prints_links(config: Config, capsys) -> None:
    engine = Engine(config, http=HttpClient(offline=True))
    assistant = DesktopAssistant(
        config, engine=engine, speaker=NullSpeaker(echo=False), listener=TextListener()
    )
    assistant._present(Response.link("Opening YouTube.", "https://youtube.com"), speak=False)
    captured = capsys.readouterr().out
    assert "Opening YouTube." in captured
    assert "https://youtube.com" in captured
    run(engine.aclose())


# --------------------------------------------------------------------------- #
# Face unlock
# --------------------------------------------------------------------------- #
def test_face_unlock_disabled_by_default(config: Config) -> None:
    result = unlock_if_enabled(config)
    assert result.status is UnlockStatus.DISABLED
    assert result.unlocked is False


def test_face_unlock_reports_missing_model(config: Config, tmp_path: Path) -> None:
    unlocker = FaceUnlock(model_path=tmp_path / "trainer.yml", cascade_path=tmp_path / "cascade.xml")
    result = unlocker.run()
    assert result.status in {UnlockStatus.MODEL_MISSING, UnlockStatus.DEPENDENCY_MISSING}
    assert result.unlocked is False


def test_face_unlock_availability_without_dependencies(tmp_path: Path) -> None:
    unlocker = FaceUnlock(model_path=tmp_path / "m.yml", cascade_path=tmp_path / "c.xml")
    result = unlocker.availability()
    assert result is not None  # either cv2 or the files are missing in CI
    assert result.status in {UnlockStatus.MODEL_MISSING, UnlockStatus.DEPENDENCY_MISSING}


def test_train_faces_without_images(tmp_path: Path) -> None:
    from jarvis.security.face_unlock import train_faces

    count, message = train_faces(
        dataset_dir=tmp_path, model_path=tmp_path / "trainer.yml", cascade_path=tmp_path / "cascade.xml"
    )
    assert count == 0
    assert "No training images" in message


def test_unlock_result_helper() -> None:
    assert UnlockResult(UnlockStatus.SUCCESS, "welcome").unlocked is True
    assert UnlockResult(UnlockStatus.FAILED, "nope").unlocked is False


def test_slow_listener_does_not_block_the_loop(config: Config) -> None:
    """Listening happens in a worker thread, so the event loop stays responsive."""

    class SlowListener:
        name = "slow"

        def listen(self) -> str:
            import time

            time.sleep(0.05)
            return "exit"

        def close(self) -> None:
            return None

    engine = Engine(config, http=HttpClient(offline=True))
    assistant = DesktopAssistant(
        config, engine=engine, speaker=NullSpeaker(echo=False), listener=SlowListener()
    )

    async def scenario() -> bool:
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            for _ in range(4):
                await asyncio.sleep(0.02)
                ticks += 1

        _, returned = await asyncio.gather(ticker(), assistant._turn())
        assert ticks >= 3, "the event loop should have kept running while listening"
        return returned

    assert run(scenario()) is False
    run(engine.aclose())
