from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from protocol_poc.app import create_app
from protocol_poc.config import Settings
from protocol_poc.db import Base
from protocol_poc.export.artifact_service import ArtifactDescriptor
from protocol_poc.export.models import ExportArtifactRecord, ExportSnapshot
from protocol_poc.export.orchestration import ExportResult
from protocol_poc.export.routes import database_session
from protocol_poc.files.service import LocalFileStorage


HEADERS = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer"}


def test_export_api_returns_descriptors_and_downloads_exact_bytes(
    tmp_path: Path, monkeypatch: object
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    content = b"exact artifact bytes"
    storage = LocalFileStorage(tmp_path)
    storage_key = "tenant/export/protocol.docx"
    storage.put(storage_key, content)
    snapshot = ExportSnapshot(
        id="snapshot-a", tenant_id="tenant-a", study_id="study-a", study_version=1,
        renderer_version="renderer-v1",
    )
    artifact = ExportArtifactRecord(
        id="artifact-a", tenant_id="tenant-a", snapshot_id="snapshot-a",
        filename="protocol.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        renderer_version="renderer-v1", size_bytes=len(content),
        sha256_hex=sha256(content).hexdigest(), storage_key=storage_key,
    )
    session.add_all([snapshot, artifact])
    session.commit()

    import protocol_poc.export.routes as routes

    settings = Settings(
        local_storage_path=str(tmp_path), allow_insecure_identity_headers=True,
        environment="test",
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)  # type: ignore[attr-defined]

    class FakeOrchestrator:
        def __init__(self, *args: object) -> None:
            pass

        def create(self, *args: object) -> ExportResult:
            return ExportResult("snapshot-a", (
                ArtifactDescriptor(
                    "artifact-a", "protocol.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    sha256(content).hexdigest(), "snapshot-a",
                    "/api/export-artifacts/artifact-a",
                ),
            ))

    monkeypatch.setattr(routes, "ExportOrchestrator", FakeOrchestrator)  # type: ignore[attr-defined]
    app = create_app()
    app.dependency_overrides[database_session] = lambda: session
    client = TestClient(app)

    response = client.post(
        "/api/studies/study-a/exports",
        headers=HEADERS,
        json={
            "expectedStudyVersion": 1,
            "templateVersionId": "template-v1",
            "templateHash": "a" * 64,
        },
    )
    assert response.status_code == 201
    assert response.json() == {
        "snapshotId": "snapshot-a",
        "blockers": [],
        "artifacts": [{
            "id": "artifact-a",
            "name": "protocol.docx",
            "mediaType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "sha256": sha256(content).hexdigest(),
            "snapshotId": "snapshot-a",
            "downloadUrl": "/api/export-artifacts/artifact-a",
        }],
    }
    download = client.get("/api/export-artifacts/artifact-a", headers=HEADERS)
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-disposition"] == 'attachment; filename="protocol.docx"'

    hidden = client.get(
        "/api/export-artifacts/artifact-a",
        headers={"X-Tenant-ID": "tenant-b", "X-Actor-ID": "writer"},
    )
    assert hidden.status_code == 404
    session.close()
