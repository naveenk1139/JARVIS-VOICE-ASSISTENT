"""Service-layer tests: HTTP resilience, feed parsing, weather codes, dictionary."""

from __future__ import annotations

import httpx
import pytest

from jarvis.config import Config
from jarvis.context import AppContext
from jarvis.models import ServiceError
from jarvis.services.dictionary import DictionaryService, normalize_word
from jarvis.services.http import HttpClient
from jarvis.services.news import NewsService
from jarvis.services.weather import WMO_CODES, Place, Weather, WeatherService
from jarvis.services.wikipedia import clean_topic, shorten
from jarvis.services.youtube import extract_video_id, search_url

from .conftest import run
from .fixtures import FORECAST, GEOCODE, RSS


# --------------------------------------------------------------------------- #
# HttpClient
# --------------------------------------------------------------------------- #
def test_offline_client_refuses_requests(tmp_path) -> None:
    client = HttpClient(offline=True)
    with pytest.raises(ServiceError) as excinfo:
        run(client.get_json("https://example.test/anything"))
    assert "offline" in str(excinfo.value)
    run(client.aclose())


def test_client_retries_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(retries=1, transport=httpx.MockTransport(handler))
    assert run(client.get_json("https://example.test/x"))["ok"] is True
    assert attempts["count"] == 2
    run(client.aclose())


def test_client_reports_http_errors() -> None:
    client = HttpClient(
        retries=0, transport=httpx.MockTransport(lambda request: httpx.Response(404, json={}))
    )
    with pytest.raises(ServiceError) as excinfo:
        run(client.get_json("https://example.test/missing", service="demo"))
    assert excinfo.value.service == "demo"
    assert excinfo.value.status == 404
    run(client.aclose())


def test_client_reports_transport_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    client = HttpClient(retries=1, transport=httpx.MockTransport(handler))
    with pytest.raises(ServiceError):
        run(client.get_text("https://example.test/down"))
    run(client.aclose())


def test_client_posts_json_with_custom_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}]})

    client = HttpClient(retries=0, transport=httpx.MockTransport(handler))
    payload = run(
        client.post_json("https://example.test/v1/messages", json={"a": 1}, headers={"x-api-key": "k"})
    )
    assert payload["content"][0]["text"] == "hi"
    assert seen["x-api-key"] == "k"
    run(client.aclose())


# --------------------------------------------------------------------------- #
# News
# --------------------------------------------------------------------------- #
def test_rss_parsing() -> None:
    headlines = NewsService._parse_feed(RSS, "https://example.test/rss")
    assert [h.title for h in headlines][0].startswith("ISRO")
    assert headlines[1].url == "https://example.test/monsoon"
    assert headlines[0].source == "Example News"


def test_rss_parsing_survives_garbage() -> None:
    assert NewsService._parse_feed("<html>not a feed</html>", "https://x.test/rss") == []


def test_headlines_are_cached(config: Config, stub_http) -> None:
    http = stub_http({}, text_responses={"example.test/rss": RSS})
    service = NewsService(AppContext(config, http))
    first = run(service.headlines(2))
    second = run(service.headlines(2))
    assert first == second
    assert http.calls.count(("example.test/rss", "https://example.test/rss")) == 1


def test_news_failure_is_reported(config: Config, stub_http) -> None:
    class Broken:
        async def get_text(self, *args, **kwargs):  # noqa: ANN002
            raise ServiceError("feed down", service="news")

        async def get_json(self, *args, **kwargs):  # noqa: ANN002
            raise ServiceError("api down", service="news")

    service = NewsService(AppContext(config, Broken()))
    with pytest.raises(ServiceError):
        run(service.headlines(3))


def test_newsapi_backend_is_used_when_key_present(config: Config, stub_http) -> None:
    config.news_api_key = "test-key"
    payload = {
        "articles": [
            {"title": "Story one", "url": "https://a.test/1", "source": {"name": "NewsAPI"}},
            {"title": "Story two", "url": "https://a.test/2", "source": {"name": "NewsAPI"}},
        ]
    }
    http = stub_http({"newsapi.org": payload})
    service = NewsService(AppContext(config, http))
    headlines = run(service.headlines(2))
    assert [h.title for h in headlines] == ["Story one", "Story two"]


# --------------------------------------------------------------------------- #
# Weather
# --------------------------------------------------------------------------- #
def test_wmo_codes_cover_the_common_cases() -> None:
    assert WMO_CODES[0] == "clear sky"
    assert WMO_CODES[63] == "moderate rain"
    assert WMO_CODES[95] == "thunderstorm"


def test_weather_summary_wording() -> None:
    weather = Weather(
        place=Place("Bengaluru", "India", 12.97, 77.59),
        temperature=27.4,
        feels_like=29.1,
        humidity=62,
        wind_speed=11.5,
        description="partly cloudy",
    )
    assert "27" in weather.summary()
    assert "partly cloudy" in weather.summary()
    assert weather.to_dict()["unit_symbol"] == "\u00b0C"


def test_geocoding_and_forecast(config: Config, stub_http) -> None:
    http = stub_http({"geocoding-api.open-meteo.com": GEOCODE, "api.open-meteo.com": FORECAST})
    service = WeatherService(AppContext(config, http))
    weather = run(service.current("Mumbai"))
    assert weather.place.name == "Bengaluru"  # canned payload
    assert weather.temperature == pytest.approx(27.4)
    assert weather.description == "partly cloudy"


def test_unknown_place_raises(config: Config, stub_http) -> None:
    http = stub_http({"geocoding-api.open-meteo.com": {"results": []}})
    service = WeatherService(AppContext(config, http))
    with pytest.raises(ServiceError):
        run(service.current("Atlantis"))


def test_default_location_falls_back_to_config(tmp_path, stub_http) -> None:
    config = Config(location="", fallback_location="Bengaluru", data_dir=tmp_path)
    http = stub_http(
        {"ipapi.co": ServiceError("no ip lookup", service="weather"), "geocoding-api.open-meteo.com": GEOCODE}
    )
    service = WeatherService(AppContext(config, http))
    place = run(service.default_place())
    assert place.name == "Bengaluru"


# --------------------------------------------------------------------------- #
# Wikipedia / dictionary / youtube helpers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("tell me about the mars rover", "mars rover"),
        ("who is Ada Lovelace?", "Ada Lovelace"),
        ("what is quantum computing", "quantum computing"),
    ],
)
def test_topic_cleaning(query: str, expected: str) -> None:
    assert clean_topic(query) == expected


def test_shorten_keeps_sentences() -> None:
    text = "First sentence here. Second sentence follows. Third one is dropped."
    assert shorten(text, 2) == "First sentence here. Second sentence follows."


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("jarvis", "jarvis"), ("  WOMBAT!! ", "wombat"), ("multi word phrase", "multi word phrase")],
)
def test_dictionary_word_normalisation(raw: str, expected: str) -> None:
    assert normalize_word(raw) == expected


def test_local_dictionary_hit(tmp_path, config: Config, stub_http) -> None:
    corpus = tmp_path / "corpus.json"
    corpus.write_text('{"wombat": ["A short-legged Australian marsupial."]}', encoding="utf-8")
    config.dictionary_path = corpus
    service = DictionaryService(AppContext(config, stub_http({})))
    definition = run(service.define("wombat"))
    assert definition.source == "local"
    assert "marsupial" in definition.spoken()


def test_dictionary_missing_word_falls_back_to_web(tmp_path, config: Config, stub_http) -> None:
    payload = [
        {
            "word": "serendipity",
            "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "A happy accident."}]}],
        }
    ]
    corpus = tmp_path / "empty-corpus.json"
    corpus.write_text("{}", encoding="utf-8")
    config.dictionary_path = corpus
    http = stub_http({"dictionaryapi.dev": payload})
    service = DictionaryService(AppContext(config, http))
    definition = run(service.define("serendipity"))
    assert definition.source == "dictionaryapi.dev"
    assert definition.part_of_speech == "noun"


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://example.com/nope", None),
    ],
)
def test_video_id_extraction(url: str, video_id: str | None) -> None:
    assert extract_video_id(url) == video_id


def test_search_url_encodes_query() -> None:
    assert search_url("lo-fi beats") == "https://www.youtube.com/results?search_query=lo-fi+beats"
