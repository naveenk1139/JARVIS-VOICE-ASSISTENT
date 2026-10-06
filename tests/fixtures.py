"""Canned API payloads used by the test suite (kept tiny and readable)."""

from __future__ import annotations

from typing import Any

GEOCODE = {
    "results": [
        {
            "name": "Bengaluru",
            "country": "India",
            "latitude": 12.9762,
            "longitude": 77.6033,
        }
    ]
}

FORECAST = {
    "current": {
        "temperature_2m": 27.4,
        "relative_humidity_2m": 62,
        "apparent_temperature": 29.1,
        "weather_code": 2,
        "wind_speed_10m": 11.5,
    }
}

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example News</title>
    <item>
      <title>ISRO tests reusable launch vehicle</title>
      <link>https://example.test/isro</link>
      <source>Example News</source>
    </item>
    <item>
      <title>Monsoon arrives early in Kerala</title>
      <link>https://example.test/monsoon</link>
      <source>Example News</source>
    </item>
    <item>
      <title>Chess: young grandmaster wins again</title>
      <link>https://example.test/chess</link>
      <source>Example News</source>
    </item>
  </channel>
</rss>
"""

WIKI_SEARCH = {"query": {"search": [{"title": "Ada Lovelace"}]}}
WIKI_SUMMARY = {
    "title": "Ada Lovelace",
    "extract": "Augusta Ada King, Countess of Lovelace, was an English mathematician and writer. "
    "She is chiefly known for her work on Charles Babbage's Analytical Engine.",
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
}

JOKE_API = {"joke": "Why do programmers prefer dark mode? Because light attracts bugs."}

OEMBED = {"title": "Lo-Fi Beats to Relax", "author_name": "Chill Channel"}

RESPONSES: dict[str, Any] = {
    "geocoding-api.open-meteo.com": GEOCODE,
    "api.open-meteo.com": FORECAST,
    "ipapi.co": {"city": "Bengaluru", "country_name": "India", "latitude": 12.97, "longitude": 77.59},
    "en.wikipedia.org/w/api.php": WIKI_SEARCH,
    "en.wikipedia.org/api/rest_v1/page/summary": WIKI_SUMMARY,
    "jokeapi.dev": JOKE_API,
    "youtube.com/oembed": OEMBED,
}

TEXT_RESPONSES: dict[str, str] = {
    "example.test/rss": RSS,
}
