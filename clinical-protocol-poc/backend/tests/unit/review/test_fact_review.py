import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from protocol_poc.audit.models import AuditEvent
from protocol_poc.db import Base
from protocol_poc.files.models import FileRecord, FileVersion, SourceEvidence
from protocol_poc.review.fact_service import (
    ExplicitConfirmationRequired,
    FactReviewError,
    FactReviewService,
    UnresolvedConflict,
)
from protocol_poc.studies.service import StudyArchived
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, Study
from protocol_poc.tenancy import TenantContext


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.commit()
        yield session


def add_fact(session: Session, *, fact_id: str, status: str = "candidate", critical: bool = False) -> Fact:
    if session.get(ProcessingAttempt, "review-attempt") is None:
        record = FileRecord(
            id="review-file", tenant_id="tenant-a", study_id="study-a", role="synopsis"
        )
        version = FileVersion(
            id="review-version", tenant_id="tenant-a", file_record_id=record.id,
            version=1, display_filename="synopsis.docx", checksum_sha256="a" * 64,
            size_bytes=10,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            storage_key="tenant/review-version.docx", status="succeeded",
        )
        evidence = SourceEvidence(
            id="review-evidence", tenant_id="tenant-a", file_version_id=version.id,
            ordinal=0, location_json={"kind": "paragraph", "index": 0},
            text="Example drug 10 mg", text_sha256="b" * 64,
        )
        attempt = ProcessingAttempt(
            id="review-attempt", tenant_id="tenant-a", study_id="study-a",
            synopsis_version_id=version.id, extractor_name="local-rules",
            extractor_version="local-rules-v1", status="succeeded", findings_json=[],
        )
        session.add_all([record, version, evidence, attempt])
        session.flush()
    fact = Fact(
        id=fact_id, tenant_id="tenant-a", study_id="study-a",
        processing_attempt_id="review-attempt", kind="dose", status=status,
        critical=critical,
    )
    session.add_all([
        fact,
        FactVersion(
            tenant_id="tenant-a", fact_id=fact_id, version=1,
            value_json={"value": "10 mg"}, source_evidence_id="review-evidence",
            source_evidence_version_id="review-version", is_current=True,
        ),
    ])
    session.commit()
    return fact


def test_critical_fact_requires_explicit_confirmation(session: Session) -> None:
    fact = add_fact(session, fact_id="critical", critical=True)
    with pytest.raises(ExplicitConfirmationRequired):
        FactReviewService(session).approve(TenantContext("tenant-a", "writer-a"), fact.id, expected_version=1, explicitly_confirmed=False)


def test_duration_fact_reports_study_design_downstream_impact() -> None:
    assert FactReviewService._downstream_impact("duration") == ("study_design",)


def test_conflicting_candidate_cannot_be_approved(session: Session) -> None:
    fact = add_fact(session, fact_id="conflict", status="conflicted")
    with pytest.raises(UnresolvedConflict):
        FactReviewService(session).approve(TenantContext("tenant-a", "writer-a"), fact.id, expected_version=1, explicitly_confirmed=True)


def test_correction_supersedes_version_and_appends_audit(session: Session) -> None:
    fact = add_fact(session, fact_id="correct-me")
    result = FactReviewService(session).correct_and_approve(
        TenantContext("tenant-a", "writer-a"), fact.id, expected_version=1,
        value_json={"kind": "dose", "value": "12", "unit": "mg"}, rationale="Source correction",
        explicitly_confirmed=True,
    )
    session.commit()

    versions = list(session.scalars(select(FactVersion).where(FactVersion.fact_id == fact.id).order_by(FactVersion.version)))
    assert result.status == "approved"
    assert [version.is_current for version in versions] == [False, True]
    assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "fact.corrected_and_approved")) is not None


def test_archived_guard_precedes_fact_version_validation(session: Session) -> None:
    fact = add_fact(session, fact_id="archived")
    study = session.get(Study, "study-a")
    assert study is not None
    study.lifecycle = "archived"
    session.commit()

    with pytest.raises(StudyArchived):
        FactReviewService(session).approve(
            TenantContext("tenant-a", "writer-a"),
            fact.id,
            expected_version=999,
            explicitly_confirmed=True,
        )


def test_deferred_fact_remains_visible_and_can_be_resumed(session: Session) -> None:
    fact = add_fact(session, fact_id="deferred")
    service = FactReviewService(session)
    ctx = TenantContext("tenant-a", "writer-a")

    service.defer(ctx, fact.id, expected_version=1, rationale="Review later")
    assert [item.id for item in service.review_queue(ctx, "study-a")] == [fact.id]

    resumed = service.resume(ctx, fact.id, expected_version=1, rationale="Evidence checked")

    assert resumed.deferred is False


def test_approved_fact_cannot_be_approved_again(session: Session) -> None:
    fact = add_fact(session, fact_id="already-approved", status="approved")

    with pytest.raises(FactReviewError, match="cannot transition"):
        FactReviewService(session).approve(
            TenantContext("tenant-a", "writer-a"),
            fact.id,
            expected_version=1,
            explicitly_confirmed=True,
        )


def test_rejected_fact_cannot_be_corrected_and_approved(session: Session) -> None:
    fact = add_fact(session, fact_id="rejected-correction", status="rejected")

    with pytest.raises(FactReviewError, match="cannot transition"):
        FactReviewService(session).correct_and_approve(
            TenantContext("tenant-a", "writer-a"),
            fact.id,
            expected_version=1,
            value_json={"value": "12 mg"},
            rationale="Invalid retry",
            explicitly_confirmed=True,
        )


def test_approved_fact_cannot_be_rejected(session: Session) -> None:
    fact = add_fact(session, fact_id="approved-rejection", status="approved")

    with pytest.raises(FactReviewError, match="cannot transition"):
        FactReviewService(session).reject(
            TenantContext("tenant-a", "writer-a"),
            fact.id,
            expected_version=1,
            rationale="Invalid rejection",
        )


def test_only_deferred_candidate_can_resume(session: Session) -> None:
    fact = add_fact(session, fact_id="not-deferred")

    with pytest.raises(FactReviewError, match="cannot transition"):
        FactReviewService(session).resume(
            TenantContext("tenant-a", "writer-a"),
            fact.id,
            expected_version=1,
            rationale="Invalid resume",
        )


def test_deferred_candidate_cannot_be_deferred_again(session: Session) -> None:
    fact = add_fact(session, fact_id="already-deferred")
    fact.deferred = True
    session.commit()

    with pytest.raises(FactReviewError, match="cannot transition"):
        FactReviewService(session).defer(
            TenantContext("tenant-a", "writer-a"),
            fact.id,
            expected_version=1,
            rationale="Invalid defer",
        )
