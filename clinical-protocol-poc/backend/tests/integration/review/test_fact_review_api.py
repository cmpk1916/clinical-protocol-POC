from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.db import Base
from protocol_poc.files.models import FileRecord, FileVersion, SourceEvidence
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, Study


def test_review_queue_orders_blockers_before_critical_and_low_confidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'review.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        facts = [
            Fact(id="low", tenant_id="tenant-a", study_id="study-a", kind="population", status="candidate"),
            Fact(id="critical", tenant_id="tenant-a", study_id="study-a", kind="dose", status="candidate", critical=True),
            Fact(id="conflict", tenant_id="tenant-a", study_id="study-a", kind="dose", status="conflicted", critical=True),
        ]
        session.add_all(facts)
        session.flush()
        session.add_all([
            FactVersion(tenant_id="tenant-a", fact_id="low", version=1, value_json={"confidence": 0.2}, is_current=True),
            FactVersion(tenant_id="tenant-a", fact_id="critical", version=1, value_json={"confidence": 0.9}, is_current=True),
            FactVersion(tenant_id="tenant-a", fact_id="conflict", version=1, value_json={"confidence": 0.8}, is_current=True),
        ])
        session.commit()

    response = TestClient(app).get(
        "/api/studies/study-a/fact-review",
        headers={"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"},
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["conflict", "critical", "low"]
    get_settings.cache_clear()


def test_review_queue_includes_value_confidence_and_exact_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'evidence-review.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        record = FileRecord(
            id="file-a", tenant_id="tenant-a", study_id="study-a", role="synopsis"
        )
        version = FileVersion(
            id="version-a", tenant_id="tenant-a", file_record_id=record.id, version=1,
            display_filename="synopsis.docx", checksum_sha256="a" * 64, size_bytes=10,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            storage_key="tenant/version-a.docx", status="succeeded",
        )
        evidence = SourceEvidence(
            id="evidence-a", tenant_id="tenant-a", file_version_id=version.id, ordinal=7,
            location_json={"kind": "paragraph", "index": 7},
            text="Arm: Experimental; Intervention: Example drug 10 mg once daily",
            text_sha256="b" * 64,
        )
        attempt = ProcessingAttempt(
            id="attempt-a", tenant_id="tenant-a", study_id="study-a",
            synopsis_version_id=version.id, extractor_name="local-rules",
            extractor_version="local-rules-v1", status="succeeded", findings_json=[],
        )
        fact = Fact(
            id="dose", tenant_id="tenant-a", study_id="study-a",
            processing_attempt_id=attempt.id, kind="dose", status="candidate", critical=True,
        )
        session.add_all([record, version, evidence, attempt, fact])
        session.flush()
        session.add(FactVersion(
            tenant_id="tenant-a", fact_id=fact.id, version=1,
            value_json={"kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"},
            confidence=1.0, source_evidence_id=evidence.id, is_current=True,
        ))
        session.commit()

    response = TestClient(app).get(
        "/api/studies/study-a/fact-review",
        headers={"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [{
        "id": "dose", "kind": "dose", "status": "candidate",
        "current_value": {"kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"},
        "confidence": 1.0,
        "source_evidence": {
            "id": "evidence-a", "location": {"kind": "paragraph", "index": 7},
            "text": "Arm: Experimental; Intervention: Example drug 10 mg once daily",
        },
        "critical": True, "version": 1, "extractor_version": "local-rules-v1",
        "synopsis_version_id": "version-a", "downstream_impact": ["study_design"],
    }]
    get_settings.cache_clear()
