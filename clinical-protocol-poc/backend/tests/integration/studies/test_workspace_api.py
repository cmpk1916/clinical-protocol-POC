from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.db import Base
from protocol_poc.ingest.service import DOCX_CONTENT_TYPE
from protocol_poc.reliability.fixtures import MISSING_DOSE_INITIAL, SECTIONS, build_synopsis
from protocol_poc.rendering.template_map import build_template
from protocol_poc.studies.models import Fact, FactVersion, Study


def _client(tmp_path, monkeypatch) -> tuple[TestClient, object]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'workspace.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    return TestClient(app), app


def test_workspace_api_returns_derived_missing_input_summary(tmp_path, monkeypatch) -> None:
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.commit()

    response = client.get(
        "/api/studies/study-a/workspace",
        headers={"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["step"] == "inputs"
    assert payload["next_action"]["kind"] == "upload_synopsis"
    assert payload["inputs"] == {"synopsis": None, "template": None}
    assert payload["blockers"][0]["code"] == "SYNOPSIS_INPUT_MISSING"
    get_settings.cache_clear()


def test_workspace_api_explains_source_correction_without_offering_retry(
    tmp_path, monkeypatch
) -> None:
    client, _app = _client(tmp_path, monkeypatch)
    headers = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}
    created = client.post(
        "/api/studies",
        headers=headers,
        json={"name": "Synthetic missing dose"},
    )
    study_id = created.json()["id"]
    synopsis = client.post(
        f"/api/studies/{study_id}/inputs",
        headers=headers,
        data={"role": "synopsis"},
        files={
            "file": (
                "synopsis.docx",
                build_synopsis(MISSING_DOSE_INITIAL),
                DOCX_CONTENT_TYPE,
            )
        },
    )
    template = client.post(
        f"/api/studies/{study_id}/inputs",
        headers=headers,
        data={"role": "template"},
        files={"file": ("template.docx", build_template(SECTIONS), DOCX_CONTENT_TYPE)},
    )

    assert (synopsis.status_code, template.status_code) == (201, 201)
    processed = client.post(
        f"/api/studies/{study_id}/inputs/{synopsis.json()['version_id']}/process",
        headers=headers,
    )
    workspace = client.get(f"/api/studies/{study_id}/workspace", headers=headers)

    assert processed.status_code == 200
    assert processed.json()["status"] == "failed"
    assert workspace.status_code == 200
    payload = workspace.json()
    assert payload["next_action"] == {
        "kind": "upload_synopsis",
        "label": "Upload corrected synopsis",
        "target_id": None,
        "href": None,
    }
    assert payload["blockers"] == [
        {
            "code": "SYNOPSIS_DOSE_MISSING",
            "message": (
                "Intervention values must include an N mg dose and once daily frequency."
            ),
            "affected_area": "arms_interventions",
            "blocking_reason": (
                "Synopsis processing cannot succeed until the source content is corrected."
            ),
        }
    ]
    get_settings.cache_clear()


def test_archived_review_is_viewable_but_every_fact_mutation_is_rejected(
    tmp_path, monkeypatch
) -> None:
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(
            Study(
                id="study-a",
                tenant_id="tenant-a",
                name="Archived study",
                lifecycle="archived",
            )
        )
        fact = Fact(
            id="fact-a",
            tenant_id="tenant-a",
            study_id="study-a",
            kind="dose",
            status="candidate",
        )
        session.add(fact)
        session.flush()
        session.add(
            FactVersion(
                tenant_id="tenant-a",
                fact_id=fact.id,
                version=1,
                value_json={"kind": "dose", "value": "10", "unit": "mg"},
                is_current=True,
            )
        )
        session.commit()
    headers = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}

    assert client.get("/api/studies/study-a/workspace", headers=headers).status_code == 200
    assert client.get("/api/studies/study-a/fact-review", headers=headers).status_code == 200

    for action in ("approve", "correct_and_approve", "reject", "defer", "resolve_conflict"):
        response = client.post(
            "/api/facts/fact-a/review",
            headers=headers,
            json={
                "action": action,
                "expected_version": 1,
                "explicitly_confirmed": True,
                "value": {"kind": "dose", "value": "11", "unit": "mg"},
                "rationale": "Synthetic review",
            },
        )
        assert response.status_code == 409
        assert response.json() == {"detail": {"code": "STUDY_ARCHIVED"}}

    for payload in (
        {"action": "correct_and_approve", "expected_version": 999},
        {"action": "resolve_conflict", "expected_version": 999, "rationale": "   "},
    ):
        response = client.post(
            "/api/facts/fact-a/review", headers=headers, json=payload
        )
        assert response.status_code == 409
        assert response.json() == {"detail": {"code": "STUDY_ARCHIVED"}}
    get_settings.cache_clear()


def test_workspace_and_review_hide_cross_tenant_studies(tmp_path, monkeypatch) -> None:
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.commit()
    headers = {"X-Tenant-ID": "tenant-b", "X-Actor-ID": "writer-b"}

    workspace = client.get("/api/studies/study-a/workspace", headers=headers)
    review = client.get("/api/studies/study-a/fact-review", headers=headers)

    assert workspace.status_code == 404
    assert workspace.json() == {"detail": {"code": "STUDY_NOT_FOUND"}}
    assert review.status_code == 404
    assert review.json() == {"detail": {"code": "STUDY_NOT_FOUND"}}
    get_settings.cache_clear()
