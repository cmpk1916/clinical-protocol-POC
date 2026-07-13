from hashlib import sha256

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.export.models import (
    ExportArtifactRecord,
    ExportSnapshot,
    ImmutableSnapshotError,
)


def test_export_artifact_record_is_snapshot_linked_and_immutable() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        snapshot = ExportSnapshot(tenant_id="tenant", study_id="study", study_version=1)
        session.add(snapshot)
        session.flush()
        artifact = ExportArtifactRecord(
            tenant_id="tenant",
            snapshot_id=snapshot.id,
            filename="protocol.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            renderer_version="renderer-v1",
            size_bytes=4,
            sha256_hex=sha256(b"docx").hexdigest(),
            storage_key="tenants/hash/exports/snapshot/artifact/protocol.docx",
        )
        session.add(artifact)
        session.commit()
        artifact.filename = "changed.docx"
        with pytest.raises(ImmutableSnapshotError, match="immutable"):
            session.commit()
