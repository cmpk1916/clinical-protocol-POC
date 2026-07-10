from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from protocol_poc.ai_gateway.fixture_provider import FixtureProvider
from protocol_poc.ai_gateway.service import AIGateway
from protocol_poc.db import Base
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
        session.commit()
        service = ExtractionService(session, AIGateway(FixtureProvider(response)))
        facts = service.extract(
            TenantContext("tenant-a", "writer-a"),
            "study-a",
            [EvidenceRef(id="e1", location={"kind": "paragraph", "index": 3})],
        )
        session.commit()

        assert all(fact.status == FactStatus.CANDIDATE for fact in facts)
        saved = session.scalar(select(FactVersion))
        assert saved is not None
        assert saved.source_evidence_id == "e1"
        assert session.scalar(select(Fact).where(Fact.status == "approved")) is None
