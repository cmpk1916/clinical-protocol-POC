import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.drafting.models import Passage, PassageVersion, SupportLink
from protocol_poc.drafting.review_service import PassageBlocked, PassageReviewService, PassageVersionConflict
from protocol_poc.files.models import FileRecord, FileVersion, StudyInput
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, Study
from protocol_poc.tenancy import TenantContext


def test_passage_with_blocker_cannot_be_accepted() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        passage = Passage(id="passage-a", tenant_id="tenant-a", study_id="study-a", section="study_design", status="blocked", current_version=1)
        session.add(passage)
        session.flush()
        session.add(PassageVersion(tenant_id="tenant-a", passage_id=passage.id, version=1, text="[[REQUIRED: intervention dose]]", placeholders=["intervention dose"], is_current=True))
        session.commit()

        with pytest.raises(PassageBlocked):
            PassageReviewService(session).accept(TenantContext("tenant-a", "writer-a"), passage.id, expected_version=1)


def test_passage_with_persisted_validation_blocker_cannot_be_accepted() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        passage = Passage(
            id="passage-a",
            tenant_id="tenant-a",
            study_id="study-a",
            section="study_design",
            status="ready_for_review",
            current_version=1,
        )
        session.add(passage)
        session.flush()
        session.add(PassageVersion(
            tenant_id="tenant-a",
            passage_id=passage.id,
            version=1,
            text="Arm A receives 99 mg once daily.",
            placeholders=[],
            validation_findings=[{
                "code": "UNSUPPORTED_DOSE",
                "severity": "blocker",
                "message": "Dose 99 mg is not an approved fact",
                "source": "deterministic",
            }],
            is_current=True,
        ))
        session.commit()

        with pytest.raises(PassageBlocked, match="blocker-free"):
            PassageReviewService(session, validator=lambda _text: []).accept(
                TenantContext("tenant-a", "writer-a"),
                passage.id,
                expected_version=1,
            )


def test_passage_with_support_outside_current_approved_fact_set_cannot_be_accepted() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.add(FileRecord(
            id="synopsis-file", tenant_id="tenant-a", study_id="study-a", role="synopsis"
        ))
        session.flush()
        session.add(FileVersion(
            id="synopsis-v2", tenant_id="tenant-a", file_record_id="synopsis-file",
            version=2, display_filename="synopsis.docx", checksum_sha256="a" * 64,
            size_bytes=1,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            storage_key="tenant/synopsis.docx", status="succeeded",
        ))
        session.add(StudyInput(
            tenant_id="tenant-a", study_id="study-a", role="synopsis",
            current_file_version_id="synopsis-v2", conformance_status="conforming",
        ))
        session.add(ProcessingAttempt(
            id="attempt-v2", tenant_id="tenant-a", study_id="study-a",
            synopsis_version_id="synopsis-v2", extractor_name="local-rules",
            extractor_version="local-rules-v1", status="succeeded", findings_json=[],
        ))
        session.add(Fact(
            id="superseded-fact", tenant_id="tenant-a", study_id="study-a",
            processing_attempt_id="old-attempt", kind="dose", status="superseded",
        ))
        session.flush()
        session.add(FactVersion(
            tenant_id="tenant-a", fact_id="superseded-fact", version=1,
            value_json={"value": "10", "unit": "mg"}, is_current=True,
        ))
        passage = Passage(
            id="passage-a", tenant_id="tenant-a", study_id="study-a",
            section="study_design", status="ready_for_review", current_version=1,
        )
        session.add(passage)
        session.flush()
        version = PassageVersion(
            id="passage-version-a", tenant_id="tenant-a", passage_id=passage.id,
            version=1, text="Synthetic bounded text.", placeholders=[], is_current=True,
        )
        session.add(version)
        session.flush()
        session.add(SupportLink(
            tenant_id="tenant-a", passage_version_id=version.id,
            support_type="fact", support_id="superseded-fact",
        ))
        session.commit()

        with pytest.raises(PassageBlocked, match="current approved fact set"):
            PassageReviewService(session, validator=lambda _text: []).accept(
                TenantContext("tenant-a", "writer-a"), passage.id, expected_version=1
            )


def test_reject_requires_current_passage_version() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        passage = Passage(id="passage-a", tenant_id="tenant-a", study_id="study-a", section="study_design", status="ready_for_review", current_version=2)
        session.add(passage)
        session.flush()
        session.add(PassageVersion(tenant_id="tenant-a", passage_id=passage.id, version=2, text="Arm A receives Synthetic Intervention A, 10 mg once daily, for 24 weeks.", placeholders=[], is_current=True))
        session.commit()

        with pytest.raises(PassageVersionConflict):
            PassageReviewService(session).reject(TenantContext("tenant-a", "writer-a"), passage.id, expected_version=1, rationale="Synthetic rejection")


def test_database_rejects_multiple_current_passage_versions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.add(Passage(
            id="passage-a", tenant_id="tenant-a", study_id="study-a",
            section="study_design", status="draft", current_version=2,
        ))
        session.add_all([
            PassageVersion(
                id="version-a", tenant_id="tenant-a", passage_id="passage-a", version=1,
                text="Synthetic version one.", placeholders=[], is_current=True,
            ),
            PassageVersion(
                id="version-b", tenant_id="tenant-a", passage_id="passage-a", version=2,
                text="Synthetic version two.", placeholders=[], is_current=True,
            ),
        ])

        with pytest.raises(IntegrityError):
            session.commit()
