from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.files.models import FileVersion, SourceEvidence, StudyInput
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.ingest.service import DOCX_CONTENT_TYPE, IngestService, UploadInput
from protocol_poc.studies.document_workflow import DocumentWorkflowService
from protocol_poc.studies.service import StudyArchived, StudyService
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
