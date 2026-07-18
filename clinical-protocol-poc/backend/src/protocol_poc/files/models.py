from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Delete, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, Update, event, inspect
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class FileRecord(Base):
    __tablename__ = "file_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "study_id", "role", name="uq_file_record_identity"),
        UniqueConstraint("id", "tenant_id", name="uq_file_record_id_tenant"),
        CheckConstraint("role IN ('synopsis', 'template')", name="ck_file_record_role"),
    )
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("file_record_id", "version", name="uq_file_version_number"),
        UniqueConstraint("file_record_id", "checksum_sha256", name="uq_file_version_checksum"),
        UniqueConstraint("id", "tenant_id", name="uq_file_version_id_tenant"),
        ForeignKeyConstraint(["file_record_id", "tenant_id"], ["file_records.id", "file_records.tenant_id"], name="fk_file_version_record_tenant"),
        CheckConstraint("status IN ('succeeded')", name="ck_file_version_status"),
        CheckConstraint("version > 0", name="ck_file_version_positive"),
        CheckConstraint("size_bytes >= 0", name="ck_file_version_size"),
        CheckConstraint("length(checksum_sha256) = 64 AND lower(checksum_sha256) = checksum_sha256", name="ck_file_version_checksum_format"),
        Index("ix_file_versions_tenant_record", "tenant_id", "file_record_id"),
    )
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    file_record_id: Mapped[str] = mapped_column(String(26), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StudyInput(Base):
    __tablename__ = "study_inputs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "study_id", "role", name="uq_study_input_role"),
        UniqueConstraint("id", "tenant_id", name="uq_study_input_id_tenant"),
        ForeignKeyConstraint(
            ["study_id", "tenant_id"],
            ["studies.id", "studies.tenant_id"],
            name="fk_study_input_study_tenant",
        ),
        ForeignKeyConstraint(
            ["current_file_version_id", "tenant_id"],
            ["file_versions.id", "file_versions.tenant_id"],
            name="fk_study_input_version_tenant",
        ),
        CheckConstraint("role IN ('synopsis', 'template')", name="ck_study_input_role"),
        CheckConstraint(
            "conformance_status IN ('conforming')",
            name="ck_study_input_conformance_status",
        ),
        CheckConstraint("revision > 0", name="ck_study_input_revision_positive"),
        Index("ix_study_inputs_tenant_study", "tenant_id", "study_id"),
    )
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    current_file_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    conformance_status: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SourceEvidence(Base):
    __tablename__ = "source_evidence"
    __table_args__ = (
        UniqueConstraint("file_version_id", "ordinal", name="uq_source_evidence_version_ordinal"),
        ForeignKeyConstraint(["file_version_id", "tenant_id"], ["file_versions.id", "file_versions.tenant_id"], name="fk_evidence_version_tenant"),
        Index("ix_source_evidence_tenant_version", "tenant_id", "file_version_id"),
        CheckConstraint("ordinal >= 0", name="ck_source_evidence_ordinal"),
        CheckConstraint("length(text_sha256) = 64 AND lower(text_sha256) = text_sha256", name="ck_source_evidence_checksum_format"),
    )
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    file_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    location_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class IngestJob(Base):
    __tablename__ = "ingest_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["file_version_id", "tenant_id"], ["file_versions.id", "file_versions.tenant_id"], name="fk_ingest_job_version_tenant"),
        CheckConstraint("role IN ('synopsis', 'template')", name="ck_ingest_job_role"),
        CheckConstraint("status IN ('pending', 'processing', 'succeeded', 'failed')", name="ck_ingest_job_status"),
        UniqueConstraint("id", "tenant_id", name="uq_ingest_job_id_tenant"),
        Index("ix_ingest_jobs_tenant_study", "tenant_id", "study_id"),
    )
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    file_version_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CleanupTask(Base):
    __tablename__ = "cleanup_tasks"
    __table_args__ = (
        ForeignKeyConstraint(["ingest_job_id", "tenant_id"], ["ingest_jobs.id", "ingest_jobs.tenant_id"], name="fk_cleanup_job_tenant"),
        CheckConstraint("status IN ('pending', 'succeeded')", name="ck_cleanup_task_status"),
        CheckConstraint("attempts >= 0", name="ck_cleanup_task_attempts"),
        CheckConstraint("length(checksum_sha256) = 64 AND lower(checksum_sha256) = checksum_sha256", name="ck_cleanup_task_checksum_format"),
        Index("ix_cleanup_tasks_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ingest_job_id: Mapped[str] = mapped_column(String(26), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ImmutableFileVersionError(RuntimeError):
    """Raised when an immutable persisted file version is mutated."""


@event.listens_for(Session, "before_flush")
def _prevent_file_version_mutation(session: Session, *_: object) -> None:
    for instance in session.dirty.union(session.deleted):
        if isinstance(instance, FileVersion) and inspect(instance).persistent:
            raise ImmutableFileVersionError("file versions are immutable")


@event.listens_for(Session, "do_orm_execute")
def _prevent_bulk_file_version_mutation(state: ORMExecuteState) -> None:
    statement = state.statement
    if isinstance(statement, (Update, Delete)) and getattr(statement.table, "name", None) == FileVersion.__tablename__:
        raise ImmutableFileVersionError("file versions are immutable")
