"""HTTP API tests - the browser front door, exercised in-process.

Uses Starlette's synchronous ``TestClient`` (backed by httpx), so there is no
server to start, no port to bind and no network access.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis.config import Config
from jarvis.engine import Engine
from jarvis.server.app import create_app

from .conftest import run


def make_client(tmp_path: Path, **overrides) -> TestClient:
    config = Config(offline=True, data_dir=tmp_path, **overrides)
    return TestClient(create_app(config))


@pytest.fixture()
def client(tmp_path: Path):  # noqa: ANN201
    with TestClient(create_app(Config(offline=True, data_dir=tmp_path))) as test_client:
        yield test_client


def test_index_serves_the_ui(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "J.A.R.V.I.S" in response.text
    assert "/static/app.js" in response.text


def test_static_assets_are_served(client: TestClient) -> None:
    for path, needle in (("/static/app.js", "speechSynthesis"), ("/static/styles.css", ".reactor")):
        response = client.get(path)
        assert response.status_code == 200
        assert needle in response.text


def test_health_reports_engine_state(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["assistant"]["name"] == "JARVIS"
    assert payload["assistant"]["skills"] >= 10


def test_skills_endpoint_lists_examples(client: TestClient) -> None:
    payload = client.get("/api/skills").json()
    assert payload["count"] >= 10
    assert payload["suggestions"]
    assert all(entry["examples"] for entry in payload["skills"])


def test_command_endpoint_handles_a_request(client: TestClient) -> None:
    response = client.post("/api/command", json={"text": "calculate 6 times 7", "session_id": "s1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["skill"] == "calculator"
    assert "42" in payload["text"]


def test_command_validates_input(client: TestClient) -> None:
    assert client.post("/api/command", json={"text": ""}).status_code == 422
    assert client.post("/api/command", json={}).status_code == 422


def test_notes_and_memory_endpoints(tmp_path: Path) -> None:
    with TestClient(create_app(Config(offline=True, data_dir=tmp_path))) as http_client:
        http_client.post("/api/command", json={"text": "add call the plumber to my list"})
        http_client.post("/api/command", json={"text": "remember that the spare key is under the mat"})
        payload = http_client.get("/api/notes").json()
        assert payload["open"][0]["text"] == "call the plumber"
        assert any("spare key" in value for value in payload["memories"].values())


def test_session_endpoint_returns_history(client: TestClient) -> None:
    client.post("/api/command", json={"text": "what time is it", "session_id": "abc"})
    payload = client.get("/api/session", params={"session_id": "abc"}).json()
    assert [turn["role"] for turn in payload["history"]] == ["user", "jarvis"]


def test_reset_clears_the_transcript(client: TestClient) -> None:
    client.post("/api/command", json={"text": "what time is it", "session_id": "abc"})
    assert client.post("/api/reset", json={"session_id": "abc"}).json()["status"] == "reset"
    payload = client.get("/api/session", params={"session_id": "abc"}).json()
    assert payload["history"] == []


def test_weather_endpoint_reports_upstream_failure(client: TestClient) -> None:
    response = client.get("/api/weather")
    assert response.status_code == 502  # offline mode -> the browser HUD shows a graceful message
    assert "error" in response.json()


def test_reminders_endpoint(client: TestClient) -> None:
    client.post("/api/command", json={"text": "remind me in 10 minutes to call mum"})
    payload = client.get("/api/reminders/due", params={"within_hours": 1}).json()
    assert payload["count"] == 1
    assert "call mum" in payload["due"][0]["text"]


def test_api_token_guard_is_optional_but_enforced_when_set(tmp_path: Path) -> None:
    with TestClient(create_app(Config(offline=True, data_dir=tmp_path, api_token="s3cret"))) as http_client:
        assert http_client.get("/api/health").status_code == 401
        ok = http_client.get("/api/health", headers={"X-JARVIS-Token": "s3cret"})
        assert ok.status_code == 200


def test_openapi_schema_is_available(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/command" in schema["paths"]


def test_app_can_be_built_from_an_existing_engine(tmp_path: Path) -> None:
    engine = Engine(Config(offline=True, data_dir=tmp_path))
    with TestClient(create_app(engine.config, engine=engine)) as http_client:
        assert http_client.get("/api/health").status_code == 200
    run(engine.aclose())


def test_unknown_route_is_404(client: TestClient) -> None:
    assert client.get("/api/nope").status_code == 404
