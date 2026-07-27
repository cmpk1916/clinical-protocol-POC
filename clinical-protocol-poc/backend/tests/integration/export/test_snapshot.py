import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.export.models import ExportSnapshot, ImmutableSnapshotError, SnapshotFact
from protocol_poc.export.service import ExportDenied, ExportService
from protocol_poc.drafting.models import Passage, PassageVersion
from protocol_poc.files.models import FileRecord, FileVersion, StudyInput
from protocol_poc.quality.models import QualityBlocker, QualityScorecard
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, Study
from protocol_poc.tenancy import TenantContext


class FixedQuality:
    def __init__(self, blockers: tuple[QualityBlocker, ...] = ()) -> None:
        self.blockers = blockers

    def calculate(self, ctx, study_id):
        return QualityScorecard({}, self.blockers, "blocked" if self.blockers else "eligible")


def seed_current_export_state(session: Session) -> None:
    session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study", version=1))
    for role, version_id, checksum in (
        ("synopsis", "synopsis-v1", "a" * 64),
        ("template", "template-v1", "b" * 64),
    ):
        record = FileRecord(
            id=f"{role}-file", tenant_id="tenant-a", study_id="study-a", role=role
        )
        session.add(record)
        session.add(FileVersion(
            id=version_id, tenant_id="tenant-a", file_record_id=record.id, version=1,
            display_filename=f"{role}.docx", checksum_sha256=checksum, size_bytes=1,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            storage_key=f"tenant/{role}.docx", status="succeeded",
        ))
        session.add(StudyInput(
            tenant_id="tenant-a", study_id="study-a", role=role,
            current_file_version_id=version_id, conformance_status="conforming",
        ))
    session.add(ProcessingAttempt(
        id="processing-v1", tenant_id="tenant-a", study_id="study-a",
        synopsis_version_id="synopsis-v1", extractor_name="local-rules",
        extractor_version="local-rules-v1", status="succeeded", findings_json=[],
    ))
    session.add(Fact(
        id="fact-a", tenant_id="tenant-a", study_id="study-a",
        processing_attempt_id="processing-v1", kind="dose", status="approved"
    ))
    session.add(FactVersion(
        id="fact-a-v1", tenant_id="tenant-a", fact_id="fact-a", version=1,
        value_json={"value": "10", "unit": "mg"}, is_current=True,
    ))
    for section in ("synopsis", "objectives_endpoints", "study_design", "eligibility"):
        passage = Passage(
            tenant_id="tenant-a", study_id="study-a", section=section, status="accepted"
        )
        session.add(passage)
        session.flush()
        session.add(PassageVersion(
            tenant_id="tenant-a", passage_id=passage.id, version=1,
            text="Synthetic accepted passage.", placeholders=[], is_current=True,
        ))
    session.flush()


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
        seed_current_export_state(session)
        session.commit()
        snapshot = ExportService(session, FixedQuality()).create_snapshot(
            TenantContext("tenant-a", "writer-a"), "study-a", expected_study_version=1,
            template_version_id="template-v1", template_hash="b" * 64,
        )
        session.commit()
        snapshot.renderer_version = "tampered"
        with pytest.raises(ImmutableSnapshotError):
            session.commit()


def test_authority_locks_prevent_a_second_session_from_mutating_snapshot_facts(
    tmp_path,
) -> None:
    import threading
    import time

    class BlockingQuality(FixedQuality):
        def __init__(self) -> None:
            super().__init__()
            self.authority_ready = threading.Event()
            self.release_export = threading.Event()

        def calculate(self, ctx, study_id):
            self.authority_ready.set()
            assert self.release_export.wait(timeout=5)
            return super().calculate(ctx, study_id)

    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 2},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as setup:
        seed_current_export_state(setup)
        setup.commit()

    quality = BlockingQuality()
    export_complete = threading.Event()
    update_started = threading.Event()
    update_complete = threading.Event()
    outcome: dict[str, object] = {}

    def export_in_first_session() -> None:
        with Session(engine) as first:
            snapshot = ExportService(first, quality).create_snapshot(
                TenantContext("tenant-a", "writer-a"), "study-a", expected_study_version=1,
                template_version_id="template-v1", template_hash="b" * 64,
            )
            first.commit()
            outcome["snapshot_id"] = snapshot.id
            export_complete.set()

    def mutate_in_second_session() -> None:
        with Session(engine) as second:
            update_started.set()
            second.execute(update(FactVersion).where(FactVersion.id == "fact-a-v1").values(
                value_json={"value": "20", "unit": "mg"}
            ))
            second.commit()
            update_complete.set()

    first = threading.Thread(target=export_in_first_session)
    first.start()
    assert quality.authority_ready.wait(timeout=5)
    second = threading.Thread(target=mutate_in_second_session)
    second.start()
    assert update_started.wait(timeout=5)
    time.sleep(0.1)
    assert not update_complete.is_set()
    quality.release_export.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert export_complete.is_set() and update_complete.is_set()
    with Session(engine) as verify:
        fact = verify.scalar(select(SnapshotFact).where(
            SnapshotFact.snapshot_id == outcome["snapshot_id"]
        ))
        assert fact is not None
        assert fact.value_json == {"value": "10", "unit": "mg"}
