from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from protocol_poc.db import Base
from protocol_poc.app import create_app
from protocol_poc.audit.models import AuditEvent
from protocol_poc.config import Settings
from protocol_poc.drafting.models import Passage, PassageVersion, SupportLink
from protocol_poc.files.models import StudyInput
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.ingest.service import DOCX_CONTENT_TYPE, IngestService, UploadInput
from protocol_poc.studies.document_workflow import (
    DocumentWorkflowService,
    ReplacementValidationError,
)
from protocol_poc.studies.models import Fact, ProcessingAttempt
from protocol_poc.studies.service import StudyService, StudyVersionConflict
from protocol_poc.studies.routes import database_session
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
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        package.writestr(
            "_rels/.rels",
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        package.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'.encode(),
        )
    return output.getvalue()


def supported_synopsis(short_title: str) -> bytes:
    return docx(
        "Study Identity", f"Short title: {short_title}", "Objectives",
        "Objective: Evaluate response", "Endpoints", "Endpoint: Response at Week 8",
        "Arms and Interventions", "Arm: Experimental; Intervention: Example drug 10 mg once daily",
        "Study Population", "Population: Adults with synthetic condition",
        "Eligibility Criteria", "Eligibility: Age 18 years or older",
    )


def template_upload() -> UploadInput:
    return UploadInput(
        "template", "template.docx", DOCX_CONTENT_TYPE,
        docx("[[SECTION:synopsis]]", "[[SECTION:objectives_endpoints]]", "[[SECTION:study_design]]", "[[SECTION:eligibility]]", "[[POC_DISCLAIMER]]"),
    )


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def context() -> TenantContext:
    return TenantContext("tenant", "actor")


@pytest.fixture
def workflow(session: Session, tmp_path: Path) -> DocumentWorkflowService:
    return DocumentWorkflowService(session, IngestService(session, LocalFileStorage(tmp_path)))


def synopsis_upload(short_title: str) -> UploadInput:
    return UploadInput("synopsis", f"{short_title}.docx", DOCX_CONTENT_TYPE, supported_synopsis(short_title))


def _accepted_passage(session: Session, ctx: TenantContext, study_id: str, section: str, fact_id: str | None) -> Passage:
    passage = Passage(tenant_id=ctx.tenant_id, study_id=study_id, section=section, status="accepted")
    session.add(passage)
    session.flush()
    version = PassageVersion(tenant_id=ctx.tenant_id, passage_id=passage.id, version=1, text="Synthetic text.", placeholders=[], is_current=True)
    session.add(version)
    session.flush()
    if fact_id is not None:
        session.add(SupportLink(tenant_id=ctx.tenant_id, passage_version_id=version.id, support_type="fact", support_id=fact_id))
    session.commit()
    return passage


def test_synopsis_replacement_supersedes_facts_and_stales_only_supported_passages(
    workflow: DocumentWorkflowService, session: Session, context: TenantContext
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    first = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    workflow.upload(context, study.id, template_upload())
    workflow.process(context, study.id, first.version_id)
    original_facts = list(session.scalars(select(Fact)))
    supported = _accepted_passage(session, context, study.id, "synopsis", original_facts[0].id)
    unrelated = _accepted_passage(session, context, study.id, "eligibility", None)
    proposed = workflow.upload(context, study.id, synopsis_upload("SYN-2"))

    outcome = workflow.confirm_replacement(
        context, study.id, "synopsis", proposed.version_id, first.version_id, 1
    )

    session.refresh(supported)
    session.refresh(unrelated)
    assert outcome.current_version_id == proposed.version_id
    assert all(fact.status == "superseded" for fact in original_facts)
    assert supported.status == "stale"
    assert unrelated.status == "accepted"
    assert {fact.status for fact in session.scalars(select(Fact))} == {"candidate", "superseded"}


def test_synopsis_replacement_extraction_failure_keeps_current_version(
    workflow: DocumentWorkflowService, session: Session, context: TenantContext
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    first = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    invalid = workflow.upload(
        context,
        study.id,
        UploadInput("synopsis", "invalid.docx", DOCX_CONTENT_TYPE, docx(
            "Study Identity", "Short title: SYN-2", "Objectives", "Objective: Evaluate response",
            "Endpoints", "Endpoint: Response at Week 8", "Arms and Interventions",
            "Arm: Experimental; Intervention: Example drug", "Study Population",
            "Population: Adults with synthetic condition", "Eligibility Criteria",
            "Eligibility: Age 18 years or older",
        )),
    )

    with pytest.raises(ReplacementValidationError):
        workflow.confirm_replacement(context, study.id, "synopsis", invalid.version_id, first.version_id, 1)

    current = session.scalar(select(StudyInput).where(StudyInput.study_id == study.id, StudyInput.role == "synopsis"))
    assert current is not None and current.current_file_version_id == first.version_id


def test_replacement_preview_names_both_versions_and_exact_effects(
    workflow: DocumentWorkflowService, session: Session, context: TenantContext
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    first = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    proposed = workflow.upload(context, study.id, synopsis_upload("SYN-2"))

    preview = workflow.preview_replacement(context, study.id, "synopsis", proposed.version_id)

    assert (preview.current_version_id, preview.current_filename, preview.current_version) == (
        first.version_id, "SYN-1.docx", 1,
    )
    assert (preview.proposed_version_id, preview.proposed_filename, preview.proposed_version) == (
        proposed.version_id, "SYN-2.docx", 2,
    )
    assert preview.effects == (
        "supersede_current_facts", "invalidate_dependent_passages", "fact_review_required",
    )


def test_replacement_preview_and_stale_confirmation_api_contract(
    workflow: DocumentWorkflowService,
    session: Session,
    context: TenantContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    first = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    proposed = workflow.upload(context, study.id, synopsis_upload("SYN-2"))
    settings = Settings(
        local_storage_path=str(tmp_path),
        allow_insecure_identity_headers=True,
        environment="test",
    )
    monkeypatch.setattr("protocol_poc.studies.routes.get_settings", lambda: settings)
    app = create_app()
    app.dependency_overrides[database_session] = lambda: session
    client = TestClient(app)
    headers = {"X-Tenant-ID": context.tenant_id, "X-Actor-ID": context.actor_id}

    preview = client.post(
        f"/api/studies/{study.id}/inputs/synopsis/replacement-preview",
        headers=headers,
        json={"proposed_version_id": proposed.version_id},
    )
    stale = client.post(
        f"/api/studies/{study.id}/inputs/synopsis/replacement-confirmation",
        headers=headers,
        json={
            "proposed_version_id": proposed.version_id,
            "expected_current_version_id": "stale-version",
            "expected_study_version": 1,
        },
    )

    assert preview.status_code == 200
    assert preview.json()["current_version_id"] == first.version_id
    assert preview.json()["proposed_filename"] == "SYN-2.docx"
    assert stale.status_code == 409
    assert stale.json() == {"detail": {"code": "STUDY_VERSION_CONFLICT"}}


def test_template_replacement_preserves_facts_and_passages_and_requires_conforming_template(
    workflow: DocumentWorkflowService, session: Session, context: TenantContext
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    synopsis = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    workflow.process(context, study.id, synopsis.version_id)
    fact = session.scalar(select(Fact))
    assert fact is not None
    passage = _accepted_passage(session, context, study.id, "synopsis", fact.id)
    first = workflow.upload(context, study.id, template_upload())
    proposed = workflow.upload(context, study.id, UploadInput("template", "template-v2.docx", DOCX_CONTENT_TYPE, docx(
        "Synthetic template version 2", "[[SECTION:synopsis]]", "[[SECTION:objectives_endpoints]]", "[[SECTION:study_design]]", "[[SECTION:eligibility]]", "[[POC_DISCLAIMER]]"
    )))

    outcome = workflow.confirm_replacement(context, study.id, "template", proposed.version_id, first.version_id, 1)

    session.refresh(fact)
    session.refresh(passage)
    assert outcome.current_version_id == proposed.version_id
    assert fact.status == "candidate"
    assert passage.status == "accepted"
    assert outcome.conformance_status == "conforming"


def test_replacement_rejects_stale_current_or_study_versions(
    workflow: DocumentWorkflowService, session: Session, context: TenantContext
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    first = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    proposed = workflow.upload(context, study.id, synopsis_upload("SYN-2"))

    with pytest.raises(StudyVersionConflict, match="version"):
        workflow.confirm_replacement(context, study.id, "synopsis", proposed.version_id, "wrong", 1)

    current = session.scalar(select(StudyInput).where(StudyInput.study_id == study.id))
    assert current is not None and current.current_file_version_id == first.version_id


def test_stale_expected_versions_win_over_invalid_or_failed_proposals(
    workflow: DocumentWorkflowService, session: Session, context: TenantContext
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    first = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    invalid_template = workflow.upload(
        context,
        study.id,
        UploadInput("template", "bad.docx", DOCX_CONTENT_TYPE, docx("[[SECTION:synopsis]]")),
    )
    assert invalid_template.status == "conformance_failed"

    with pytest.raises(StudyVersionConflict):
        workflow.confirm_replacement(
            context, study.id, "template", invalid_template.version_id, "stale", 999
        )

    session.refresh(study)
    current = session.scalar(select(StudyInput).where(StudyInput.study_id == study.id, StudyInput.role == "synopsis"))
    assert current is not None and current.current_file_version_id == first.version_id
    assert study.version == 1


def test_batch_invalidation_audit_lists_only_facts_supporting_each_passage(
    session: Session, context: TenantContext
) -> None:
    from protocol_poc.review.impact_service import ImpactService

    study = StudyService(session).create(context, "Synthetic Study")
    first = Fact(tenant_id=context.tenant_id, study_id=study.id, kind="dose", status="approved")
    second = Fact(tenant_id=context.tenant_id, study_id=study.id, kind="endpoint", status="approved")
    session.add_all([first, second])
    session.flush()
    first_passage = _accepted_passage(session, context, study.id, "synopsis", first.id)
    second_passage = _accepted_passage(session, context, study.id, "eligibility", second.id)

    ImpactService(session).invalidate_for_facts(context, [first.id, second.id])
    session.flush()
    audits = {
        event.aggregate_id: event.payload_json
        for event in session.scalars(select(AuditEvent).where(AuditEvent.event_type == "passage.invalidated"))
    }

    assert audits[first_passage.id]["fact_ids"] == [first.id]
    assert audits[second_passage.id]["fact_ids"] == [second.id]


def test_replacement_rolls_back_activation_and_invalidation_on_failure(
    workflow: DocumentWorkflowService, session: Session, context: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    study = StudyService(session).create(context, "Synthetic Study")
    first = workflow.upload(context, study.id, synopsis_upload("SYN-1"))
    workflow.process(context, study.id, first.version_id)
    old_fact = session.scalar(select(Fact))
    assert old_fact is not None
    old_fact.deferred = True
    passage = _accepted_passage(session, context, study.id, "synopsis", old_fact.id)
    proposed = workflow.upload(context, study.id, synopsis_upload("SYN-2"))
    session.refresh(study)
    initial_revision = session.scalar(select(StudyInput).where(StudyInput.study_id == study.id)).revision  # type: ignore[union-attr]
    original_append = __import__("protocol_poc.studies.document_workflow", fromlist=["AuditService"]).AuditService.append

    def fail_after_replacement_audit(self: object, *args: object, **kwargs: object) -> object:
        event = original_append(self, *args, **kwargs)
        if args[1] == "input.replacement_confirmed":
            raise RuntimeError("injected late replacement failure")
        return event

    monkeypatch.setattr("protocol_poc.studies.document_workflow.AuditService.append", fail_after_replacement_audit)
    with pytest.raises(RuntimeError, match="injected late"):
        workflow.confirm_replacement(context, study.id, "synopsis", proposed.version_id, first.version_id, 1)

    current = session.scalar(select(StudyInput).where(StudyInput.study_id == study.id))
    session.refresh(study)
    session.refresh(old_fact)
    session.refresh(passage)
    assert current is not None and current.current_file_version_id == first.version_id
    assert old_fact.status == "candidate"
    assert old_fact.deferred is True
    assert passage.status == "accepted"
    assert passage.invalidation_reason is None
    assert current.revision == initial_revision
    assert study.version == 1
    assert not session.scalars(select(ProcessingAttempt).where(ProcessingAttempt.synopsis_version_id == proposed.version_id)).all()
    assert not session.scalars(select(AuditEvent).where(AuditEvent.event_type.in_(("input.replacement_confirmed", "passage.invalidated")))).all()
