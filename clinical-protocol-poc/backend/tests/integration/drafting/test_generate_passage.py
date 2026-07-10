from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from protocol_poc.ai_gateway.fixture_provider import FixtureProvider
from protocol_poc.ai_gateway.service import AIGateway
from protocol_poc.db import Base
from protocol_poc.drafting.service import DraftingService
from protocol_poc.studies.models import Study
from protocol_poc.tenancy import TenantContext


def test_missing_required_fact_becomes_placeholder_not_guess() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.commit()
        service = DraftingService(session, AIGateway(FixtureProvider({"text": "must not be used"})))

        result = service.generate(TenantContext("tenant-a", "writer-a"), "study-a", section="study_design")

        assert "[[REQUIRED: intervention dose]]" in result.text
        assert result.status == "blocked"


def test_all_scoped_sections_are_allowlisted() -> None:
    assert DraftingService.SCOPED_SECTIONS == {
        "synopsis", "objectives_endpoints", "study_design", "eligibility"
    }
