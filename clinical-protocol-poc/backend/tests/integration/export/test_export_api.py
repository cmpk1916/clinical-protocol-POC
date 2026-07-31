from datetime import datetime, timezone
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
from protocol_poc.studies.models import Study
from protocol_poc.tenancy import TenantContext
from tests.integration.export.test_artifact_orchestration import seed_eligible_study


HEADERS = {"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer"}


def _export_api_client(
    session: Session,
    tmp_path: Path,
    monkeypatch: object,
) -> TestClient:
    import protocol_poc.export.routes as routes

    settings = Settings(
        local_storage_path=str(tmp_path), allow_insecure_identity_headers=True,
        environment="test",
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)  # type: ignore[attr-defined]
    app = create_app()
    app.dependency_overrides[database_session] = lambda: session
    return TestClient(app)


def _artifact(
    *,
    artifact_id: str,
    snapshot_id: str,
    filename: str,
    media_type: str,
    sha256_hex: str,
) -> ExportArtifactRecord:
    return ExportArtifactRecord(
        id=artifact_id,
        tenant_id="tenant-a",
        snapshot_id=snapshot_id,
        filename=filename,
        media_type=media_type,
        renderer_version="renderer-v1",
        size_bytes=1,
        sha256_hex=sha256_hex,
        storage_key=f"exports/{snapshot_id}/{artifact_id}/{filename}",
    )


def test_latest_export_api_returns_newest_complete_snapshot_in_contract_order(
    tmp_path: Path, monkeypatch: object
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Study(id="study-a", tenant_id="tenant-a", name="Study A"))
    session.add_all([
        ExportSnapshot(
            id="snapshot-old", tenant_id="tenant-a", study_id="study-a",
            study_version=1, renderer_version="renderer-v1",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        ExportSnapshot(
            id="snapshot-new", tenant_id="tenant-a", study_id="study-a",
            study_version=2, renderer_version="renderer-v1",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    ])
    session.flush()
    session.add_all([
        _artifact(
            artifact_id="new-scorecard", snapshot_id="snapshot-new",
            filename="scorecard.html", media_type="text/html", sha256_hex="3" * 64,
        ),
        _artifact(
            artifact_id="new-protocol", snapshot_id="snapshot-new",
            filename="protocol.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            sha256_hex="1" * 64,
        ),
        _artifact(
            artifact_id="new-traceability", snapshot_id="snapshot-new",
            filename="traceability.csv", media_type="text/csv", sha256_hex="2" * 64,
        ),
    ])
    session.commit()

    response = _export_api_client(session, tmp_path, monkeypatch).get(
        "/api/studies/study-a/exports/latest", headers=HEADERS
    )

    assert response.status_code == 200
    assert response.json() == {
        "snapshotId": "snapshot-new",
        "blockers": [],
        "artifacts": [
            {
                "id": "new-protocol",
                "name": "protocol.docx",
                "mediaType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "sha256": "1" * 64,
                "snapshotId": "snapshot-new",
                "downloadUrl": "/api/export-artifacts/new-protocol",
            },
            {
                "id": "new-traceability",
                "name": "traceability.csv",
                "mediaType": "text/csv",
                "sha256": "2" * 64,
                "snapshotId": "snapshot-new",
                "downloadUrl": "/api/export-artifacts/new-traceability",
            },
            {
                "id": "new-scorecard",
                "name": "scorecard.html",
                "mediaType": "text/html",
                "sha256": "3" * 64,
                "snapshotId": "snapshot-new",
                "downloadUrl": "/api/export-artifacts/new-scorecard",
            },
        ],
    }
    session.close()


def test_latest_export_api_returns_empty_state_for_existing_study_without_export(
    tmp_path: Path, monkeypatch: object
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Study(id="study-empty", tenant_id="tenant-a", name="Empty Study"))
    session.commit()

    response = _export_api_client(session, tmp_path, monkeypatch).get(
        "/api/studies/study-empty/exports/latest", headers=HEADERS
    )

    assert response.status_code == 200
    assert response.json() == {"snapshotId": None, "blockers": [], "artifacts": []}
    session.close()


def test_latest_export_api_hides_missing_and_cross_tenant_studies(
    tmp_path: Path, monkeypatch: object
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Study(id="study-a", tenant_id="tenant-a", name="Study A"))
    session.commit()
    client = _export_api_client(session, tmp_path, monkeypatch)

    missing = client.get("/api/studies/missing/exports/latest", headers=HEADERS)
    hidden = client.get(
        "/api/studies/study-a/exports/latest",
        headers={"X-Tenant-ID": "tenant-b", "X-Actor-ID": "writer"},
    )

    assert missing.status_code == 404
    assert missing.json() == {"detail": {"code": "STUDY_NOT_FOUND"}}
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": {"code": "STUDY_NOT_FOUND"}}
    session.close()


def test_latest_export_api_fails_closed_for_incomplete_latest_snapshot(
    tmp_path: Path, monkeypatch: object
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Study(id="study-partial", tenant_id="tenant-a", name="Partial Study"))
    session.add(ExportSnapshot(
        id="snapshot-partial", tenant_id="tenant-a", study_id="study-partial",
        study_version=1, renderer_version="renderer-v1",
    ))
    session.flush()
    session.add(_artifact(
        artifact_id="partial-protocol", snapshot_id="snapshot-partial",
        filename="protocol.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256_hex="4" * 64,
    ))
    session.commit()

    response = _export_api_client(session, tmp_path, monkeypatch).get(
        "/api/studies/study-partial/exports/latest", headers=HEADERS
    )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "EXPORT_INTEGRITY_FAILED"}}
    session.close()


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
