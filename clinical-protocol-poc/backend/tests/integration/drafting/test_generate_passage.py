from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.db import Base
from protocol_poc.studies.models import Fact, FactVersion, Study


def _client(tmp_path, monkeypatch) -> tuple[TestClient, object]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'drafting.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    return TestClient(app), app


def _seed_approved_facts(app: object, *, lifecycle: str = "active") -> None:
    values = {
        "identity-a": ("study_identity", {"kind": "string", "value": "SYN-1"}),
        "population-a": ("population", {"kind": "string", "value": "Adults with synthetic condition"}),
        "objective-a": ("objective", {"kind": "string", "value": "Evaluate response"}),
        "endpoint-a": ("endpoint", {"kind": "string", "value": "Response"}),
        "timepoint-a": ("timepoint", {"kind": "string", "value": "Week 24"}),
        "arm-a": ("arm", {"kind": "string", "value": "Arm A"}),
        "intervention-a": ("intervention", {"kind": "string", "value": "Synthetic Intervention A"}),
        "dose-a": ("dose", {"kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"}),
        "duration-a": ("duration", {"kind": "string", "value": "24 weeks"}),
        "eligibility-a": ("eligibility", {"kind": "structured_criterion", "value": {"text": "Age 18 years or older"}}),
    }
    with app.state.session_factory() as session:  # type: ignore[attr-defined]
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study", lifecycle=lifecycle))
        for fact_id, (kind, value) in values.items():
            session.add(Fact(id=fact_id, tenant_id="tenant-a", study_id="study-a", kind=kind, status="approved"))
            session.flush()
            session.add(FactVersion(id=f"{fact_id}-v1", tenant_id="tenant-a", fact_id=fact_id, version=1, value_json=value, is_current=True))
        session.commit()


def test_passage_api_generates_and_lists_exact_deterministic_support(tmp_path, monkeypatch) -> None:
    client, app = _client(tmp_path, monkeypatch)
    _seed_approved_facts(app)
    headers = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}

    generated = client.post("/api/studies/study-a/passages", headers=headers, json={"section": "study_design"})
    listed = client.get("/api/studies/study-a/passages", headers=headers)

    assert generated.status_code == 200
    assert generated.json()["text"] == "Arm A receives Synthetic Intervention A, 10 mg once daily, for 24 weeks."
    assert listed.status_code == 200
    passage = listed.json()["passages"][0]
    assert passage["status"] == "ready_for_review"
    assert passage["claims"] == [{"text": generated.json()["text"], "fact_ids": ["arm-a", "intervention-a", "dose-a", "duration-a"]}]
    assert passage["fact_support_ids"] == ["arm-a", "intervention-a", "dose-a", "duration-a"]
    get_settings.cache_clear()


def test_passage_api_hides_other_tenants_and_denies_archived_mutations(tmp_path, monkeypatch) -> None:
    client, app = _client(tmp_path, monkeypatch)
    _seed_approved_facts(app, lifecycle="archived")
    owner = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}
    other = {"X-Tenant-ID": "tenant-b", "X-Actor-ID": "writer-b"}

    assert client.get("/api/studies/study-a/passages", headers=owner).status_code == 200
    assert client.get("/api/studies/study-a/passages", headers=other).status_code == 404
    response = client.post("/api/studies/study-a/passages", headers=owner, json={"section": "study_design"})
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "STUDY_ARCHIVED"}}
    get_settings.cache_clear()


def test_archived_passages_remain_viewable_but_deny_every_review_mutation(tmp_path, monkeypatch) -> None:
    client, app = _client(tmp_path, monkeypatch)
    _seed_approved_facts(app)
    headers = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}
    generated = client.post("/api/studies/study-a/passages", headers=headers, json={"section": "study_design"})
    passage_id = generated.json()["passage_id"]
    with app.state.session_factory.begin() as session:  # type: ignore[attr-defined]
        study = session.get(Study, "study-a")
        assert study is not None
        study.lifecycle = "archived"

    listed = client.get("/api/studies/study-a/passages", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["read_only"] is True
    assert listed.json()["passages"][0]["text"] == generated.json()["text"]

    for body in (
        {"action": "accept", "expected_version": 1},
        {"action": "edit", "expected_version": 1, "text": "Edited.", "support_ids": ["dose-a"]},
        {"action": "reject", "expected_version": 1, "rationale": "Synthetic rejection"},
        {"action": "regenerate", "expected_version": 1},
    ):
        response = client.post(f"/api/passages/{passage_id}/review", headers=headers, json=body)
        assert response.status_code == 409
        assert response.json() == {"detail": {"code": "STUDY_ARCHIVED"}}
    get_settings.cache_clear()


def test_all_scoped_sections_are_allowlisted() -> None:
    from protocol_poc.drafting.service import DraftingService

    assert DraftingService.SCOPED_SECTIONS == {
        "synopsis", "objectives_endpoints", "study_design", "eligibility"
    }
