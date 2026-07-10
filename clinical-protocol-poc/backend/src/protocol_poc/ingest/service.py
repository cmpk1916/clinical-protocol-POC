from dataclasses import asdict, dataclass
import hashlib
from pathlib import PurePath
import threading

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.common.ids import new_id
from protocol_poc.files.models import CleanupTask, FileRecord, FileVersion, IngestJob, SourceEvidence, now
from protocol_poc.files.service import FileStorage, IndeterminateWriteError
from protocol_poc.ingest.docx_parser import DocxParser, UnsafeDocumentError
from protocol_poc.tenancy import TenantContext, require_tenant_context


DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
@dataclass(slots=True)
class _ScopeLockEntry:
    lock: threading.Lock
    users: int = 0


_scope_locks: dict[str, _ScopeLockEntry] = {}
_scope_locks_guard = threading.Lock()


def _acquire_scope_lock(scope: str) -> _ScopeLockEntry:
    with _scope_locks_guard:
        entry = _scope_locks.setdefault(scope, _ScopeLockEntry(threading.Lock()))
        entry.users += 1
    entry.lock.acquire()
    return entry


def _release_scope_lock(scope: str, entry: _ScopeLockEntry) -> None:
    entry.lock.release()
    with _scope_locks_guard:
        entry.users -= 1
        if entry.users == 0 and _scope_locks.get(scope) is entry:
            del _scope_locks[scope]


def scope_lock_registry_size() -> int:
    with _scope_locks_guard:
        return len(_scope_locks)


def acquire_database_scope_lock(session: Session, scope: str) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    lock_key = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})


@dataclass(frozen=True, slots=True)
class UploadInput:
    role: str
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class IngestResult:
    job_id: str
    file_id: str
    version_id: str
    version: int
    checksum_sha256: str
    status: str = "succeeded"


class UploadValidationError(ValueError):
    pass


class IngestService:
    def __init__(self, session: Session, storage: FileStorage, parser: DocxParser | None = None) -> None:
        self._session, self._storage = session, storage
        self._parser = parser or DocxParser()

    def ingest(self, ctx: TenantContext, study_id: str, upload: UploadInput) -> IngestResult:
        context = require_tenant_context(ctx)
        if not study_id.strip() or upload.role not in {"synopsis", "template"}:
            raise UploadValidationError("invalid study or role")
        job = IngestJob(tenant_id=context.tenant_id, study_id=study_id, role=upload.role, status="pending")
        self._session.add(job)
        self._session.commit()
        checksum = hashlib.sha256(upload.content).hexdigest()
        written_key: str | None = None
        scope = f"{context.tenant_id}\0{study_id}\0{upload.role}"
        scope_lock = _acquire_scope_lock(scope)
        try:
            job.status = "processing"
            acquire_database_scope_lock(self._session, scope)
            if not upload.filename.lower().endswith(".docx") or upload.content_type != DOCX_CONTENT_TYPE:
                raise UploadValidationError("only DOCX files are accepted")
            evidence = self._parser.parse(upload.content)
            record = self._session.scalar(select(FileRecord).where(FileRecord.tenant_id == context.tenant_id, FileRecord.study_id == study_id, FileRecord.role == upload.role))
            if record is not None:
                existing = self._session.scalar(select(FileVersion).where(FileVersion.file_record_id == record.id, FileVersion.checksum_sha256 == checksum))
                if existing is not None:
                    job.status, job.file_version_id = "succeeded", existing.id
                    AuditService(self._session).append(context, "input.ingest_succeeded", "file", record.id, {"file_version_id": existing.id, "checksum_sha256": checksum, "status": "succeeded", "idempotent": True})
                    self._session.commit()
                    return IngestResult(job.id, record.id, existing.id, existing.version, checksum)
            if record is None:
                record = FileRecord(tenant_id=context.tenant_id, study_id=study_id, role=upload.role)
                self._session.add(record)
                self._session.flush()
            version_number = (self._session.scalar(select(func.max(FileVersion.version)).where(FileVersion.file_record_id == record.id)) or 0) + 1
            version_id = new_id()
            tenant_key = hashlib.sha256(context.tenant_id.encode()).hexdigest()
            key = f"tenants/{tenant_key}/files/{record.id}/versions/{version_id}.docx"
            if self._storage.put(key, upload.content):
                written_key = key
            version = FileVersion(id=version_id, tenant_id=context.tenant_id, file_record_id=record.id, version=version_number, display_filename=self._safe_filename(upload.filename), checksum_sha256=checksum, size_bytes=len(upload.content), content_type=DOCX_CONTENT_TYPE, storage_key=key, status="succeeded")
            self._session.add(version)
            for ordinal, item in enumerate(evidence):
                self._session.add(SourceEvidence(tenant_id=context.tenant_id, file_version_id=version.id, ordinal=ordinal, location_json=asdict(item.location), text=item.text, text_sha256=hashlib.sha256(item.text.encode()).hexdigest()))
            job.status, job.file_version_id = "succeeded", version.id
            AuditService(self._session).append(context, "input.ingest_succeeded", "file", record.id, {"file_version_id": version.id, "checksum_sha256": checksum, "status": "succeeded"})
            self._session.commit()
            return IngestResult(job.id, record.id, version.id, version.version, checksum)
        except Exception as exc:
            self._session.rollback()
            cleanup_status = "not_needed"
            cleanup_key = written_key
            if isinstance(exc, IndeterminateWriteError):
                cleanup_key = exc.key
                cleanup_status = "reconciliation_required"
            elif written_key is not None:
                try:
                    self._storage.delete(written_key)
                    cleanup_status = "deleted"
                except Exception:
                    cleanup_status = "failed"
            failed_job = self._session.get(IngestJob, job.id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.error_code = self._error_code(exc)
                AuditService(self._session).append(context, "input.ingest_failed", "ingest_job", failed_job.id, {"status": "failed", "error_code": failed_job.error_code, "checksum_sha256": checksum, "cleanup_status": cleanup_status})
                if cleanup_status in {"failed", "reconciliation_required"} and cleanup_key is not None:
                    self._session.add(CleanupTask(tenant_id=context.tenant_id, ingest_job_id=failed_job.id, storage_key=cleanup_key, checksum_sha256=checksum, status="pending"))
                self._session.commit()
            raise
        finally:
            _release_scope_lock(scope, scope_lock)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        value = PurePath(filename.replace("\\", "/")).name.strip()
        return (value or "document.docx")[:255]

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if isinstance(exc, UnsafeDocumentError):
            return "unsafe_document"
        if isinstance(exc, UploadValidationError):
            return "invalid_upload"
        if isinstance(exc, IndeterminateWriteError):
            return "indeterminate_storage_write"
        return "ingest_failed"


class CleanupService:
    def __init__(self, session: Session, storage: FileStorage) -> None:
        self._session, self._storage = session, storage

    def retry(self, ctx: TenantContext, task_id: str) -> CleanupTask:
        context = require_tenant_context(ctx)
        task = self._session.scalar(select(CleanupTask).where(CleanupTask.id == task_id, CleanupTask.tenant_id == context.tenant_id))
        if task is None:
            raise LookupError("cleanup task not found")
        if task.status == "succeeded":
            return task
        try:
            existing_checksum = self._storage.object_checksum(task.storage_key)
            if existing_checksum is not None:
                if existing_checksum != task.checksum_sha256:
                    raise FileExistsError("cleanup object checksum mismatch")
                self._storage.delete(task.storage_key)
        except Exception:
            self._session.rollback()
            failed_task = self._session.scalar(select(CleanupTask).where(CleanupTask.id == task_id, CleanupTask.tenant_id == context.tenant_id))
            if failed_task is not None:
                failed_task.attempts += 1
                failed_task.last_attempt_at = now()
                self._session.commit()
            raise
        task.attempts += 1
        task.last_attempt_at = now()
        task.status = "succeeded"
        AuditService(self._session).append(context, "input.cleanup_succeeded", "cleanup_task", task.id, {"status": "succeeded", "checksum_sha256": task.checksum_sha256})
        self._session.commit()
        return task
