from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.export.artifact_service import EXPECTED_FILENAMES, ExportArtifactRepository
from protocol_poc.export.orchestration import ExportCommand, ExportOrchestrator
from protocol_poc.export.service import ExportDenied
from protocol_poc.export.models import ExportArtifactRecord, ExportSnapshot
from protocol_poc.files.models import FileRecord, FileVersion, StudyInput
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.drafting.models import Passage, PassageVersion, SupportLink
from protocol_poc.quality.models import DimensionResult, QualityScorecard
from protocol_poc.rendering.artifact_service import ArtifactService
from protocol_poc.rendering.docx_renderer import RenderSnapshot
from protocol_poc.rendering.template_map import build_template
from protocol_poc.tenancy import TenantContext
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, Study


def card() -> QualityScorecard:
    return QualityScorecard(
        {
            name: DimensionResult("pass", 1, 1)
            for name in (
                "completeness",
                "consistency",
                "traceability",
                "template_conformance",
                "writer_review_status",
                "approved_guidance_coverage",
            )
        },
        (),
        "eligible",
    )


def test_repository_persists_and_reads_exact_tenant_scoped_artifacts(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        snapshot = ExportSnapshot(
            tenant_id="tenant-a",
            study_id="study-a",
            study_version=1,
            renderer_version="renderer-v1",
        )
        session.add(snapshot)
        session.flush()
        rendered = ArtifactService("renderer-v1").create(
            RenderSnapshot(snapshot.id, {"study_design": "Synthetic passage."}),
            card(),
            build_template(["study_design"]),
        )
        repository = ExportArtifactRepository(session, LocalFileStorage(tmp_path))
        descriptors = repository.persist(TenantContext("tenant-a", "writer"), snapshot, rendered)
        session.commit()

        assert [item.name for item in descriptors] == [
            "protocol.docx",
            "traceability.csv",
            "scorecard.html",
        ]
        assert {item.snapshot_id for item in descriptors} == {snapshot.id}
        assert len(session.scalars(select(ExportArtifactRecord)).all()) == 3
        for descriptor, expected in zip(descriptors, rendered, strict=True):
            record, content = repository.get(
                TenantContext("tenant-a", "writer"), descriptor.id
            )
            assert record.sha256_hex == descriptor.sha256 == expected.sha256_hex
            assert content == expected.content
            with pytest.raises(LookupError, match="not found"):
                repository.get(TenantContext("tenant-b", "writer"), descriptor.id)


def test_repository_cleans_written_objects_when_a_later_write_fails(tmp_path: Path) -> None:
    class FailSecondWrite(LocalFileStorage):
        calls = 0

        def put(self, key: str, data: bytes) -> bool:
            self.calls += 1
            if self.calls == 2:
                raise OSError("storage unavailable")
            return super().put(key, data)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        snapshot = ExportSnapshot(
            tenant_id="tenant-a", study_id="study-a", study_version=1,
            renderer_version="renderer-v1",
        )
        session.add(snapshot)
        session.flush()
        rendered = ArtifactService("renderer-v1").create(
            RenderSnapshot(snapshot.id, {"study_design": "Synthetic passage."}),
            card(),
            build_template(["study_design"]),
        )
        with pytest.raises(OSError, match="unavailable"):
            ExportArtifactRepository(session, FailSecondWrite(tmp_path)).persist(
                TenantContext("tenant-a", "writer"), snapshot, rendered
            )
        session.rollback()
        assert list(tmp_path.rglob("*.*")) == []
        assert session.scalars(select(ExportArtifactRecord)).all() == []


def seed_eligible_study(session: Session, storage: LocalFileStorage) -> ExportCommand:
    session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study", version=1))
    session.add(Fact(
        id="fact-dose", tenant_id="tenant-a", study_id="study-a", kind="dose",
        status="approved", critical=True,
    ))
    session.add(FactVersion(
        id="fact-dose-v1", tenant_id="tenant-a", fact_id="fact-dose", version=1,
        value_json={"value": "10", "unit": "mg"}, is_current=True,
    ))
    for section in ("synopsis", "objectives_endpoints", "study_design", "eligibility"):
        passage_id = f"passage-{section}"
        version_id = f"version-{section}"
        session.add(Passage(
            id=passage_id, tenant_id="tenant-a", study_id="study-a",
            section=section, status="accepted",
        ))
        session.add(PassageVersion(
            id=version_id, tenant_id="tenant-a", passage_id=passage_id, version=1,
            text=f"Synthetic accepted {section} passage.", placeholders=[], is_current=True,
        ))
        session.add(SupportLink(
            tenant_id="tenant-a", passage_version_id=version_id,
            support_type="fact", support_id="fact-dose",
        ))
    template = build_template([
        "synopsis", "objectives_endpoints", "study_design", "eligibility",
    ])
    template_hash = __import__("hashlib").sha256(template).hexdigest()
    storage_key = "tenants/template/source.docx"
    storage.put(storage_key, template)
    session.add(FileRecord(
        id="template-file", tenant_id="tenant-a", study_id="study-a", role="template",
    ))
    session.add(FileVersion(
        id="template-v1", tenant_id="tenant-a", file_record_id="template-file", version=1,
        display_filename="template.docx", checksum_sha256=template_hash,
        size_bytes=len(template),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        storage_key=storage_key, status="succeeded",
    ))
    synopsis_key = "tenants/synopsis/source.docx"
    storage.put(synopsis_key, template)
    session.add(FileRecord(
        id="synopsis-file", tenant_id="tenant-a", study_id="study-a", role="synopsis",
    ))
    session.add(FileVersion(
        id="synopsis-v1", tenant_id="tenant-a", file_record_id="synopsis-file", version=1,
        display_filename="synopsis.docx", checksum_sha256=template_hash,
        size_bytes=len(template),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        storage_key=synopsis_key, status="succeeded",
    ))
    session.add_all([
        StudyInput(
            tenant_id="tenant-a", study_id="study-a", role="template",
            current_file_version_id="template-v1", conformance_status="conforming",
        ),
        StudyInput(
            tenant_id="tenant-a", study_id="study-a", role="synopsis",
            current_file_version_id="synopsis-v1", conformance_status="conforming",
        ),
        ProcessingAttempt(
            id="processing-v1", tenant_id="tenant-a", study_id="study-a",
            synopsis_version_id="synopsis-v1", extractor_name="local-rules",
            extractor_version="local-rules-v1", status="succeeded", findings_json=[],
        ),
    ])
    session.commit()
    return ExportCommand(1, "template-v1", template_hash)


def test_orchestrator_creates_exact_artifact_set_from_validated_snapshot(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFileStorage(tmp_path)
    with Session(engine) as session:
        command = seed_eligible_study(session, storage)
        result = ExportOrchestrator(session, storage, "renderer-v1").create(
            TenantContext("tenant-a", "writer"), "study-a", command
        )
        session.commit()
        assert [item.name for item in result.artifacts] == list(EXPECTED_FILENAMES)
        assert {item.snapshot_id for item in result.artifacts} == {result.snapshot_id}
        assert len(session.scalars(select(ExportArtifactRecord)).all()) == 3


@pytest.mark.parametrize(
    ("version_id", "template_hash", "expected"),
    [
        ("missing", "0" * 64, "TEMPLATE_VERSION_INVALID"),
        ("template-v1", "0" * 64, "TEMPLATE_HASH_MISMATCH"),
    ],
)
def test_orchestrator_fails_closed_for_invalid_template(
    tmp_path: Path, version_id: str, template_hash: str, expected: str
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFileStorage(tmp_path)
    with Session(engine) as session:
        seed_eligible_study(session, storage)
        with pytest.raises(ExportDenied) as captured:
            ExportOrchestrator(session, storage, "renderer-v1").create(
                TenantContext("tenant-a", "writer"), "study-a",
                ExportCommand(1, version_id, template_hash),
            )
        assert captured.value.codes == (expected,)
        session.rollback()
        assert session.scalars(select(ExportArtifactRecord)).all() == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("archive", "STUDY_ARCHIVED"),
        ("unprocessed_synopsis", "INPUT_PROCESSING_INCOMPLETE"),
        ("candidate_fact", "FACT_REVIEW_INCOMPLETE"),
        ("stale_passage", "STALE_PASSAGE"),
        ("noncurrent_template", "TEMPLATE_VERSION_INVALID"),
    ],
)
def test_orchestrator_rechecks_current_workspace_authority_before_export(
    tmp_path: Path, change: str, expected: str
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalFileStorage(tmp_path)
    with Session(engine) as session:
        command = seed_eligible_study(session, storage)
        study = session.get(Study, "study-a")
        assert study is not None
        if change == "archive":
            study.lifecycle = "archived"
        elif change == "unprocessed_synopsis":
            current = session.scalar(select(StudyInput).where(StudyInput.role == "synopsis"))
            assert current is not None
            current.current_file_version_id = "template-v1"
        elif change == "candidate_fact":
            fact = session.get(Fact, "fact-dose")
            assert fact is not None
            fact.status = "candidate"
        elif change == "stale_passage":
            passage = session.get(Passage, "passage-eligibility")
            assert passage is not None
            passage.status = "stale"
        else:
            current = session.scalar(select(StudyInput).where(StudyInput.role == "template"))
            assert current is not None
            current.current_file_version_id = "synopsis-v1"
        session.commit()

        with pytest.raises(ExportDenied) as captured:
            ExportOrchestrator(session, storage, "renderer-v1").create(
                TenantContext("tenant-a", "writer"), "study-a", command
            )

        assert expected in captured.value.codes
        session.rollback()
        assert session.scalars(select(ExportArtifactRecord)).all() == []
