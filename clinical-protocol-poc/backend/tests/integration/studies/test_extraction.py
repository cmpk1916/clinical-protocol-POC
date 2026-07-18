from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from protocol_poc.ai_gateway.fixture_provider import FixtureProvider
from protocol_poc.ai_gateway.service import AIGateway
from protocol_poc.db import Base
from protocol_poc.files.models import FileRecord, FileVersion, SourceEvidence
from protocol_poc.studies.enums import FactStatus
from protocol_poc.studies.extraction_service import EvidenceRef, ExtractionService
from protocol_poc.studies.models import Fact, FactVersion, Study
from protocol_poc.tenancy import TenantContext


def test_extracted_candidate_is_never_approved() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    response = {
        "candidates": [{
            "kind": "dose",
            "value": {"kind": "dose", "value": "10", "unit": "mg"},
            "source_evidence_id": "e1",
            "source_location": {"kind": "paragraph", "index": 3},
            "critical": True,
            "confidence": 0.93,
        }]
    }
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.add(
            FileRecord(
                id="file-a",
                tenant_id="tenant-a",
                study_id="study-a",
                role="synopsis",
            )
        )
        session.flush()
        session.add(
            FileVersion(
                id="version-a",
                tenant_id="tenant-a",
                file_record_id="file-a",
                version=1,
                display_filename="synopsis.docx",
                checksum_sha256="a" * 64,
                size_bytes=1,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                storage_key="tenant/version-a.docx",
                status="succeeded",
            )
        )
        session.flush()
        session.add(
            SourceEvidence(
                id="e1",
                tenant_id="tenant-a",
                file_version_id="version-a",
                ordinal=0,
                location_json={"kind": "paragraph", "index": 3},
                text="Synthetic dose evidence",
                text_sha256="b" * 64,
            )
        )
        session.commit()
        service = ExtractionService(session, AIGateway(FixtureProvider(response)))
        facts = service.extract(
            TenantContext("tenant-a", "writer-a"),
            "study-a",
            [
                EvidenceRef(
                    id="e1",
                    version_id="version-a",
                    location={"kind": "paragraph", "index": 3},
                )
            ],
        )
        session.commit()

        assert all(fact.status == FactStatus.CANDIDATE for fact in facts)
        saved = session.scalar(select(FactVersion))
        assert saved is not None
        assert saved.source_evidence_id == "e1"
        assert saved.source_evidence_version_id == "version-a"
        assert session.scalar(select(Fact).where(Fact.status == "approved")) is None
