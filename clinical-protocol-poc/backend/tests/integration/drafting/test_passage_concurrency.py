import os
import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.drafting.models import Passage, PassageVersion, SupportLink
from protocol_poc.drafting.review_service import PassageReviewService
from protocol_poc.files.models import (
    FileRecord,
    FileVersion,
    SourceEvidence,
    StudyInput,
)
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.ingest.service import IngestService
from protocol_poc.studies.document_workflow import DocumentWorkflowService
from protocol_poc.studies.local_extractor import ExtractionProposal, LocalCandidate
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, Study
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext


@pytest.fixture
def postgres_engine():
    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for row-lock concurrency coverage")
    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_reviewable_passage(engine) -> None:
    with Session(engine) as session:
        session.add(Study(
            id="study-a", tenant_id="tenant-a", name="Synthetic study", version=1
        ))
        session.add(FileRecord(
            id="synopsis-file", tenant_id="tenant-a", study_id="study-a",
            role="synopsis",
        ))
        session.flush()
        session.add(FileVersion(
            id="synopsis-v1", tenant_id="tenant-a",
            file_record_id="synopsis-file", version=1,
            display_filename="synopsis.docx", checksum_sha256="a" * 64,
            size_bytes=1,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            storage_key="tenant/synopsis.docx", status="succeeded",
        ))
        session.add(FileVersion(
            id="synopsis-v2", tenant_id="tenant-a",
            file_record_id="synopsis-file", version=2,
            display_filename="synopsis-v2.docx", checksum_sha256="b" * 64,
            size_bytes=1,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            storage_key="tenant/synopsis-v2.docx", status="succeeded",
        ))
        session.add(SourceEvidence(
            id="proposed-evidence", tenant_id="tenant-a",
            file_version_id="synopsis-v2", ordinal=0,
            location_json={"paragraph": 0}, text="Synthetic replacement evidence.",
            text_sha256="c" * 64,
        ))
        session.add(StudyInput(
            tenant_id="tenant-a", study_id="study-a", role="synopsis",
            current_file_version_id="synopsis-v1",
            conformance_status="conforming",
        ))
        session.add(ProcessingAttempt(
            id="attempt-v1", tenant_id="tenant-a", study_id="study-a",
            synopsis_version_id="synopsis-v1", extractor_name="local-rules",
            extractor_version="local-rules-v1", status="succeeded",
            findings_json=[],
        ))
        session.flush()
        session.add(Fact(
            id="fact-a", tenant_id="tenant-a", study_id="study-a",
            processing_attempt_id="attempt-v1", kind="dose", status="approved",
        ))
        session.flush()
        session.add(FactVersion(
            id="fact-version-a", tenant_id="tenant-a", fact_id="fact-a",
            version=1, value_json={"kind": "dose", "value": "10", "unit": "mg"},
            is_current=True,
        ))
        session.add(Passage(
            id="passage-a", tenant_id="tenant-a", study_id="study-a",
            section="study_design", status="ready_for_review", current_version=1,
        ))
        session.flush()
        session.add(PassageVersion(
            id="passage-version-a", tenant_id="tenant-a",
            passage_id="passage-a", version=1,
            text="Synthetic bounded passage.", placeholders=[], is_current=True,
        ))
        session.flush()
        session.add(SupportLink(
            tenant_id="tenant-a", passage_version_id="passage-version-a",
            support_type="fact", support_id="fact-a",
        ))
        session.commit()


@pytest.mark.parametrize("concurrent_mutation", ["replacement", "archive"])
def test_accept_serializes_with_replacement_and_archive(
    postgres_engine, concurrent_mutation: str, tmp_path: Path
) -> None:
    _seed_reviewable_passage(postgres_engine)
    ctx = TenantContext("tenant-a", "writer-a")
    validation_started = threading.Event()
    release_accept = threading.Event()
    mutation_started = threading.Event()
    mutation_complete = threading.Event()
    accept_complete = threading.Event()
    errors: list[BaseException] = []

    def validator(_text: str):
        validation_started.set()
        assert release_accept.wait(timeout=5)
        return []

    def accept() -> None:
        try:
            with Session(postgres_engine) as session:
                PassageReviewService(session, validator=validator).accept(
                    ctx, "passage-a", expected_version=1
                )
                session.commit()
                accept_complete.set()
        except BaseException as error:
            errors.append(error)
            release_accept.set()

    def mutate() -> None:
        try:
            with Session(postgres_engine) as session:
                mutation_started.set()
                if concurrent_mutation == "archive":
                    StudyService(session).archive(ctx, "study-a", expected_version=1)
                else:
                    evidence = session.get(SourceEvidence, "proposed-evidence")
                    assert evidence is not None
                    workflow = DocumentWorkflowService(
                        session,
                        IngestService(session, LocalFileStorage(tmp_path)),
                    )
                    proposal = ExtractionProposal(
                        (
                            LocalCandidate(
                                "dose",
                                {"kind": "dose", "value": "20", "unit": "mg"},
                                evidence.id,
                            ),
                        ),
                        (),
                    )
                    workflow._extract_replacement = lambda *_: (  # type: ignore[method-assign]
                        proposal,
                        {evidence.id: evidence},
                    )
                    workflow.confirm_replacement(
                        ctx,
                        "study-a",
                        "synopsis",
                        "synopsis-v2",
                        "synopsis-v1",
                        1,
                    )
                session.commit()
                mutation_complete.set()
        except BaseException as error:
            errors.append(error)
            release_accept.set()

    accept_thread = threading.Thread(target=accept)
    mutation_thread = threading.Thread(target=mutate)
    accept_thread.start()
    assert validation_started.wait(timeout=5)
    mutation_thread.start()
    assert mutation_started.wait(timeout=5)
    completed_before_accept_release = mutation_complete.wait(timeout=0.3)
    release_accept.set()
    accept_thread.join(timeout=5)
    mutation_thread.join(timeout=5)

    assert errors == []
    assert accept_complete.is_set()
    assert mutation_complete.is_set()
    assert completed_before_accept_release is False
    with Session(postgres_engine) as session:
        study = session.get(Study, "study-a")
        passage = session.get(Passage, "passage-a")
        assert study is not None and passage is not None
        if concurrent_mutation == "replacement":
            assert passage.status == "stale"
        else:
            assert study.lifecycle == "archived"
