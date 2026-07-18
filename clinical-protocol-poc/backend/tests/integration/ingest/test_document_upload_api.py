from collections.abc import Iterator
from io import BytesIO
import hashlib
import hmac
from pathlib import Path
import time
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from protocol_poc.app import create_app
from protocol_poc.config import Settings
from protocol_poc.db import Base
from protocol_poc.files.models import IngestJob, StudyInput
from protocol_poc.identity import canonical_identity
from protocol_poc.ingest.routes import database_session
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext


DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def docx(*paragraphs: str) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>" for paragraph in paragraphs
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


def supported_template() -> bytes:
    return docx(
        "[[SECTION:synopsis]]",
        "[[SECTION:objectives_endpoints]]",
        "[[SECTION:study_design]]",
        "[[SECTION:eligibility]]",
        "[[POC_DISCLAIMER]]",
    )


def synopsis_without_dose() -> bytes:
    return docx(
        "Study Identity", "Short title: SYN-1", "Objectives",
        "Objective: Evaluate response", "Endpoints", "Endpoint: Response at Week 8",
        "Arms and Interventions", "Arm: Experimental; Intervention: Example drug",
        "Study Population", "Population: Adults with synthetic condition",
        "Eligibility Criteria", "Eligibility: Age 18 years or older",
    )


def signed_headers(settings: Settings, tenant: str = "tenant") -> dict[str, str]:
    timestamp = str(int(time.time()))
    actor = f"actor-{tenant}"
    signature = hmac.new(
        settings.identity_hmac_secret.encode(),
        canonical_identity(tenant, actor, timestamp),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Tenant-ID": tenant,
        "X-Actor-ID": actor,
        "X-Identity-Timestamp": timestamp,
        "X-Identity-Signature": signature,
    }


@pytest.fixture
def upload_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Session, Settings]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    app = create_app()
    app.dependency_overrides[database_session] = lambda: session
    import protocol_poc.ingest.routes as routes

    settings = Settings(local_storage_path=str(tmp_path), identity_hmac_secret="test-secret")
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    yield TestClient(app), session, settings
    session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("role", "content"),
    (("synopsis", supported_synopsis()), ("template", supported_template())),
    ids=("synopsis", "template"),
)
def test_first_valid_supported_input_is_activated(
    upload_api: tuple[TestClient, Session, Settings], role: str, content: bytes
) -> None:
    client, session, settings = upload_api
    study = StudyService(session).create(TenantContext("tenant", "actor-tenant"), "Synthetic Study")

    response = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=signed_headers(settings),
        data={"role": role},
        files={"file": ("source.docx", content, DOCX_CONTENT_TYPE)},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "activated"
    assert response.json()["current_file_version_id"] == response.json()["version_id"]
    assert response.json()["findings"] == []
    current = session.scalar(select(StudyInput).where(StudyInput.role == role))
    assert current is not None
    assert current.current_file_version_id == response.json()["version_id"]


def test_invalid_contract_reports_findings_without_activation(
    upload_api: tuple[TestClient, Session, Settings],
) -> None:
    client, session, settings = upload_api
    study = StudyService(session).create(TenantContext("tenant", "actor-tenant"), "Synthetic Study")

    response = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=signed_headers(settings),
        data={"role": "synopsis"},
        files={
            "file": (
                "source.docx",
                docx("Study Identity", "Short title: SYN-1"),
                DOCX_CONTENT_TYPE,
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "conformance_failed"
    assert {finding["field"] for finding in response.json()["findings"]} == {
        "objectives",
        "endpoints",
        "arms_interventions",
        "population",
        "eligibility",
    }
    assert response.json()["current_file_version_id"] is None
    assert session.scalar(select(StudyInput)) is None


def test_identical_version_is_reused_and_later_replacement_is_only_previewed(
    upload_api: tuple[TestClient, Session, Settings],
) -> None:
    client, session, settings = upload_api
    study = StudyService(session).create(TenantContext("tenant", "actor-tenant"), "Synthetic Study")
    headers = signed_headers(settings)
    first_file = {"file": ("source.docx", supported_synopsis(), DOCX_CONTENT_TYPE)}

    first = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=headers,
        data={"role": "synopsis"},
        files=first_file,
    )
    same = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=headers,
        data={"role": "synopsis"},
        files=first_file,
    )
    changed = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=headers,
        data={"role": "synopsis"},
        files={
            "file": (
                "source.docx",
                supported_synopsis("SYN-2"),
                DOCX_CONTENT_TYPE,
            )
        },
    )

    assert first.status_code == same.status_code == changed.status_code == 201
    assert same.json()["version_id"] == first.json()["version_id"]
    assert same.json()["status"] == "activated"
    assert changed.json()["version"] == 2
    assert changed.json()["status"] == "replacement_confirmation_required"
    assert changed.json()["current_file_version_id"] == first.json()["version_id"]
    current = session.scalar(select(StudyInput))
    assert current is not None
    assert (current.current_file_version_id, current.revision) == (
        first.json()["version_id"],
        1,
    )


def test_archived_study_is_rejected_before_ingest(
    upload_api: tuple[TestClient, Session, Settings],
) -> None:
    client, session, settings = upload_api
    ctx = TenantContext("tenant", "actor-tenant")
    studies = StudyService(session)
    study = studies.create(ctx, "Synthetic Study")
    studies.archive(ctx, study.id, expected_version=1)

    response = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=signed_headers(settings),
        data={"role": "synopsis"},
        files={"file": ("source.docx", supported_synopsis(), DOCX_CONTENT_TYPE)},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STUDY_ARCHIVED"
    assert session.scalar(select(IngestJob)) is None


@pytest.mark.parametrize("study_id", ["missing", "cross-tenant"])
def test_missing_and_cross_tenant_studies_are_hidden(
    upload_api: tuple[TestClient, Session, Settings], study_id: str
) -> None:
    client, session, settings = upload_api
    if study_id == "cross-tenant":
        study_id = (
            StudyService(session)
            .create(TenantContext("tenant-a", "actor-a"), "Other Tenant Study")
            .id
        )

    response = client.post(
        f"/api/studies/{study_id}/inputs",
        headers=signed_headers(settings, "tenant-b"),
        data={"role": "synopsis"},
        files={"file": ("source.docx", supported_synopsis(), DOCX_CONTENT_TYPE)},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "STUDY_NOT_FOUND"
    assert session.scalar(select(IngestJob)) is None


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "status_code", "error_code"),
    (
        ("bad.txt", "text/plain", b"text", 422, "INVALID_UPLOAD"),
        ("bad.docx", DOCX_CONTENT_TYPE, b"not a zip", 400, "UNSAFE_DOCUMENT"),
    ),
    ids=("validation", "unsafe-document"),
)
def test_ingest_errors_have_stable_responses(
    upload_api: tuple[TestClient, Session, Settings],
    filename: str,
    content_type: str,
    content: bytes,
    status_code: int,
    error_code: str,
) -> None:
    client, session, settings = upload_api
    study = StudyService(session).create(TenantContext("tenant", "actor-tenant"), "Synthetic Study")

    response = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=signed_headers(settings),
        data={"role": "synopsis"},
        files={"file": (filename, content, content_type)},
    )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == error_code


def test_process_and_retry_routes_use_local_extractor_only(
    upload_api: tuple[TestClient, Session, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, session, settings = upload_api
    study = StudyService(session).create(
        TenantContext("tenant", "actor-tenant"), "Synthetic Study"
    )
    headers = signed_headers(settings)
    uploaded = client.post(
        f"/api/studies/{study.id}/inputs",
        headers=headers,
        data={"role": "synopsis"},
        files={
            "file": (
                "source.docx",
                synopsis_without_dose(),
                DOCX_CONTENT_TYPE,
            )
        },
    )
    # The assertion below guards against accidental reintroduction of the legacy gateway.
    monkeypatch.setattr(
        "protocol_poc.ai_gateway.service.AIGateway.run",
        lambda *_args, **_kwargs: pytest.fail("self-service processing called AIGateway"),
    )

    processed = client.post(
        f"/api/studies/{study.id}/inputs/{uploaded.json()['version_id']}/process",
        headers=headers,
    )
    retried = client.post(
        f"/api/studies/{study.id}/processing-attempts/{processed.json()['attempt_id']}/retry",
        headers=headers,
    )

    assert processed.status_code == retried.status_code == 200
    assert processed.json()["status"] == retried.json()["status"] == "failed"
    assert processed.json()["attempt_id"] != retried.json()["attempt_id"]
    assert processed.json()["findings"][0]["code"] == "SYNOPSIS_DOSE_MISSING"
