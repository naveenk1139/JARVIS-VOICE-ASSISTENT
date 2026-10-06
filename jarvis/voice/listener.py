"""Microphone and text input for the desktop app."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)


class Listener(Protocol):
    name: str

    def listen(self) -> str: ...
    def close(self) -> None: ...


class TextListener:
    """Reads commands from stdin - always available, ideal for testing."""

    name = "text"

    def __init__(self, prompt: str = "you> ") -> None:
        self.prompt = prompt

    def listen(self) -> str:
        try:
            return input(self.prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return "exit"

    def close(self) -> None:  # pragma: no cover
        return None


class MicrophoneListener:
    """Speech-to-text through ``SpeechRecognition`` + ``PyAudio``."""

    name = "microphone"

    def __init__(
        self,
        *,
        language: str = "en-in",
        energy_threshold: int = 300,
        pause_threshold: float = 0.9,
        ambient_calibration: float = 1.0,
        timeout: float | None = 8.0,
        phrase_time_limit: float | None = 12.0,
    ) -> None:
        import speech_recognition as sr  # lazy import

        self._sr = sr
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = energy_threshold
        self._recognizer.pause_threshold = pause_threshold
        self._microphone = sr.Microphone()
        self.language = language
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        self._calibrated = False
        self._ambient_calibration = ambient_calibration

    def _calibrate(self) -> None:
        with self._microphone as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=self._ambient_calibration)
        self._calibrated = True

    def listen(self) -> str:
        if not self._calibrated:
            self._calibrate()
        try:
            with self._microphone as source:
                audio = self._recognizer.listen(
                    source, timeout=self.timeout, phrase_time_limit=self.phrase_time_limit
                )
        except self._sr.WaitTimeoutError:
            return ""
        except OSError as exc:  # no microphone / permission problem
            log.error("Microphone unavailable: %s", exc)
            return ""

        try:
            text = self._recognizer.recognize_google(audio, language=self.language)
            log.debug("Heard: %s", text)
            return text.strip()
        except self._sr.UnknownValueError:
            return ""
        except self._sr.RequestError as exc:
            log.warning("Speech service unreachable: %s", exc)
            return ""

    def close(self) -> None:  # pragma: no cover
        self._microphone = None  # type: ignore[assignment]


class WakeWordListener:
    """Wraps a listener and discards utterances until the wake word appears.

    This replaces the legacy behaviour of running a whole second recognition
    pass just to detect the assistant's name.
    """

    def __init__(self, inner: Listener, words: list[str]) -> None:
        self.inner = inner
        self.words = [word.lower() for word in words if word]
        self.name = f"{inner.name}+wake"

    def listen(self) -> str:
        while True:
            utterance = self.inner.listen()
            if not utterance:
                return ""
            lowered = utterance.lower()
            for word in self.words:
                if word in lowered:
                    # strip the wake word so skills see a clean command
                    index = lowered.index(word) + len(word)
                    remainder = utterance[index:].strip(" ,.!?")
                    return remainder or utterance
            log.debug("Ignoring utterance without wake word: %s", utterance)

    def close(self) -> None:
        self.inner.close()


def build_listener(config, *, prefer: str = "auto") -> Listener:
    """Microphone when possible, stdin otherwise."""
    if prefer == "text":
        return TextListener()
    if prefer in ("auto", "microphone"):
        try:
            listener = MicrophoneListener()
        except Exception as exc:  # ImportError or no audio device
            if prefer == "microphone":
                raise
            log.warning("Microphone listener unavailable (%s); falling back to typed input", exc)
        else:
            if config.wake_word:
                return WakeWordListener(listener, [w.strip() for w in config.wake_word.split(",")])
            return listener
    return TextListener()
