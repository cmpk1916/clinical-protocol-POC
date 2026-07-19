import pytest
from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.db import Base
from protocol_poc.files.models import FileRecord, FileVersion, SourceEvidence
from protocol_poc.review.conflicts import FactConflict
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
            confidence=1.0, source_evidence_id=evidence.id,
            source_evidence_version_id=version.id, is_current=True,
        ))
        session.commit()

    response = TestClient(app).get(
        "/api/studies/study-a/fact-review",
        headers={"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [{
        "id": "dose", "kind": "dose", "status": "candidate", "deferred": False,
        "current_value": {"kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"},
        "confidence": 1.0,
        "source_evidence": {
            "id": "evidence-a", "location": {"kind": "paragraph", "index": 7},
            "text": "Arm: Experimental; Intervention: Example drug 10 mg once daily",
        },
        "evidence_valid": True,
        "critical": True, "version": 1, "extractor_version": "local-rules-v1",
        "synopsis_version_id": "version-a", "downstream_impact": ["study_design"],
    }]
    get_settings.cache_clear()


def test_review_queue_excludes_cross_version_evidence_but_remains_viewable_when_archived(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'provenance-review.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        session.add(
            Study(
                id="study-a",
                tenant_id="tenant-a",
                name="Archived study",
                lifecycle="archived",
            )
        )
        record = FileRecord(
            id="file-a", tenant_id="tenant-a", study_id="study-a", role="synopsis"
        )
        versions = [
            FileVersion(
                id=f"version-{suffix}",
                tenant_id="tenant-a",
                file_record_id=record.id,
                version=index,
                display_filename="synopsis.docx",
                checksum_sha256=checksum * 64,
                size_bytes=10,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                storage_key=f"tenant/version-{suffix}.docx",
                status="succeeded",
            )
            for index, suffix, checksum in ((1, "a", "a"), (2, "b", "b"))
        ]
        evidence = [
            SourceEvidence(
                id="evidence-a", tenant_id="tenant-a", file_version_id="version-a",
                ordinal=0, location_json={"kind": "paragraph", "index": 0},
                text="archived but viewable evidence", text_sha256="c" * 64,
            ),
            SourceEvidence(
                id="evidence-b", tenant_id="tenant-a", file_version_id="version-b",
                ordinal=0, location_json={"kind": "paragraph", "index": 0},
                text="evidence from wrong version", text_sha256="d" * 64,
            ),
        ]
        attempt = ProcessingAttempt(
            id="attempt-a",
            tenant_id="tenant-a",
            study_id="study-a",
            synopsis_version_id="version-a",
            extractor_name="local-rules",
            extractor_version="local-rules-v1",
            status="succeeded",
            findings_json=[],
        )
        facts = [
            Fact(
                id="valid-viewable",
                tenant_id="tenant-a",
                study_id="study-a",
                processing_attempt_id="attempt-a",
                kind="population",
                status="candidate",
            ),
            Fact(
                id="corrupt-hidden",
                tenant_id="tenant-a",
                study_id="study-a",
                processing_attempt_id="attempt-a",
                kind="population",
                status="candidate",
            ),
        ]
        session.add_all([record, *versions, *evidence, attempt, *facts])
        session.flush()
        session.add_all(
            [
                FactVersion(
                    tenant_id="tenant-a",
                    fact_id="valid-viewable",
                    version=1,
                    value_json={"kind": "string", "value": "legacy"},
                    source_evidence_id="evidence-a",
                    source_evidence_version_id="version-a",
                    is_current=True,
                ),
                FactVersion(
                    tenant_id="tenant-a",
                    fact_id="corrupt-hidden",
                    version=1,
                    value_json={"kind": "string", "value": "corrupt"},
                    source_evidence_id="evidence-b",
                    source_evidence_version_id="version-b",
                    is_current=True,
                ),
            ]
        )
        session.commit()

    response = TestClient(app).get(
        "/api/studies/study-a/fact-review",
        headers={"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        "corrupt-hidden",
        "valid-viewable",
    ]
    invalid = response.json()["items"][0]
    assert invalid["evidence_valid"] is False
    assert invalid["source_evidence"] is None
    get_settings.cache_clear()


def test_review_queue_fails_closed_for_mismatched_exact_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'invalid-evidence.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        record = FileRecord(id="file-a", tenant_id="tenant-a", study_id="study-a", role="synopsis")
        versions = [
            FileVersion(
                id=f"version-{suffix}", tenant_id="tenant-a", file_record_id="file-a",
                version=index, display_filename="synopsis.docx", checksum_sha256=checksum * 64,
                size_bytes=10,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                storage_key=f"tenant/version-{suffix}.docx", status="succeeded",
            )
            for index, suffix, checksum in ((1, "a", "a"), (2, "b", "b"))
        ]
        evidence = SourceEvidence(
            id="wrong-evidence", tenant_id="tenant-a", file_version_id="version-b", ordinal=0,
            location_json={"kind": "paragraph", "index": 0}, text="wrong version",
            text_sha256="c" * 64,
        )
        attempt = ProcessingAttempt(
            id="attempt-a", tenant_id="tenant-a", study_id="study-a",
            synopsis_version_id="version-a", extractor_name="local-rules",
            extractor_version="local-rules-v1", status="succeeded", findings_json=[],
        )
        fact = Fact(
            id="fact-a", tenant_id="tenant-a", study_id="study-a",
            processing_attempt_id="attempt-a", kind="population", status="candidate",
        )
        session.add_all([record, *versions, evidence, attempt, fact])
        session.flush()
        session.add(FactVersion(
            tenant_id="tenant-a", fact_id="fact-a", version=1,
            value_json={"kind": "string", "value": "Synthetic adults"},
            source_evidence_id="wrong-evidence", source_evidence_version_id="version-b",
            is_current=True,
        ))
        session.commit()

    client = TestClient(app)
    headers = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}
    queue = client.get("/api/studies/study-a/fact-review", headers=headers)

    assert queue.status_code == 200
    assert queue.json()["items"][0]["evidence_valid"] is False
    assert queue.json()["items"][0]["source_evidence"] is None
    mutation = client.post(
        "/api/facts/fact-a/review", headers=headers,
        json={"action": "approve", "expected_version": 1, "explicitly_confirmed": True},
    )
    assert mutation.status_code == 409
    assert mutation.json() == {"detail": {"code": "EXACT_EVIDENCE_UNAVAILABLE"}}
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("action", "status", "extra"),
    [
        ("approve", "candidate", {"explicitly_confirmed": True}),
        (
            "correct_and_approve",
            "candidate",
            {"value": {"kind": "string", "value": "corrected"}, "rationale": "Correction"},
        ),
        ("reject", "candidate", {"rationale": "Reject"}),
        ("defer", "candidate", {"rationale": "Defer"}),
        ("resume", "candidate", {"rationale": "Resume"}),
        ("resolve_conflict", "conflicted", {"rationale": "Resolve"}),
    ],
)
def test_review_mutations_fail_closed_without_a_processing_attempt_and_evidence(
    tmp_path, monkeypatch, action: str, status: str, extra: dict[str, object]
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / f'{action}.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        fact = Fact(
            id="fact-a",
            tenant_id="tenant-a",
            study_id="study-a",
            processing_attempt_id=None,
            kind="population",
            status=status,
        )
        session.add(fact)
        session.flush()
        session.add(
            FactVersion(
                tenant_id="tenant-a",
                fact_id=fact.id,
                version=1,
                value_json={"kind": "string", "value": "Synthetic adults"},
                is_current=True,
            )
        )
        if status == "conflicted":
            session.add(
                FactConflict(
                    tenant_id="tenant-a",
                    fact_id=fact.id,
                    conflicting_fact_id=fact.id,
                    status="open",
                )
            )
        session.commit()

    response = TestClient(app).post(
        "/api/facts/fact-a/review",
        headers={"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"},
        json={"action": action, "expected_version": 1, **extra},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "EXACT_EVIDENCE_UNAVAILABLE"}}
    get_settings.cache_clear()


def test_review_queue_keeps_candidate_without_current_version_visible_and_blocked(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'missing-version.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        session.add_all(
            [
                Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"),
                Fact(
                    id="fact-a",
                    tenant_id="tenant-a",
                    study_id="study-a",
                    kind="population",
                    status="candidate",
                ),
            ]
        )
        session.commit()

    client = TestClient(app)
    headers = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}
    workspace = client.get("/api/studies/study-a/workspace", headers=headers)
    response = client.get("/api/studies/study-a/fact-review", headers=headers)

    assert workspace.status_code == 200
    assert workspace.json()["counts"]["candidate_facts"] == 1
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    item = response.json()["items"][0]
    assert item["id"] == "fact-a"
    assert item["current_value"] == {}
    assert item["evidence_valid"] is False
    assert item["source_evidence"] is None
    get_settings.cache_clear()


def test_conflict_resolution_requires_rationale_and_returns_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'conflict-review.db'}")
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
            id="evidence-a", tenant_id="tenant-a", file_version_id=version.id, ordinal=0,
            location_json={"kind": "paragraph", "index": 0}, text="Dose 10 mg",
            text_sha256="b" * 64,
        )
        attempt = ProcessingAttempt(
            id="attempt-a", tenant_id="tenant-a", study_id="study-a",
            synopsis_version_id=version.id, extractor_name="local-rules",
            extractor_version="local-rules-v1", status="succeeded", findings_json=[],
        )
        facts = [
            Fact(
                id="fact-a", tenant_id="tenant-a", study_id="study-a",
                processing_attempt_id=attempt.id, kind="dose", status="conflicted",
            ),
            Fact(
                id="fact-b", tenant_id="tenant-a", study_id="study-a",
                processing_attempt_id=attempt.id, kind="dose", status="candidate",
            ),
        ]
        session.add_all([record, version, evidence, attempt, *facts])
        session.flush()
        session.add_all([
            FactVersion(
                tenant_id="tenant-a", fact_id=item.id, version=1,
                value_json={"value": "10 mg"}, source_evidence_id=evidence.id,
                source_evidence_version_id=version.id, is_current=True,
            )
            for item in facts
        ])
        session.add(FactConflict(
            tenant_id="tenant-a", fact_id="fact-a", conflicting_fact_id="fact-b", status="open",
        ))
        session.commit()

    client = TestClient(app)
    headers = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"}
    missing = client.post(
        "/api/facts/fact-a/review", headers=headers,
        json={"action": "resolve_conflict", "expected_version": 1, "rationale": "   "},
    )
    assert missing.status_code == 422
    assert missing.json() == {"detail": {"code": "RATIONALE_REQUIRED"}}

    resolved = client.post(
        "/api/facts/fact-a/review", headers=headers,
        json={"action": "resolve_conflict", "expected_version": 1, "rationale": "Use synopsis wording"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "candidate"
    get_settings.cache_clear()
