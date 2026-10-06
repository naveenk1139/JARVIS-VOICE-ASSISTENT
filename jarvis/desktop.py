"""Desktop front door: microphone in, spoken replies out, same engine as the web UI."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from .config import Config
from .engine import Engine
from .models import Response
from .security.face_unlock import UnlockResult, unlock_if_enabled
from .voice.listener import Listener, build_listener
from .voice.speaker import Speaker, build_speaker

log = logging.getLogger(__name__)


class DesktopAssistant:
    """Runs the assistant loop on the local machine."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        engine: Engine | None = None,
        speaker: Speaker | None = None,
        listener: Listener | None = None,
        input_mode: str = "auto",
    ) -> None:
        self.config = config or Config.from_env()
        self.engine = engine or Engine(self.config)
        self.speaker = speaker or build_speaker(self.config)
        self.listener = listener or build_listener(self.config, prefer=input_mode)

    # ------------------------------------------------------------------ lifecycle
    async def run(self) -> None:
        unlock = unlock_if_enabled(self.config)
        self._report_unlock(unlock)
        if self.config.require_face_unlock and not unlock.unlocked:
            self._say(unlock.message)
            if unlock.status.value not in {"disabled"}:
                log.warning("Continuing without face unlock (status: %s)", unlock.status.value)

        await self.greet()
        try:
            while True:
                if not await self._turn():
                    break
        except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover - interactive
            self._say("Goodbye.")
        finally:
            await self.aclose()

    async def _turn(self) -> bool:
        utterance: str = await asyncio.to_thread(self.listener.listen)
        if not utterance:
            return True  # silence or unrecognised speech: keep listening
        lowered = utterance.strip().lower()
        if lowered in {"exit", "quit", "stop", "goodbye", "bye"}:
            self._say(f"Goodbye, {self.config.display_name()}.")
            return False

        response = await self.engine.handle(utterance, session_id="desktop")
        self._present(response)
        return response.kind != "exit"

    async def greet(self) -> None:
        hour = dt.datetime.now().hour
        part = "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")
        self._say(f"Good {part}, {self.config.display_name()}. {self.config.assistant_name} online.")

        response = await self.engine.handle("what is the weather", session_id="desktop")
        self._present(response, speak=False)
        self._say(response.text)

    # -------------------------------------------------------------------- output
    def _present(self, response: Response, *, speak: bool = True) -> None:
        prefix = {"error": "!", "link": "->"}.get(response.kind, " ")
        print(f"{prefix} {response.text}")
        if response.url:
            print(f"   {response.url}")
        if speak and response.speak and response.kind != "error":
            self._say(response.text)

    def _say(self, text: str) -> None:
        try:
            self.speaker.speak(text)
        except Exception:  # pragma: no cover - audio devices are flaky
            log.exception("Text-to-speech failed")
            print(f"JARVIS: {text}")

    def _report_unlock(self, result: UnlockResult) -> None:
        if result.status.value == "disabled":
            return
        self._say(result.message)
        log.info("Face unlock status=%s confidence=%s", result.status.value, result.confidence)
        if result.status.value in {"model_missing", "dependency_missing"}:
            print(f"hint: {result.message}")

    # ---------------------------------------------------------------------- close
    async def aclose(self) -> None:
        self.listener.close()
        self.speaker.close()
        await self.engine.aclose()


async def run_desktop(config: Config | None = None, *, input_mode: str = "auto") -> None:
    assistant = DesktopAssistant(config, input_mode=input_mode)
    await assistant.run()
