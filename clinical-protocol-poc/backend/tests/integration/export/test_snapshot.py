import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.export.models import ExportSnapshot, ImmutableSnapshotError
from protocol_poc.export.service import ExportDenied, ExportService
from protocol_poc.quality.models import QualityBlocker, QualityScorecard
from protocol_poc.studies.models import Study
from protocol_poc.tenancy import TenantContext


class FixedQuality:
    def __init__(self, blockers: tuple[QualityBlocker, ...] = ()) -> None:
        self.blockers = blockers

    def calculate(self, ctx, study_id):
        return QualityScorecard({}, self.blockers, "blocked" if self.blockers else "eligible")


def test_denied_attempt_creates_no_snapshot() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.commit()
        with pytest.raises(ExportDenied):
            ExportService(session, FixedQuality((QualityBlocker("STALE_PASSAGE", "stale"),))).create_snapshot(
                TenantContext("tenant-a", "writer-a"), "study-a", expected_study_version=1,
                template_version_id="template-v1", template_hash="a" * 64,
            )
        session.commit()
        assert session.scalar(select(ExportSnapshot)) is None


def test_snapshot_is_immutable_and_version_locked() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study", version=1))
        session.commit()
        snapshot = ExportService(session, FixedQuality()).create_snapshot(
            TenantContext("tenant-a", "writer-a"), "study-a", expected_study_version=1,
            template_version_id="template-v1", template_hash="a" * 64,
        )
        session.commit()
        snapshot.renderer_version = "tampered"
        with pytest.raises(ImmutableSnapshotError):
            session.commit()
