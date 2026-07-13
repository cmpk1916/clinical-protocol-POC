from __future__ import annotations

from fastapi.testclient import TestClient
from pathlib import Path
from sqlalchemy import select

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.studies.models import Study


def test_seed_routes_are_hidden_outside_test_environment(monkeypatch: object) -> None:
    monkeypatch.setenv("APP_ENV", "production")  # type: ignore[attr-defined]
    get_settings.cache_clear()

    response = TestClient(create_app()).post("/test/reset")

    assert response.status_code == 404


def test_seed_routes_reset_and_select_a_scenario_in_test_environment(
    monkeypatch: object, tmp_path: Path,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'test.db'}")  # type: ignore[attr-defined]
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "objects"))  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    assert client.post("/test/reset").status_code == 200
    assert client.post(
        "/test/studies/synthetic-phase-2/seed",
        json={"scenario": "fact_change_invalidation"},
    ).status_code == 200
    response = client.get("/test/studies/synthetic-phase-2/state")

    assert response.status_code == 200
    assert response.json()["passage"]["stale"] is True
    assert response.json()["export"]["blockers"]
    assert response.json()["exportCommand"]["templateVersionId"] == "template-v1"
    with app.state.session_factory() as session:
        assert session.scalar(select(Study).where(Study.id == "synthetic-phase-2")) is not None
    assert list((tmp_path / "objects").rglob("*.docx"))
