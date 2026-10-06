"""Weather and geocoding via Open-Meteo (free, no API key required)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models import ServiceError

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..context import AppContext

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
IP_LOOKUP_URL = "https://ipapi.co/json/"

# WMO weather interpretation codes -> human readable description
WMO_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snowfall",
    73: "moderate snowfall",
    75: "heavy snowfall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


@dataclass(slots=True)
class Place:
    name: str
    country: str
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        return f"{self.name}, {self.country}" if self.country else self.name


@dataclass(slots=True)
class Weather:
    place: Place
    temperature: float
    feels_like: float
    humidity: int
    wind_speed: float
    description: str
    units: str = "metric"

    @property
    def unit_symbol(self) -> str:
        return "\u00b0C" if self.units == "metric" else "\u00b0F"

    @property
    def wind_unit(self) -> str:
        return "km/h" if self.units == "metric" else "mph"

    def summary(self) -> str:
        return (
            f"It is {round(self.temperature)}{self.unit_symbol} and {self.description} "
            f"in {self.place.label}, with {self.humidity}% humidity and "
            f"{round(self.wind_speed)} {self.wind_unit} winds."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "place": self.place.label,
            "latitude": self.place.latitude,
            "longitude": self.place.longitude,
            "temperature": round(self.temperature, 1),
            "feels_like": round(self.feels_like, 1),
            "humidity": self.humidity,
            "wind_speed": round(self.wind_speed, 1),
            "description": self.description,
            "units": self.units,
            "unit_symbol": self.unit_symbol,
        }


class WeatherService:
    """Geocode a place name and fetch its current conditions."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._place_cache: dict[str, Place] = {}
        self._default_place: Place | None = None

    # ------------------------------------------------------------- geocoding
    async def resolve_place(self, query: str | None = None) -> Place:
        """Resolve ``query`` to a :class:`Place`, falling back to the user's location."""
        query = (query or "").strip()
        if query:
            key = query.lower()
            if key in self._place_cache:
                return self._place_cache[key]
            place = await self._geocode(query)
            if place is None:
                raise ServiceError(f"I could not find a place called {query}", service="weather")
            self._place_cache[key] = place
            return place
        return await self.default_place()

    async def default_place(self) -> Place:
        if self._default_place is not None:
            return self._default_place

        configured = self.ctx.config.location.strip()
        if configured:
            self._default_place = await self._geocode(configured) or Place(
                name=configured, country="", latitude=0.0, longitude=0.0
            )
            return self._default_place

        detected = await self._detect_place()
        if detected is not None:
            self._default_place = detected
            return detected

        fallback = self.ctx.config.fallback_location or "Bengaluru"
        log.info("Falling back to configured default location %s", fallback)
        self._default_place = await self._geocode(fallback) or Place(
            name=fallback, country="", latitude=12.97, longitude=77.59
        )
        return self._default_place

    async def _geocode(self, name: str) -> Place | None:
        payload = await self.ctx.http.get_json(
            GEOCODE_URL, params={"name": name, "count": 1, "language": "en"}, service="weather"
        )
        results = (payload or {}).get("results") or []
        if not results:
            return None
        top = results[0]
        return Place(
            name=top.get("name", name),
            country=top.get("country", ""),
            latitude=float(top["latitude"]),
            longitude=float(top["longitude"]),
        )

    async def _detect_place(self) -> Place | None:
        try:
            payload = await self.ctx.http.get_json(IP_LOOKUP_URL, service="weather")
        except ServiceError as exc:
            log.info("IP geolocation unavailable: %s", exc)
            return None
        city = (payload or {}).get("city") or ""
        if not city:
            return None
        return Place(
            name=city,
            country=(payload or {}).get("country_name", ""),
            latitude=float(payload.get("latitude", 0.0)),
            longitude=float(payload.get("longitude", 0.0)),
        )

    # -------------------------------------------------------------- forecast
    async def current(self, query: str | None = None) -> Weather:
        place = await self.resolve_place(query)
        units = self.ctx.config.units if self.ctx.config.units in {"metric", "imperial"} else "metric"
        payload = await self.ctx.http.get_json(
            FORECAST_URL,
            params={
                "latitude": place.latitude,
                "longitude": place.longitude,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "temperature_unit": "celsius" if units == "metric" else "fahrenheit",
                "wind_speed_unit": "kmh" if units == "metric" else "mph",
                "timezone": "auto",
            },
            service="weather",
        )
        current = (payload or {}).get("current") or {}
        if not current:
            raise ServiceError("the weather service returned no current conditions", service="weather")

        code = int(current.get("weather_code", 0) or 0)
        return Weather(
            place=place,
            temperature=float(current.get("temperature_2m", 0.0)),
            feels_like=float(current.get("apparent_temperature", current.get("temperature_2m", 0.0))),
            humidity=int(current.get("relative_humidity_2m", 0) or 0),
            wind_speed=float(current.get("wind_speed_10m", 0.0) or 0.0),
            description=WMO_CODES.get(code, "unsettled weather"),
            units=units,
        )
