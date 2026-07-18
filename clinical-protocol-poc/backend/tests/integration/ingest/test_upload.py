from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
from pathlib import Path
import time
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from protocol_poc.audit.models import AuditEvent
from protocol_poc.app import create_app
from protocol_poc.db import Base
from protocol_poc.files.models import CleanupTask, FileRecord, FileVersion, ImmutableFileVersionError, SourceEvidence
from protocol_poc.files.models import IngestJob
from protocol_poc.files.service import IndeterminateWriteError, LocalFileStorage
from protocol_poc.ingest.service import CleanupService, IngestService, UploadInput, acquire_database_scope_lock, scope_lock_registry_size
from protocol_poc.ingest.routes import database_session
from protocol_poc.config import Settings
from protocol_poc.identity import canonical_identity
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext


def docx(text: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", b'''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>''')
        package.writestr("_rels/.rels", b'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>''')
        package.writestr("word/document.xml", f'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'''.encode())
    return output.getvalue()


def test_upload_api_requires_explicit_tenant_context() -> None:
    response = TestClient(create_app()).post("/api/studies/study/inputs")
    assert response.status_code == 401


def test_real_multipart_upload_is_idempotent_and_versions(tmp_path: Path, monkeypatch: object) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    app = create_app()
    app.dependency_overrides[database_session] = lambda: session
    import protocol_poc.ingest.routes as routes
    settings = Settings(local_storage_path=str(tmp_path), identity_hmac_secret="test-secret")
    monkeypatch.setattr(routes, "get_settings", lambda: settings)  # type: ignore[attr-defined]
    client = TestClient(app)
    study_id = StudyService(session).create(
        TenantContext("tenant", "actor"), "Synthetic Study"
    ).id
    timestamp = str(int(time.time()))
    signature = hmac.new(b"test-secret", canonical_identity("tenant", "actor", timestamp), hashlib.sha256).hexdigest()
    headers = {"X-Tenant-ID": "tenant", "X-Actor-ID": "actor", "X-Identity-Timestamp": timestamp, "X-Identity-Signature": signature}
    files = {"file": ("source.docx", docx("first"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    first = client.post(f"/api/studies/{study_id}/inputs", headers=headers, data={"role": "synopsis"}, files=files)
    same = client.post(f"/api/studies/{study_id}/inputs", headers=headers, data={"role": "synopsis"}, files=files)
    changed = client.post(f"/api/studies/{study_id}/inputs", headers=headers, data={"role": "synopsis"}, files={"file": ("source.docx", docx("second"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert first.status_code == 201
    assert same.json()["version_id"] == first.json()["version_id"]
    assert changed.json()["version"] == 2
    rejected = client.post(f"/api/studies/{study_id}/inputs", headers=headers, data={"role": "template"}, files={"file": ("bad.txt", b"text", "text/plain")})
    assert rejected.status_code == 422
    assert session.scalar(select(IngestJob).where(IngestJob.role == "template")).status == "failed"  # type: ignore[union-attr]
    session.close()


def test_identity_spoof_and_replay_are_rejected(tmp_path: Path, monkeypatch: object) -> None:
    app = create_app()
    import protocol_poc.ingest.routes as routes
    settings = Settings(local_storage_path=str(tmp_path), identity_hmac_secret="secret", identity_replay_window_seconds=30)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)  # type: ignore[attr-defined]
    client = TestClient(app)
    now = str(int(time.time()))
    invalid = {"X-Tenant-ID": "victim", "X-Actor-ID": "attacker", "X-Identity-Timestamp": now, "X-Identity-Signature": "0" * 64}
    assert client.post("/api/studies/s/inputs", headers=invalid).status_code == 401
    old = str(int(time.time()) - 60)
    old_signature = hmac.new(b"secret", canonical_identity("tenant", "actor", old), hashlib.sha256).hexdigest()
    replay = {"X-Tenant-ID": "tenant", "X-Actor-ID": "actor", "X-Identity-Timestamp": old, "X-Identity-Signature": old_signature}
    assert client.post("/api/studies/s/inputs", headers=replay).status_code == 401


def test_idempotent_versions_tenant_isolation_and_audit_has_no_text(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = IngestService(session, LocalFileStorage(tmp_path))
        first = service.ingest(TenantContext("t1", "a1"), "study", UploadInput("synopsis", "source.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("SECRET CLINICAL TEXT")))
        same = service.ingest(TenantContext("t1", "a1"), "study", UploadInput("synopsis", "other.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("SECRET CLINICAL TEXT")))
        second = service.ingest(TenantContext("t1", "a1"), "study", UploadInput("synopsis", "source.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("changed")))
        isolated = service.ingest(TenantContext("t2", "a2"), "study", UploadInput("synopsis", "source.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("SECRET CLINICAL TEXT")))
        other_study = service.ingest(TenantContext("t1", "a1"), "other-study", UploadInput("synopsis", "../unsafe.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("SECRET CLINICAL TEXT")))
        other_role = service.ingest(TenantContext("t1", "a1"), "study", UploadInput("template", "source.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("SECRET CLINICAL TEXT")))

        assert first.version_id == same.version_id
        assert second.version == 2
        assert isolated.version_id != first.version_id
        assert len({first.version_id, isolated.version_id, other_study.version_id, other_role.version_id}) == 4
        assert len(session.scalars(select(FileVersion)).all()) == 5
        assert len(session.scalars(select(SourceEvidence)).all()) == 5
        unsafe_version = session.get(FileVersion, other_study.version_id)
        assert unsafe_version is not None and unsafe_version.display_filename == "unsafe.docx"
        assert "unsafe.docx" not in unsafe_version.storage_key and ".." not in unsafe_version.storage_key
        assert len(session.scalars(select(FileRecord)).all()) == 4
        payloads = [str(event.payload_json) for event in session.scalars(select(AuditEvent))]
        assert all("SECRET CLINICAL TEXT" not in payload for payload in payloads)


def test_unsafe_upload_leaves_durable_failed_job_without_version(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = IngestService(session, LocalFileStorage(tmp_path))
        try:
            service.ingest(TenantContext("t1", "a1"), "study", UploadInput("synopsis", "source.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"not a zip"))
        except ValueError:
            pass
        job = session.scalar(select(IngestJob))
        assert job is not None
        assert (job.status, job.error_code) == ("failed", "unsafe_document")
        assert session.scalars(select(FileVersion)).all() == []


def test_file_versions_are_immutable(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = IngestService(session, LocalFileStorage(tmp_path)).ingest(TenantContext("t", "a"), "s", UploadInput("synopsis", "x.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("x")))
        version = session.get(FileVersion, result.version_id)
        assert version is not None
        version.status = "failed"
        with pytest.raises(ImmutableFileVersionError):
            session.commit()
        session.rollback()
        with pytest.raises(ImmutableFileVersionError):
            session.execute(update(FileVersion).values(status="failed"))


def test_db_failure_cleans_object_and_persists_sanitized_failure_audit(tmp_path: Path) -> None:
    class FailSecondCommitSession(Session):
        commits = 0

        def commit(self) -> None:
            self.commits += 1
            if self.commits == 2:
                raise RuntimeError("sensitive database details")
            super().commit()

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with FailSecondCommitSession(engine) as session:
        with pytest.raises(RuntimeError):
            IngestService(session, LocalFileStorage(tmp_path)).ingest(TenantContext("t", "a"), "s", UploadInput("synopsis", "x.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("clinical secret")))
        assert list(tmp_path.rglob("*.docx")) == []
        assert session.scalars(select(FileVersion)).all() == []
        job = session.scalar(select(IngestJob))
        assert job is not None and (job.status, job.error_code) == ("failed", "ingest_failed")
        event = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "input.ingest_failed"))
        assert event is not None
        payload = str(event.payload_json)
        assert "clinical secret" not in payload and "sensitive database details" not in payload


def test_failed_cleanup_persists_outbox_and_retry_is_idempotent(tmp_path: Path) -> None:
    class FailSecondCommitSession(Session):
        commits = 0

        def commit(self) -> None:
            self.commits += 1
            if self.commits == 2:
                raise RuntimeError("db")
            super().commit()

    class DeleteFails(LocalFileStorage):
        def delete(self, key: str) -> None:
            raise OSError("storage credential detail")

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with FailSecondCommitSession(engine) as session:
        with pytest.raises(RuntimeError):
            IngestService(session, DeleteFails(tmp_path)).ingest(TenantContext("t", "a"), "s", UploadInput("synopsis", "x.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx("secret")))
        task = session.scalar(select(CleanupTask))
        assert task is not None and task.status == "pending" and task.attempts == 0
        assert "secret" not in str(task.storage_key)
        class HeadFails(LocalFileStorage):
            def object_checksum(self, key: str) -> str | None:
                raise OSError("provider detail")

        with pytest.raises(OSError):
            CleanupService(session, HeadFails(tmp_path)).retry(TenantContext("t", "a"), task.id)
        session.expire_all()
        assert session.get(CleanupTask, task.id).attempts == 1  # type: ignore[union-attr]
        retried = CleanupService(session, LocalFileStorage(tmp_path)).retry(TenantContext("t", "a"), task.id)
        assert retried.status == "succeeded" and retried.attempts == 2
        assert CleanupService(session, LocalFileStorage(tmp_path)).retry(TenantContext("t", "a"), task.id).attempts == 2
        assert list(tmp_path.rglob("*.docx")) == []


def test_concurrent_uploads_converge_or_allocate_distinct_versions(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'concurrent.db'}", connect_args={"timeout": 10})
    Base.metadata.create_all(engine)

    def upload(text_value: str) -> tuple[str, int]:
        with Session(engine) as session:
            result = IngestService(session, LocalFileStorage(tmp_path / "objects")).ingest(TenantContext("tenant", "actor"), "study", UploadInput("synopsis", "x.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx(text_value)))
            return result.version_id, result.version

    with ThreadPoolExecutor(max_workers=2) as executor:
        identical = list(executor.map(upload, ["same", "same"]))
    assert identical[0][0] == identical[1][0]
    with ThreadPoolExecutor(max_workers=2) as executor:
        different = list(executor.map(upload, ["different-a", "different-b"]))
    assert {version for _, version in different} == {2, 3}
    assert scope_lock_registry_size() == 0


def test_scope_lock_registry_does_not_leak_many_keys(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = IngestService(session, LocalFileStorage(tmp_path))
        for index in range(100):
            service.ingest(TenantContext("tenant", "actor"), f"study-{index}", UploadInput("synopsis", "x.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx(str(index))))
    assert scope_lock_registry_size() == 0


def test_indeterminate_storage_write_persists_reconciliation_task(tmp_path: Path) -> None:
    class IndeterminateStorage(LocalFileStorage):
        def put(self, key: str, data: bytes) -> bool:
            raise IndeterminateWriteError(key, hashlib.sha256(data).hexdigest())

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        content = docx("secret")
        with pytest.raises(IndeterminateWriteError):
            IngestService(session, IndeterminateStorage(tmp_path)).ingest(TenantContext("t", "a"), "s", UploadInput("synopsis", "x.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", content))
        task = session.scalar(select(CleanupTask))
        job = session.scalar(select(IngestJob))
        assert task is not None and task.checksum_sha256 == hashlib.sha256(content).hexdigest()
        assert job is not None and job.error_code == "indeterminate_storage_write"


def test_postgres_uses_transaction_scoped_advisory_lock() -> None:
    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class FakeSession:
        captured: tuple[str, dict[str, int]] | None = None

        def get_bind(self) -> Bind:
            return Bind()

        def execute(self, statement: object, parameters: dict[str, int]) -> None:
            self.captured = (str(statement), parameters)

    session = FakeSession()
    acquire_database_scope_lock(session, "tenant\0study\0synopsis")  # type: ignore[arg-type]
    assert session.captured is not None
    assert session.captured[0] == "SELECT pg_advisory_xact_lock(:key)"
    assert -(2**63) <= session.captured[1]["key"] < 2**63
