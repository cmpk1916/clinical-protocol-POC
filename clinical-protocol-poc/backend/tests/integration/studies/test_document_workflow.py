from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.files.models import FileVersion, SourceEvidence, StudyInput
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.ingest.service import DOCX_CONTENT_TYPE, IngestService, UploadInput
from protocol_poc.studies.document_workflow import (
    DocumentWorkflowService,
    ProcessingConflict,
    ProcessingNotFound,
)
from protocol_poc.studies.local_extractor import ExtractionProposal, LocalCandidate
from protocol_poc.studies.models import (
    Fact,
    FactVersion,
    ImmutableProcessingAttemptError,
    ProcessingAttempt,
)
from protocol_poc.studies.service import StudyArchived, StudyNotFound, StudyService
from protocol_poc.tenancy import TenantContext


def docx(*paragraphs: str) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as package:
        package.writestr(
            "[Content_Types].xml",
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b"</Types>",
        )
        package.writestr(
            "_rels/.rels",
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            b"</Relationships>",
        )
        package.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'.encode(),
        )
    return output.getvalue()


def supported_synopsis(short_title: str = "SYN-1") -> bytes:
    return docx(
        "Study Identity",
        f"Short title: {short_title}",
        "Objectives",
        "Objective: Evaluate response",
        "Endpoints",
        "Endpoint: Response at Week 8",
        "Arms and Interventions",
        "Arm: Experimental; Intervention: Example drug 10 mg once daily",
        "Study Population",
        "Population: Adults with synthetic condition",
        "Eligibility Criteria",
        "Eligibility: Age 18 years or older",
    )


def supported_synopsis_without_dose() -> bytes:
    return docx(
        "Study Identity",
        "Short title: SYN-1",
        "Objectives",
        "Objective: Evaluate response",
        "Endpoints",
        "Endpoint: Response at Week 8",
        "Arms and Interventions",
        "Arm: Experimental; Intervention: Example drug",
        "Study Population",
        "Population: Adults with synthetic condition",
        "Eligibility Criteria",
        "Eligibility: Age 18 years or older",
    )


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def workflow(session: Session, tmp_path: Path) -> DocumentWorkflowService:
    return DocumentWorkflowService(session, IngestService(session, LocalFileStorage(tmp_path)))


def upload(content: bytes) -> UploadInput:
    return UploadInput("synopsis", "synopsis.docx", DOCX_CONTENT_TYPE, content)


def template_upload() -> UploadInput:
    return UploadInput(
        "template",
        "template.docx",
        DOCX_CONTENT_TYPE,
        docx(
            "[[SECTION:synopsis]]",
            "[[SECTION:objectives_endpoints]]",
            "[[SECTION:study_design]]",
            "[[SECTION:eligibility]]",
            "[[POC_DISCLAIMER]]",
        ),
    )


def test_first_valid_upload_activates_version_one(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")

    outcome = workflow(session, tmp_path).upload(ctx, study.id, upload(supported_synopsis()))
    current = session.scalar(select(StudyInput))

    assert outcome.status == "activated"
    assert outcome.version == 1
    assert outcome.findings == ()
    assert current is not None
    assert (current.current_file_version_id, current.conformance_status, current.revision) == (
        outcome.version_id,
        "conforming",
        1,
    )


def test_first_valid_template_upload_activates_template_role(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")

    outcome = workflow(session, tmp_path).upload(ctx, study.id, template_upload())
    current = session.scalar(select(StudyInput))

    assert outcome.status == "activated"
    assert current is not None and current.role == "template"


def test_invalid_upload_records_version_and_findings_without_activation(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")

    outcome = workflow(session, tmp_path).upload(
        ctx,
        study.id,
        upload(docx("Study Identity", "Short title: SYN-1")),
    )

    assert outcome.status == "conformance_failed"
    assert {finding.field for finding in outcome.findings} == {
        "objectives",
        "endpoints",
        "arms_interventions",
        "population",
        "eligibility",
    }
    assert session.scalar(select(StudyInput)) is None
    assert len(session.scalars(select(FileVersion)).all()) == 1
    assert len(session.scalars(select(SourceEvidence)).all()) == 2


def test_identical_upload_reuses_immutable_version(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    content = supported_synopsis()

    first = service.upload(ctx, study.id, upload(content))
    same = service.upload(ctx, study.id, upload(content))

    assert same.version_id == first.version_id
    assert same.status == "activated"
    assert len(session.scalars(select(FileVersion)).all()) == 1
    assert session.scalar(select(StudyInput)).revision == 1  # type: ignore[union-attr]


def test_second_valid_upload_requires_confirmation_and_leaves_version_one_current(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    first = service.upload(ctx, study.id, upload(supported_synopsis()))

    proposed = service.upload(ctx, study.id, upload(supported_synopsis("SYN-2")))
    current = session.scalar(select(StudyInput))

    assert proposed.status == "replacement_confirmation_required"
    assert proposed.version == 2
    assert proposed.current_file_version_id == first.version_id
    assert current is not None
    assert (current.current_file_version_id, current.revision) == (first.version_id, 1)
    assert len(session.scalars(select(FileVersion)).all()) == 2


def test_upload_rejects_archived_study_before_ingest(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    studies = StudyService(session)
    study = studies.create(ctx, "Synthetic Study")
    studies.archive(ctx, study.id, expected_version=1)

    with pytest.raises(StudyArchived):
        workflow(session, tmp_path).upload(ctx, study.id, upload(supported_synopsis()))

    assert session.scalars(select(FileVersion)).all() == []


def test_upload_rejects_cross_tenant_study_before_ingest(
    session: Session, tmp_path: Path
) -> None:
    study = StudyService(session).create(
        TenantContext("tenant-a", "actor-a"), "Synthetic Study"
    )

    with pytest.raises(StudyNotFound):
        workflow(session, tmp_path).upload(
            TenantContext("tenant-b", "actor-b"),
            study.id,
            upload(supported_synopsis()),
        )

    assert session.scalars(select(FileVersion)).all() == []


def test_process_persists_succeeded_attempt_and_candidate_facts(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    uploaded = service.upload(ctx, study.id, upload(supported_synopsis()))

    outcome = service.process(ctx, study.id, uploaded.version_id)

    attempt = session.get(ProcessingAttempt, outcome.attempt_id)
    facts = list(session.scalars(select(Fact).order_by(Fact.kind)))
    versions = list(session.scalars(select(FactVersion)))
    assert outcome.status == "succeeded"
    assert outcome.findings == ()
    assert attempt is not None
    assert (attempt.status, attempt.extractor_version, attempt.synopsis_version_id) == (
        "succeeded", "local-rules-v1", uploaded.version_id,
    )
    assert facts and {fact.status for fact in facts} == {"candidate"}
    assert {fact.processing_attempt_id for fact in facts} == {attempt.id}
    assert all(version.source_evidence_id for version in versions)


def test_process_failure_persists_findings_without_partial_facts(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    uploaded = service.upload(ctx, study.id, upload(supported_synopsis_without_dose()))

    outcome = service.process(ctx, study.id, uploaded.version_id)

    assert outcome.status == "failed"
    assert [finding.code for finding in outcome.findings] == ["SYNOPSIS_DOSE_MISSING"]
    assert session.scalars(select(Fact)).all() == []
    attempt = session.get(ProcessingAttempt, outcome.attempt_id)
    assert attempt is not None and attempt.status == "failed"
    assert attempt.findings_json[0]["code"] == "SYNOPSIS_DOSE_MISSING"


def test_retry_creates_new_attempt_for_unchanged_synopsis(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    uploaded = service.upload(ctx, study.id, upload(supported_synopsis_without_dose()))
    failed = service.process(ctx, study.id, uploaded.version_id)

    retried = service.retry(ctx, study.id, failed.attempt_id)

    assert retried.status == "failed"
    assert retried.attempt_id != failed.attempt_id
    attempts = list(session.scalars(select(ProcessingAttempt).order_by(ProcessingAttempt.started_at)))
    assert len(attempts) == 2
    assert {attempt.synopsis_version_id for attempt in attempts} == {uploaded.version_id}


def test_process_rejects_when_an_attempt_is_already_active(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    uploaded = service.upload(ctx, study.id, upload(supported_synopsis()))
    session.add(ProcessingAttempt(
        tenant_id=ctx.tenant_id, study_id=study.id,
        synopsis_version_id=uploaded.version_id, extractor_name="local-rules",
        extractor_version="local-rules-v1", status="processing", findings_json=[],
    ))
    session.commit()

    with pytest.raises(ProcessingConflict):
        service.process(ctx, study.id, uploaded.version_id)


def test_retry_rejects_attempt_when_synopsis_is_no_longer_current(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    first = service.upload(ctx, study.id, upload(supported_synopsis_without_dose()))
    failed = service.process(ctx, study.id, first.version_id)
    second = service.upload(ctx, study.id, upload(supported_synopsis("SYN-2")))
    current = session.scalar(select(StudyInput))
    assert current is not None
    current.current_file_version_id = second.version_id
    session.commit()

    with pytest.raises(ProcessingNotFound):
        service.retry(ctx, study.id, failed.attempt_id)


def test_claim_is_persisted_before_evidence_loading(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    uploaded = service.upload(ctx, study.id, upload(supported_synopsis()))
    original = service._ingest.evidence_for_version

    def evidence_after_claim(context: TenantContext, version_id: str):
        attempt = session.scalar(
            select(ProcessingAttempt).where(
                ProcessingAttempt.synopsis_version_id == version_id,
                ProcessingAttempt.status == "processing",
            )
        )
        assert attempt is not None
        return original(context, version_id)

    service._ingest.evidence_for_version = evidence_after_claim  # type: ignore[method-assign]

    assert service.process(ctx, study.id, uploaded.version_id).status == "succeeded"


@pytest.mark.parametrize(
    ("failure_stage", "error_code", "finding_code"),
    [
        ("evidence", "evidence_load_failed", "PROCESSING_EVIDENCE_LOAD_FAILED"),
        ("extractor", "extractor_failed", "PROCESSING_EXTRACTOR_FAILED"),
    ],
)
def test_unexpected_processing_failure_persists_retryable_attempt_without_facts(
    session: Session,
    tmp_path: Path,
    failure_stage: str,
    error_code: str,
    finding_code: str,
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    uploaded = service.upload(ctx, study.id, upload(supported_synopsis()))

    if failure_stage == "evidence":
        def fail_evidence(_context: TenantContext, _version_id: str):
            raise RuntimeError("sensitive evidence failure")

        service._ingest.evidence_for_version = fail_evidence  # type: ignore[method-assign]
    else:
        def fail_extract(_evidence: object):
            raise RuntimeError("sensitive extractor failure")

        service._extractor.extract = fail_extract  # type: ignore[method-assign]

    outcome = service.process(ctx, study.id, uploaded.version_id)

    attempt = session.get(ProcessingAttempt, outcome.attempt_id)
    assert outcome.status == "failed"
    assert [(item.code, item.field) for item in outcome.findings] == [
        (finding_code, "synopsis")
    ]
    assert attempt is not None and attempt.error_code == error_code
    assert "sensitive" not in str(attempt.findings_json)
    assert session.scalars(select(Fact)).all() == []


def test_current_synopsis_is_revalidated_after_extraction_before_persistence(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    first = service.upload(ctx, study.id, upload(supported_synopsis()))
    second = service.upload(ctx, study.id, upload(supported_synopsis("SYN-2")))
    original_extract = service._extractor.extract

    def change_current(evidence: object):
        proposal = original_extract(evidence)  # type: ignore[arg-type]
        current = session.scalar(select(StudyInput).where(StudyInput.role == "synopsis"))
        assert current is not None
        current.current_file_version_id = second.version_id
        session.commit()
        return proposal

    service._extractor.extract = change_current  # type: ignore[method-assign]

    outcome = service.process(ctx, study.id, first.version_id)

    assert outcome.status == "failed"
    assert [item.code for item in outcome.findings] == [
        "PROCESSING_SYNOPSIS_NO_LONGER_CURRENT"
    ]
    assert session.scalars(select(Fact)).all() == []


def test_candidate_evidence_must_belong_to_exact_attempt_synopsis(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    first = service.upload(ctx, study.id, upload(supported_synopsis()))
    second = service.upload(ctx, study.id, upload(supported_synopsis("SYN-2")))
    foreign_evidence = session.scalar(
        select(SourceEvidence).where(SourceEvidence.file_version_id == second.version_id)
    )
    assert foreign_evidence is not None

    service._extractor.extract = lambda _evidence: ExtractionProposal(  # type: ignore[method-assign]
        (
            LocalCandidate(
                "study_identity",
                {"kind": "string", "value": "corrupt"},
                foreign_evidence.id,
            ),
        ),
        (),
    )

    outcome = service.process(ctx, study.id, first.version_id)

    assert outcome.status == "failed"
    assert [item.code for item in outcome.findings] == [
        "PROCESSING_EVIDENCE_PROVENANCE_INVALID"
    ]
    assert session.scalars(select(Fact)).all() == []


def test_terminal_processing_attempt_rejects_orm_and_bulk_mutation(
    session: Session, tmp_path: Path
) -> None:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    service = workflow(session, tmp_path)
    uploaded = service.upload(ctx, study.id, upload(supported_synopsis()))
    outcome = service.process(ctx, study.id, uploaded.version_id)
    attempt = session.get(ProcessingAttempt, outcome.attempt_id)
    assert attempt is not None

    attempt.error_code = "tampered"
    with pytest.raises(ImmutableProcessingAttemptError):
        session.flush()
    session.rollback()

    attempt = session.get(ProcessingAttempt, outcome.attempt_id)
    assert attempt is not None
    session.delete(attempt)
    with pytest.raises(ImmutableProcessingAttemptError):
        session.flush()
    session.rollback()

    with pytest.raises(ImmutableProcessingAttemptError):
        session.execute(
            update(ProcessingAttempt)
            .where(ProcessingAttempt.id == outcome.attempt_id)
            .values(error_code="tampered")
        )
    with pytest.raises(ImmutableProcessingAttemptError):
        session.execute(
            delete(ProcessingAttempt).where(
                ProcessingAttempt.id == outcome.attempt_id
            )
        )
