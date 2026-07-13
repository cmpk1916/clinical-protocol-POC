from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.common.ids import new_id
from protocol_poc.export.models import ExportArtifactRecord, ExportSnapshot
from protocol_poc.files.service import FileStorage
from protocol_poc.rendering.artifact_service import Artifact
from protocol_poc.tenancy import TenantContext, require_tenant_context


EXPECTED_FILENAMES = ("protocol.docx", "traceability.csv", "scorecard.html")


@dataclass(frozen=True)
class ArtifactDescriptor:
    id: str
    name: str
    media_type: str
    sha256: str
    snapshot_id: str
    download_url: str


class ExportArtifactRepository:
    def __init__(self, session: Session, storage: FileStorage) -> None:
        self._session = session
        self._storage = storage

    def persist(
        self,
        ctx: TenantContext,
        snapshot: ExportSnapshot,
        artifacts: list[Artifact],
    ) -> tuple[ArtifactDescriptor, ...]:
        context = require_tenant_context(ctx)
        if snapshot.tenant_id != context.tenant_id:
            raise LookupError("snapshot not found")
        filenames = tuple(item.filename for item in artifacts)
        if filenames != EXPECTED_FILENAMES:
            raise ValueError("export must contain the exact three artifact files")
        tenant_key = sha256(context.tenant_id.encode()).hexdigest()
        written_keys: list[str] = []
        descriptors: list[ArtifactDescriptor] = []
        try:
            for item in artifacts:
                if not item.verify_integrity():
                    raise ValueError("rendered artifact hash mismatch")
                artifact_id = new_id()
                storage_key = (
                    f"tenants/{tenant_key}/exports/{snapshot.id}/"
                    f"{artifact_id}/{item.filename}"
                )
                if self._storage.put(storage_key, item.content):
                    written_keys.append(storage_key)
                stored_checksum = self._storage.object_checksum(storage_key)
                if stored_checksum != item.sha256_hex:
                    raise OSError("stored artifact hash mismatch")
                record = ExportArtifactRecord(
                    id=artifact_id,
                    tenant_id=context.tenant_id,
                    snapshot_id=snapshot.id,
                    filename=item.filename,
                    media_type=item.media_type,
                    renderer_version=item.renderer_version,
                    size_bytes=len(item.content),
                    sha256_hex=item.sha256_hex,
                    storage_key=storage_key,
                )
                self._session.add(record)
                descriptors.append(self._descriptor(record))
            self._session.flush()
        except Exception:
            for storage_key in reversed(written_keys):
                try:
                    self._storage.delete(storage_key)
                except Exception:
                    pass
            raise
        return tuple(descriptors)

    def get(
        self,
        ctx: TenantContext,
        artifact_id: str,
    ) -> tuple[ExportArtifactRecord, bytes]:
        context = require_tenant_context(ctx)
        record = self._session.scalar(
            select(ExportArtifactRecord).where(
                ExportArtifactRecord.id == artifact_id,
                ExportArtifactRecord.tenant_id == context.tenant_id,
            )
        )
        if record is None:
            raise LookupError("export artifact not found")
        content = self._storage.get(record.storage_key)
        if content is None:
            raise LookupError("export artifact not found")
        if len(content) != record.size_bytes or sha256(content).hexdigest() != record.sha256_hex:
            raise OSError("export artifact integrity check failed")
        return record, content

    @staticmethod
    def _descriptor(record: ExportArtifactRecord) -> ArtifactDescriptor:
        return ArtifactDescriptor(
            id=record.id,
            name=record.filename,
            media_type=record.media_type,
            sha256=record.sha256_hex,
            snapshot_id=record.snapshot_id,
            download_url=f"/api/export-artifacts/{record.id}",
        )
