from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.drafting.context import DraftContextBuilder
from protocol_poc.studies.models import Fact, FactVersion, Study
from protocol_poc.tenancy import TenantContext


def test_context_contains_only_approved_current_facts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        session.add_all([
            Fact(id="approved", tenant_id="tenant-a", study_id="study-a", kind="endpoint", status="approved"),
            Fact(id="candidate", tenant_id="tenant-a", study_id="study-a", kind="endpoint", status="candidate"),
        ])
        session.flush()
        session.add_all([
            FactVersion(tenant_id="tenant-a", fact_id="approved", version=1, value_json={"value": "HbA1c"}, is_current=True),
            FactVersion(tenant_id="tenant-a", fact_id="candidate", version=1, value_json={"value": "Weight"}, is_current=True),
        ])
        session.commit()

        context = DraftContextBuilder(session).for_section(TenantContext("tenant-a", "writer-a"), "study-a", "objectives_endpoints")

        assert "approved" in context.fact_ids
        assert "candidate" not in context.fact_ids
