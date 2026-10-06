"""Text-to-speech back ends for the desktop app.

``pyttsx3`` is used when available; otherwise the OS tools (``say`` on macOS,
``espeak-ng``/``espeak`` on Linux, PowerShell's SAPI bridge on Windows) are
tried, and finally a console-only speaker keeps everything working headless.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
import sys
from typing import Protocol

log = logging.getLogger(__name__)


class Speaker(Protocol):
    name: str

    def speak(self, text: str) -> None: ...
    def set_persona(self, persona: str) -> None: ...
    def close(self) -> None: ...


class NullSpeaker:
    """Prints instead of talking - used in tests and headless environments."""

    name = "null"

    def __init__(self, echo: bool = True) -> None:
        self.echo = echo
        self.persona = "jarvis"

    def speak(self, text: str) -> None:
        if self.echo:
            print(f"JARVIS: {text}")

    def set_persona(self, persona: str) -> None:
        self.persona = persona

    def close(self) -> None:  # pragma: no cover - nothing to release
        return None


class Pyttsx3Speaker:
    """Cross-platform offline TTS through ``pyttsx3``."""

    name = "pyttsx3"

    def __init__(
        self, *, rate: int = 180, persona: str = "jarvis", masculine_index: int = 0, feminine_index: int = 1
    ) -> None:
        import pyttsx3  # imported lazily: the core has no hard dependency

        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._voices = list(self._engine.getProperty("voices"))
        self._masculine = masculine_index
        self._feminine = feminine_index
        self.set_persona(persona)

    def set_persona(self, persona: str) -> None:
        index = self._feminine if persona == "friday" else self._masculine
        if 0 <= index < len(self._voices):
            self._engine.setProperty("voice", self._voices[index].id)
        else:
            log.info("Voice index %s unavailable; keeping the default voice", index)

    def speak(self, text: str) -> None:
        self._engine.say(text)
        self._engine.runAndWait()

    def close(self) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            self._engine.stop()


class CommandSpeaker:
    """Falls back to the operating system's own speech command."""

    name = "system"

    def __init__(self, persona: str = "jarvis") -> None:
        self.persona = persona
        self._command = self._detect()

    @staticmethod
    def _detect() -> list[str] | None:
        if sys.platform == "darwin" and shutil.which("say"):
            return ["say"]
        for candidate in ("espeak-ng", "espeak"):
            if shutil.which(candidate):
                return [candidate, "-s", "160"]
        if sys.platform.startswith("win") and shutil.which("powershell"):
            return [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Speak($args[0])",
            ]
        return None

    @property
    def available(self) -> bool:
        return self._command is not None

    def set_persona(self, persona: str) -> None:
        self.persona = persona

    def speak(self, text: str) -> None:
        if not self._command:
            return
        try:
            subprocess.run([*self._command, text], check=False, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            log.warning("System speaker failed: %s", exc)

    def close(self) -> None:  # pragma: no cover
        return None


def build_speaker(config, *, prefer: str = "auto") -> Speaker:
    """Pick the best available speaker: pyttsx3 -> OS command -> console."""
    order = (
        (
            "pyttsx3",
            lambda: Pyttsx3Speaker(
                rate=config.voice_rate,
                persona=config.persona,
                masculine_index=config.voice_index_masculine,
                feminine_index=config.voice_index_feminine,
            ),
        ),
        ("system", lambda: CommandSpeaker(persona=config.persona)),
        ("null", lambda: NullSpeaker()),
    )
    for name, factory in order:
        if prefer not in ("auto", name):
            continue
        try:
            speaker = factory()
        except Exception as exc:  # ImportError, missing audio device, ...
            log.info("Speaker backend %s unavailable: %s", name, exc)
            continue
        if isinstance(speaker, CommandSpeaker) and not speaker.available:
            log.info("No system speech command found on this platform")
            continue
        log.info("Using %s speaker", name)
        return speaker
    return NullSpeaker()
