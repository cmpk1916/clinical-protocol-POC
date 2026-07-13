from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, JSON, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, Session, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class ImmutableSnapshotError(RuntimeError):
    pass


class ExportSnapshot(Base):
    __tablename__ = "export_snapshots"
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_version: Mapped[int] = mapped_column(nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class _SnapshotRow:
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)


def _snapshot_fk(name: str) -> tuple[ForeignKeyConstraint]:
    return (ForeignKeyConstraint(["snapshot_id"], ["export_snapshots.id"], name=f"fk_{name}_snapshot"),)


class SnapshotFact(_SnapshotRow, Base):
    __tablename__ = "snapshot_facts"
    __table_args__ = _snapshot_fk("snapshot_fact")
    source_fact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[int] = mapped_column(nullable=False)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SnapshotPassage(_SnapshotRow, Base):
    __tablename__ = "snapshot_passages"
    __table_args__ = _snapshot_fk("snapshot_passage")
    source_passage_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[int] = mapped_column(nullable=False)
    section: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    review_state: Mapped[str] = mapped_column(String(32), nullable=False)


class SnapshotGuidance(_SnapshotRow, Base):
    __tablename__ = "snapshot_guidance"
    __table_args__ = _snapshot_fk("snapshot_guidance")
    guidance_id: Mapped[str] = mapped_column(String(128), nullable=False)
    release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SnapshotTemplate(_SnapshotRow, Base):
    __tablename__ = "snapshot_templates"
    __table_args__ = _snapshot_fk("snapshot_template")
    template_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SnapshotFinding(_SnapshotRow, Base):
    __tablename__ = "snapshot_findings"
    __table_args__ = _snapshot_fk("snapshot_finding")
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)


class ExportArtifactRecord(_SnapshotRow, Base):
    __tablename__ = "export_artifacts"
    __table_args__ = (
        *_snapshot_fk("export_artifact"),
        UniqueConstraint(
            "tenant_id", "snapshot_id", "filename",
            name="uq_export_artifact_snapshot_filename",
        ),
        UniqueConstraint("storage_key", name="uq_export_artifact_storage_key"),
        CheckConstraint(
            "filename IN ('protocol.docx','traceability.csv','scorecard.html')",
            name="ck_export_artifact_filename",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_export_artifact_size"),
        CheckConstraint(
            "length(sha256_hex) = 64 AND lower(sha256_hex) = sha256_hex",
            name="ck_export_artifact_sha256",
        ),
    )
    filename: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


SNAPSHOT_TYPES = (
    ExportSnapshot,
    SnapshotFact,
    SnapshotPassage,
    SnapshotGuidance,
    SnapshotTemplate,
    SnapshotFinding,
    ExportArtifactRecord,
)


@event.listens_for(Session, "before_flush")
def _deny_snapshot_mutation(session: Session, *_: object) -> None:
    for instance in session.dirty.union(session.deleted):
        if isinstance(instance, SNAPSHOT_TYPES) and inspect(instance).persistent:  # type: ignore[attr-defined]
            raise ImmutableSnapshotError("export snapshots are immutable")
