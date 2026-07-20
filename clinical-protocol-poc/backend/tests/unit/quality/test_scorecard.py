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


def test_completeness_requires_the_exact_four_governed_sections() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        session.add(Passage(
            id="p1", tenant_id="tenant-a", study_id="study-a", section="study_design",
            status="ready_for_review", current_version=1,
        ))
        session.flush()
        session.add(PassageVersion(
            tenant_id="tenant-a", passage_id="p1", version=1,
            text="Arm A receives Synthetic Intervention A, 10 mg once daily, for 24 weeks.",
            placeholders=[], is_current=True,
        ))
        session.commit()

        card = QualityService(session).calculate(TenantContext("tenant-a", "writer-a"), "study-a")

        assert card.dimensions["completeness"].status == "blocked"
        assert card.dimensions["completeness"].passed_count == 1
        assert card.dimensions["completeness"].applicable_count == 4
        assert {blocker.code for blocker in card.blockers} >= {"REQUIRED_SECTION_MISSING"}


def test_completeness_fails_closed_for_legacy_duplicate_sections() -> None:
    passages = [
        Passage(id="p1", tenant_id="tenant-a", study_id="study-a", section="study_design", status="ready_for_review", current_version=1),
        Passage(id="p2", tenant_id="tenant-a", study_id="study-a", section="study_design", status="ready_for_review", current_version=1),
    ]

    class LegacySession:
        def scalars(self, statement):  # type: ignore[no-untyped-def]
            entity = statement.column_descriptions[0]["entity"]
            return iter(passages if entity is Passage else [])

    card = QualityService(LegacySession()).calculate(TenantContext("tenant-a", "writer-a"), "study-a")  # type: ignore[arg-type]

    assert card.dimensions["completeness"].status == "blocked"
    assert "DUPLICATE_SECTION" in {blocker.code for blocker in card.blockers}
