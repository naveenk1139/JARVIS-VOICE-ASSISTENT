"""Optional LLM fallback for open-ended questions.

Two wire formats are supported so the assistant is not tied to one vendor:

* ``openai``    - ``/chat/completions`` (OpenAI, Groq, Together, OpenRouter, Ollama...)
* ``anthropic`` - ``/v1/messages``    (Claude)

No SDKs are required; everything goes through the shared HTTP client.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from ..config import Config
from ..models import Response, ServiceError
from ..services.http import HttpClient
from .base import Brain

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are {name}, a concise, courteous voice assistant. Answer in at most three sentences, "
    "never use markdown, bullet points or emojis, and prefer spoken-friendly phrasing. "
    "If you are unsure, say so briefly."
)


class LLMBrain(Brain):
    name = "llm"

    def __init__(self, config: Config, http: HttpClient) -> None:
        self.config = config
        self.http = http

    @property
    def available(self) -> bool:
        return bool(self.config.llm_api_key) and not self.config.offline

    def _system_prompt(self) -> str:
        return self.config.llm_system_prompt or SYSTEM_PROMPT.format(name=self.config.assistant_name)

    def _history_messages(self, history: Sequence[Any]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for turn in list(history)[-6:]:
            role = getattr(turn, "role", None)
            text = getattr(turn, "text", None)
            if role in {"user", "jarvis"} and text:
                messages.append({"role": "user" if role == "user" else "assistant", "content": str(text)})
        return messages

    async def answer(self, question: str, history: Sequence[Any] = ()) -> Response:
        if not self.available:
            raise ServiceError("no language model is configured", service="llm")

        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(self._history_messages(history))
        messages.append({"role": "user", "content": question})

        if self.config.llm_provider == "anthropic":
            text = await self._ask_anthropic(messages)
        else:
            text = await self._ask_openai(messages)

        return Response.ok(
            text.strip(),
            kind="text",
            data={"brain": self.config.llm_provider, "model": self.config.llm_model},
            skill="llm",
        )

    # ---------------------------------------------------------------- providers
    async def _ask_openai(self, messages: list[dict[str, str]]) -> str:
        base = (self.config.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        payload = await self.http.post_json(
            f"{base}/chat/completions",
            json={
                "model": self.config.llm_model,
                "messages": messages,
                "max_tokens": self.config.llm_max_tokens,
                "temperature": self.config.llm_temperature,
            },
            data=None,
            service="llm",
        )
        choices = (payload or {}).get("choices") or []
        if not choices:
            raise ServiceError("the language model returned no answer", service="llm")
        message = choices[0].get("message") or {}
        return str(message.get("content") or "").strip()

    async def _ask_anthropic(self, messages: list[dict[str, str]]) -> str:
        base = (self.config.llm_base_url or "https://api.anthropic.com").rstrip("/")
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]
        payload = await self.http.post_json(
            f"{base}/v1/messages",
            headers={
                "x-api-key": self.config.llm_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.config.llm_model,
                "system": system,
                "messages": convo,
                "max_tokens": self.config.llm_max_tokens,
                "temperature": self.config.llm_temperature,
            },
            service="llm",
        )
        blocks = (payload or {}).get("content") or []
        text = " ".join(str(b.get("text", "")) for b in blocks if b.get("type") == "text")
        return text.strip()


def build_brain(config: Config, http: HttpClient) -> Brain | None:
    """Return an LLM brain when a key is present, else ``None``."""
    if not config.llm_api_key:
        return None
    return LLMBrain(config, http)
