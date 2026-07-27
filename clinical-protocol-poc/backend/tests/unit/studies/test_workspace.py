import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.drafting.models import Passage, PassageVersion
from protocol_poc.export.models import ExportSnapshot
from protocol_poc.files.models import FileRecord, FileVersion, StudyInput
from protocol_poc.studies.models import Fact, ProcessingAttempt
from protocol_poc.studies.service import StudyService
from protocol_poc.studies.workspace import WorkspaceSummaryService
from protocol_poc.tenancy import TenantContext


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _current_input(session: Session, study_id: str, role: str) -> str:
    record = FileRecord(tenant_id="tenant", study_id=study_id, role=role)
    session.add(record)
    session.flush()
    version = FileVersion(
        tenant_id="tenant",
        file_record_id=record.id,
        version=1,
        display_filename=f"{role}.docx",
        checksum_sha256=("a" if role == "synopsis" else "b") * 64,
        size_bytes=100,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        storage_key=f"tenant/{record.id}.docx",
        status="succeeded",
    )
    session.add(version)
    session.flush()
    session.add(
        StudyInput(
            tenant_id="tenant",
            study_id=study_id,
            role=role,
            current_file_version_id=version.id,
            conformance_status="conforming",
            revision=1,
        )
    )
    session.flush()
    return version.id


def _scenario(session: Session, state: str) -> tuple[TenantContext, str]:
    ctx = TenantContext("tenant", "actor")
    study = StudyService(session).create(ctx, "Synthetic Study")
    if state == "no_inputs":
        return ctx, study.id
    synopsis_id = _current_input(session, study.id, "synopsis")
    _current_input(session, study.id, "template")
    if state == "needs_processing":
        return ctx, study.id
    attempt = ProcessingAttempt(
        tenant_id="tenant",
        study_id=study.id,
        synopsis_version_id=synopsis_id,
        extractor_name="local-rules",
        extractor_version="local-rules-v1",
        status="succeeded",
        findings_json=[],
    )
    session.add(attempt)
    session.flush()
    if state == "candidate_facts":
        session.add(Fact(tenant_id="tenant", study_id=study.id, kind="dose", status="candidate"))
        session.flush()
        return ctx, study.id
    session.add(Fact(tenant_id="tenant", study_id=study.id, kind="dose", status="approved"))
    session.flush()
    if state == "accepted_facts":
        return ctx, study.id
    for section in ("synopsis", "objectives_endpoints", "study_design", "eligibility"):
        session.add(Passage(tenant_id="tenant", study_id=study.id, section=section, status="accepted"))
    session.flush()
    if state == "accepted_passages":
        return ctx, study.id
    session.add(
        ExportSnapshot(
            tenant_id="tenant",
            study_id=study.id,
            study_version=study.version,
            renderer_version="renderer-v1",
        )
    )
    session.flush()
    return ctx, study.id


@pytest.mark.parametrize(
    ("state", "step", "action"),
    [
        ("no_inputs", "inputs", "upload_synopsis"),
        ("needs_processing", "processing", "process_synopsis"),
        ("candidate_facts", "fact_review", "review_facts"),
        ("accepted_facts", "passage_review", "generate_passages"),
        ("accepted_passages", "export", "create_export"),
        ("exported", "export", "view_export"),
    ],
)
def test_workspace_derives_next_safe_action(
    session: Session, state: str, step: str, action: str
) -> None:
    ctx, study_id = _scenario(session, state)

    summary = WorkspaceSummaryService(session).get(ctx, study_id)

    assert (summary.step, summary.next_action.kind) == (step, action)


def test_workspace_exposes_fact_review_as_an_export_blocker(
    session: Session,
) -> None:
    ctx, study_id = _scenario(session, "candidate_facts")

    summary = WorkspaceSummaryService(session).get(ctx, study_id)

    assert [(item.code, item.message) for item in summary.blockers] == [
        (
            "FACT_REVIEW_INCOMPLETE",
            "One candidate fact must be reviewed before drafting or export.",
        )
    ]


def test_workspace_returns_the_current_conformed_template_export_command(
    session: Session,
) -> None:
    ctx, study_id = _scenario(session, "accepted_passages")

    summary = WorkspaceSummaryService(session).get(ctx, study_id)

    assert summary.export_command is not None
    assert summary.export_command.expected_study_version == 1
    assert summary.export_command.template_version_id == summary.inputs["template"].version_id  # type: ignore[union-attr]
    assert summary.export_command.template_hash == "b" * 64


def test_workspace_reports_latest_failed_attempt_findings_and_retry(session: Session) -> None:
    ctx, study_id = _scenario(session, "needs_processing")
    synopsis = WorkspaceSummaryService(session).get(ctx, study_id).inputs["synopsis"]
    assert synopsis is not None
    session.add(
        ProcessingAttempt(
            id="attempt-failed",
            tenant_id="tenant",
            study_id=study_id,
            synopsis_version_id=synopsis.version_id,
            extractor_name="local-rules",
            extractor_version="local-rules-v1",
            status="failed",
            error_code="extraction_findings",
            findings_json=[
                {
                    "code": "SYNOPSIS_DOSE_MISSING",
                    "field": "dose",
                    "message": "A dose is required.",
                }
            ],
        )
    )
    session.flush()

    summary = WorkspaceSummaryService(session).get(ctx, study_id)

    assert summary.next_action.kind == "retry_processing"
    assert summary.next_action.target_id == "attempt-failed"
    assert [(item.code, item.message) for item in summary.blockers] == [
        ("SYNOPSIS_DOSE_MISSING", "A dose is required.")
    ]


def test_archived_workspace_remains_viewable_and_is_read_only(session: Session) -> None:
    ctx, study_id = _scenario(session, "candidate_facts")
    study = StudyService(session).get(ctx, study_id)
    StudyService(session).archive(ctx, study_id, study.version)

    summary = WorkspaceSummaryService(session).get(ctx, study_id)

    assert summary.step == "archived"
    assert summary.read_only is True
    assert summary.counts.candidate_facts == 1
    assert summary.next_action.kind == "restore_study"


def test_workspace_surfaces_stale_passage_before_export(session: Session) -> None:
    ctx, study_id = _scenario(session, "accepted_facts")
    for index, section in enumerate(("synopsis", "objectives_endpoints", "study_design")):
        session.add(
            Passage(
                id=f"passage-{index}",
                tenant_id="tenant",
                study_id=study_id,
                section=section,
                status="accepted",
            )
        )
    session.add(
        Passage(
            tenant_id="tenant",
            study_id=study_id,
            section="eligibility",
            status="stale",
        )
    )
    session.flush()

    summary = WorkspaceSummaryService(session).get(ctx, study_id)

    assert summary.step == "passage_review"
    assert summary.next_action.kind == "review_passages"
    assert [(item.code, item.message) for item in summary.blockers] == [
        ("STALE_PASSAGE", "One current draft passage is stale and must be regenerated.")
    ]


def test_workspace_surfaces_quality_blockers_before_export(session: Session) -> None:
    ctx, study_id = _scenario(session, "accepted_passages")
    passages = list(session.query(Passage).all())
    for passage in passages:
        session.add(
            PassageVersion(
                tenant_id="tenant",
                passage_id=passage.id,
                version=1,
                text="Synthetic accepted passage.",
                placeholders=[],
                is_current=True,
            )
        )
    session.flush()

    summary = WorkspaceSummaryService(session).get(ctx, study_id)

    assert summary.step == "export"
    assert summary.next_action.kind == "review_quality"
    assert {item.code for item in summary.blockers} == {"INCOMPLETE_PROVENANCE"}


def test_database_rejects_duplicate_required_passage_sections(
    session: Session,
) -> None:
    ctx, study_id = _scenario(session, "accepted_facts")
    for index, section in enumerate(
        ("synopsis", "objectives_endpoints", "study_design", "study_design")
    ):
        session.add(
            Passage(
                id=f"duplicate-{index}",
                tenant_id="tenant",
                study_id=study_id,
                section=section,
                status="accepted",
            )
        )
    with pytest.raises(IntegrityError):
        session.flush()
