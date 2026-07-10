from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.guidance.models import GuidanceChunk, GuidanceRelease, GuidanceSource
from protocol_poc.guidance.service import GuidanceService


def test_retrieval_returns_only_active_release() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = GuidanceSource(id="source-a", tenant_id="tenant-a", name="Synthetic guidance")
        session.add(source)
        session.flush()
        session.add_all([
            GuidanceRelease(id="draft", tenant_id="tenant-a", source_id=source.id, version="1", state="draft"),
            GuidanceRelease(id="active", tenant_id="tenant-a", source_id=source.id, version="2", state="active"),
        ])
        session.flush()
        session.add_all([
            GuidanceChunk(id="draft-chunk", tenant_id="tenant-a", release_id="draft", section="eligibility", location="p1", content="Eligibility draft", content_hash="a" * 64, applicability_tags=["eligibility"]),
            GuidanceChunk(id="active-chunk", tenant_id="tenant-a", release_id="active", section="eligibility", location="p2", content="Eligibility approved active", content_hash="b" * 64, applicability_tags=["eligibility"]),
        ])
        session.commit()

        service = GuidanceService(session)
        service.rebuild_index("tenant-a")
        results = service.search("eligibility", tenant_id="tenant-a")

        assert results
        assert {result.release_id for result in results} == {"active"}
