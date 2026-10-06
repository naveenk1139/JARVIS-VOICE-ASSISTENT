"""Thin, resilient HTTP layer shared by every network-backed service."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ..models import ServiceError

log = logging.getLogger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpClient:
    """Async HTTP client with timeouts, small retry policy and offline mode.

    A single instance is created per :class:`~jarvis.engine.Engine` and shared by
    all skills so connection pooling works and tests can inject a transport.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        retries: int = 2,
        user_agent: str = "JARVIS-Voice-Assistant/2.0",
        offline: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self.offline = offline
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept-Language": "en-IN,en;q=0.8"},
            transport=transport,
        )

    # ------------------------------------------------------------------ verbs
    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        service: str = "http",
    ) -> Any:
        response = await self._request("GET", url, params=params, service=service)
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise ServiceError(f"{service} returned a malformed response", service=service) from exc

    async def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        service: str = "http",
    ) -> str:
        response = await self._request("GET", url, params=params, service=service)
        return response.text

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        service: str = "http",
    ) -> Any:
        response = await self._request("POST", url, json=json, data=data, headers=headers, service=service)
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise ServiceError(f"{service} returned a malformed response", service=service) from exc

    # -------------------------------------------------------------- internals
    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        service: str = "http",
    ) -> httpx.Response:
        if self.offline:
            raise ServiceError(
                f"{service} is unavailable while JARVIS runs in offline mode",
                service=service,
            )

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = await self._client.request(
                    method, url, params=params, json=json, data=data, headers=headers
                )
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("%s request to %s failed (%s), attempt %s", service, url, exc, attempt + 1)
            else:
                if response.status_code in _RETRY_STATUS:
                    last_error = ServiceError(
                        f"{service} is busy (HTTP {response.status_code})",
                        service=service,
                        status=response.status_code,
                    )
                elif response.status_code >= 400:
                    raise ServiceError(
                        f"{service} rejected the request (HTTP {response.status_code})",
                        service=service,
                        status=response.status_code,
                    )
                else:
                    return response

            if attempt < self.retries:
                await asyncio.sleep(0.4 * (attempt + 1))

        raise ServiceError(f"could not reach {service}", service=service) from last_error

    # ---------------------------------------------------------------- lifecycle
    async def aclose(self) -> None:
        await self._client.aclose()
