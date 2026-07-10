from __future__ import annotations

from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings


def test_seed_routes_are_hidden_outside_test_environment(monkeypatch: object) -> None:
    monkeypatch.setenv("APP_ENV", "production")  # type: ignore[attr-defined]
    get_settings.cache_clear()

    response = TestClient(create_app()).post("/test/reset")

    assert response.status_code == 404


def test_seed_routes_reset_and_select_a_scenario_in_test_environment(
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    client = TestClient(create_app())

    assert client.post("/test/reset").status_code == 200
    assert client.post(
        "/test/studies/synthetic-phase-2/seed",
        json={"scenario": "fact_change_invalidation"},
    ).status_code == 200
    response = client.get("/test/studies/synthetic-phase-2/state")

    assert response.status_code == 200
    assert response.json()["passage"]["stale"] is True
    assert response.json()["export"]["blockers"]
