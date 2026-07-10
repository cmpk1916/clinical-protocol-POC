from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.drafting.models import Passage, PassageVersion
from protocol_poc.quality.service import QualityService
from protocol_poc.studies.models import Study
from protocol_poc.tenancy import TenantContext


def test_scorecard_has_dimensions_and_no_composite() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.commit()
        card = QualityService(session).calculate(TenantContext("tenant-a", "writer-a"), "study-a")
        assert set(card.dimensions) == {
            "completeness", "consistency", "traceability", "template_conformance",
            "writer_review_status", "approved_guidance_coverage",
        }
        assert not hasattr(card, "overall_score")
        assert card.export_status == "blocked"


def test_required_placeholder_is_hard_blocker() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        passage = Passage(id="p1", tenant_id="tenant-a", study_id="study-a", section="study_design", status="blocked", current_version=1)
        session.add(passage)
        session.flush()
        session.add(PassageVersion(tenant_id="tenant-a", passage_id="p1", version=1, text="[[REQUIRED: intervention dose]]", placeholders=["intervention dose"], is_current=True))
        session.commit()
        card = QualityService(session).calculate(TenantContext("tenant-a", "writer-a"), "study-a")
        assert "REQUIRED_PLACEHOLDER" in {blocker.code for blocker in card.blockers}
