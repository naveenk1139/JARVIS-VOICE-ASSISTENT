"""Weather and location skill."""

from __future__ import annotations

from ..models import Match, Response, ServiceError
from .base import Skill


class WeatherSkill(Skill):
    name = "weather"
    description = "Current conditions and coordinates for any city, via Open-Meteo."
    requires_network = True
    priority = 20
    examples = ("What is the weather?", "Weather in Bengaluru", "Where am I?")
    patterns = (
        r"^(?:what(?:'s| is) )?(?:the )?weather(?: like)?(?: today| right now)?(?: in| at| for)?\s*(?P<location>[a-z][a-z .,'-]*)?(?P<weather>)$",
        r"^(?:how(?:'s| is) )?the weather(?: in| at| for)?\s*(?P<location>[a-z][a-z .,'-]*)?(?P<weather>)$",
        r"^(?:is it|will it be) (?P<condition>raining|sunny|cloudy|hot|cold)(?: in| at| for)?\s*(?P<location>[a-z][a-z .,'-]*)?(?P<weather>)$",
        r"^(?:what(?:'s| is) )?the temperature(?: in| at| for)?\s*(?P<location>[a-z][a-z .,'-]*)?(?P<weather>)$",
        r"^(?:where am i|what(?:'s| is) my location|my coordinates)(?P<location_check>)$",
        r"^(?:what(?:'s| is) )?the (?:latitude|longitude)(?P<location_check>)$",
    )

    async def handle(self, match: Match, text: str) -> Response:
        location = match.group("location").strip(" ,.")
        try:
            weather = await self.ctx.weather.current(location or None)
        except ServiceError as exc:
            return Response.error(str(exc), data={"service": "weather"})

        payload = weather.to_dict()
        if "location_check" in match.groups:
            return Response.ok(
                f"You are in {weather.place.label}, which sits at latitude "
                f"{round(weather.place.latitude, 2)} and longitude {round(weather.place.longitude, 2)}.",
                data=payload,
            )
        return Response.ok(weather.summary(), data=payload)
