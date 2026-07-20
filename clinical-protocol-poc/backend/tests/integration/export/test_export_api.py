from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from protocol_poc.app import create_app
from protocol_poc.config import Settings
from protocol_poc.db import Base
import protocol_poc.export.artifact_service as artifact_service
import protocol_poc.export.service as export_service
from protocol_poc.export.artifact_service import ArtifactDescriptor, EXPECTED_FILENAMES
from protocol_poc.export.models import ExportArtifactRecord, ExportSnapshot
from protocol_poc.export.orchestration import ExportOrchestrator, ExportResult
from protocol_poc.export.routes import database_session
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.tenancy import TenantContext
from tests.integration.export.test_artifact_orchestration import seed_eligible_study


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


def test_export_api_compensates_written_artifacts_when_commit_fails(
    tmp_path: Path, monkeypatch: object
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    storage = LocalFileStorage(tmp_path)
    storage_key = "tenants/tenant-a/exports/snapshot-a/artifact-a/protocol.docx"
    content = b"synthetic artifact"

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
            snapshot = ExportSnapshot(
                id="snapshot-a", tenant_id="tenant-a", study_id="study-a", study_version=1,
                renderer_version="renderer-v1",
            )
            session.add(snapshot)
            session.flush()
            storage.put(storage_key, content)
            session.add(ExportArtifactRecord(
                id="artifact-a", tenant_id="tenant-a", snapshot_id=snapshot.id,
                filename="protocol.docx",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                renderer_version="renderer-v1", size_bytes=len(content),
                sha256_hex=sha256(content).hexdigest(), storage_key=storage_key,
            ))
            return ExportResult(
                snapshot.id,
                (ArtifactDescriptor(
                    "artifact-a", "protocol.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    sha256(content).hexdigest(), snapshot.id,
                    "/api/export-artifacts/artifact-a",
                ),),
                (storage_key,),
            )

    def fail_commit() -> None:
        from sqlalchemy.exc import OperationalError

        raise OperationalError("COMMIT", {}, RuntimeError("synthetic commit failure"))

    monkeypatch.setattr(routes, "ExportOrchestrator", FakeOrchestrator)  # type: ignore[attr-defined]
    monkeypatch.setattr(session, "commit", fail_commit)
    app = create_app()
    app.dependency_overrides[database_session] = lambda: session
    response = TestClient(app).post(
        "/api/studies/study-a/exports",
        headers=HEADERS,
        json={
            "expectedStudyVersion": 1,
            "templateVersionId": "template-v1",
            "templateHash": "a" * 64,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "EXPORT_FAILED", "blockers": ["EXPORT_FAILED"]}
    }
    assert storage.get(storage_key) is None
    assert session.scalars(select(ExportSnapshot)).all() == []
    assert session.scalars(select(ExportArtifactRecord)).all() == []
    session.close()


def test_export_api_rolls_back_real_export_without_deleting_preexisting_artifact(
    tmp_path: Path, monkeypatch: object
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    storage = LocalFileStorage(tmp_path)
    command = seed_eligible_study(session, storage)
    tenant_key = sha256(b"tenant-a").hexdigest()

    import protocol_poc.export.routes as routes

    settings = Settings(
        local_storage_path=str(tmp_path), allow_insecure_identity_headers=True,
        environment="test",
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        export_service,
        "ExportSnapshot",
        lambda **kwargs: ExportSnapshot(id="snapshot-a", **kwargs),
    )
    artifact_ids = iter(("artifact-existing", "artifact-new-1", "artifact-new-2"))
    monkeypatch.setattr(artifact_service, "new_id", lambda: next(artifact_ids))
    probe = ExportOrchestrator(session, storage, "renderer-v1").create(
        TenantContext("tenant-a", "writer"), "study-a", command
    )
    existing_key = probe.storage_keys[0]
    snapshot_id = probe.snapshot_id
    existing_content = storage.get(existing_key)
    assert existing_content is not None
    session.rollback()
    for storage_key in probe.storage_keys:
        storage.delete(storage_key)
    storage.put(existing_key, existing_content)
    artifact_ids = iter(("artifact-existing", "artifact-new-1", "artifact-new-2"))
    monkeypatch.setattr(artifact_service, "new_id", lambda: next(artifact_ids))

    commit_state = {"attempted": False}

    def fail_commit() -> None:
        from sqlalchemy.exc import OperationalError

        commit_state["attempted"] = True
        pending_artifacts = session.scalars(select(ExportArtifactRecord)).all()
        assert len(pending_artifacts) == 3
        assert {item.filename for item in pending_artifacts} == set(EXPECTED_FILENAMES)
        pending_files = {
            path.relative_to(tmp_path).as_posix()
            for path in (tmp_path / "tenants" / tenant_key / "exports").rglob("*")
            if path.is_file()
        }
        assert pending_files == {
            existing_key,
            f"tenants/{tenant_key}/exports/{snapshot_id}/artifact-new-1/traceability.csv",
            f"tenants/{tenant_key}/exports/{snapshot_id}/artifact-new-2/scorecard.html",
        }
        raise OperationalError("COMMIT", {}, RuntimeError("synthetic commit failure"))

    monkeypatch.setattr(session, "commit", fail_commit)
    app = create_app()
    app.dependency_overrides[database_session] = lambda: session
    response = TestClient(app).post(
        "/api/studies/study-a/exports",
        headers=HEADERS,
        json={
            "expectedStudyVersion": command.expected_study_version,
            "templateVersionId": command.template_version_id,
            "templateHash": command.template_hash,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "EXPORT_FAILED", "blockers": ["EXPORT_FAILED"]}
    }
    assert commit_state["attempted"]
    assert session.scalars(select(ExportSnapshot)).all() == []
    assert session.scalars(select(ExportArtifactRecord)).all() == []
    export_files = [path for path in (tmp_path / "tenants" / tenant_key / "exports").rglob("*") if path.is_file()]
    assert export_files == [tmp_path / existing_key]
    assert storage.get(existing_key) == existing_content
    session.close()
