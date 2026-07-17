from pathlib import Path

from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.db import Base


def client(tmp_path: Path, monkeypatch: object) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'studies.db'}")  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def headers(tenant: str = "tenant-a") -> dict[str, str]:
    return {"X-Tenant-ID": tenant, "X-Actor-ID": f"writer-{tenant}"}


def test_create_rejects_blank_names_and_unknown_fields(tmp_path: Path, monkeypatch: object) -> None:
    api = client(tmp_path, monkeypatch)

    assert api.post("/api/studies", json={"name": "   "}, headers=headers()).status_code == 422
    assert (
        api.post(
            "/api/studies",
            json={"name": "Synthetic Alpha", "unexpected": True},
            headers=headers(),
        ).status_code
        == 422
    )
    get_settings.cache_clear()


def test_tenant_cannot_load_another_tenants_study(tmp_path: Path, monkeypatch: object) -> None:
    api = client(tmp_path, monkeypatch)
    created = api.post("/api/studies", json={"name": "Synthetic Alpha"}, headers=headers())

    response = api.get(f"/api/studies/{created.json()['id']}", headers=headers("tenant-b"))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "STUDY_NOT_FOUND"
    get_settings.cache_clear()


def test_lifecycle_filtering_archive_conflict_and_restore(tmp_path: Path, monkeypatch: object) -> None:
    api = client(tmp_path, monkeypatch)
    first = api.post("/api/studies", json={"name": "Synthetic Alpha"}, headers=headers()).json()
    second = api.post("/api/studies", json={"name": "Synthetic Beta"}, headers=headers()).json()

    archived = api.post(
        f"/api/studies/{first['id']}/archive",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert (archived.status_code, archived.json()["lifecycle"], archived.json()["version"]) == (
        200,
        "archived",
        2,
    )
    active = api.get("/api/studies?lifecycle=active", headers=headers())
    archived_list = api.get("/api/studies?lifecycle=archived", headers=headers())
    assert [item["id"] for item in active.json()["items"]] == [second["id"]]
    assert [item["id"] for item in archived_list.json()["items"]] == [first["id"]]

    blocked = api.post(
        f"/api/studies/{first['id']}/archive",
        json={"expected_version": 2},
        headers=headers(),
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "STUDY_ARCHIVED"

    stale = api.post(
        f"/api/studies/{first['id']}/restore",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STUDY_VERSION_CONFLICT"

    restored = api.post(
        f"/api/studies/{first['id']}/restore",
        json={"expected_version": 2},
        headers=headers(),
    )
    assert (restored.status_code, restored.json()["lifecycle"], restored.json()["version"]) == (
        200,
        "active",
        3,
    )
    get_settings.cache_clear()
