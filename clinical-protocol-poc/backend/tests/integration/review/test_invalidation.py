from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.drafting.models import Passage, PassageVersion, SupportLink
from protocol_poc.review.fact_service import FactReviewService
from protocol_poc.studies.models import Fact, FactVersion, Study
from protocol_poc.tenancy import TenantContext


def test_fact_edit_invalidates_dependent_accepted_passage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    ctx = TenantContext("tenant-a", "writer-a")
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id=ctx.tenant_id, name="Synthetic study"))
        session.flush()
        fact = Fact(id="dose-a", tenant_id=ctx.tenant_id, study_id="study-a", kind="dose", status="approved", critical=True)
        passage = Passage(id="passage-a", tenant_id=ctx.tenant_id, study_id="study-a", section="study_design", status="accepted", current_version=1)
        session.add_all([fact, passage])
        session.flush()
        fact_version = FactVersion(tenant_id=ctx.tenant_id, fact_id=fact.id, version=1, value_json={"kind": "dose", "value": "10", "unit": "mg"}, is_current=True)
        passage_version = PassageVersion(id="pv-a", tenant_id=ctx.tenant_id, passage_id=passage.id, version=1, text="Dose is 10 mg.", placeholders=[], is_current=True)
        session.add_all([fact_version, passage_version])
        session.flush()
        session.add(SupportLink(tenant_id=ctx.tenant_id, passage_version_id=passage_version.id, support_type="fact", support_id=fact.id))
        session.commit()

        FactReviewService(session).correct_and_approve(
            ctx, fact.id, expected_version=1,
            value_json={"kind": "dose", "value": "20", "unit": "mg"},
            rationale="Updated synthetic dose", explicitly_confirmed=True,
        )
        session.commit()
        session.refresh(passage)

        assert passage.status == "stale"
        assert passage.invalidation_reason == "supporting_fact_changed"
