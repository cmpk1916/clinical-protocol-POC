import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.drafting.models import Passage, PassageVersion
from protocol_poc.drafting.review_service import PassageBlocked, PassageReviewService, PassageVersionConflict
from protocol_poc.studies.models import Study
from protocol_poc.tenancy import TenantContext


def test_passage_with_blocker_cannot_be_accepted() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        passage = Passage(id="passage-a", tenant_id="tenant-a", study_id="study-a", section="study_design", status="blocked", current_version=1)
        session.add(passage)
        session.flush()
        session.add(PassageVersion(tenant_id="tenant-a", passage_id=passage.id, version=1, text="[[REQUIRED: intervention dose]]", placeholders=["intervention dose"], is_current=True))
        session.commit()

        with pytest.raises(PassageBlocked):
            PassageReviewService(session).accept(TenantContext("tenant-a", "writer-a"), passage.id, expected_version=1)


def test_reject_requires_current_passage_version() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        passage = Passage(id="passage-a", tenant_id="tenant-a", study_id="study-a", section="study_design", status="ready_for_review", current_version=2)
        session.add(passage)
        session.flush()
        session.add(PassageVersion(tenant_id="tenant-a", passage_id=passage.id, version=2, text="Arm A receives Synthetic Intervention A, 10 mg once daily, for 24 weeks.", placeholders=[], is_current=True))
        session.commit()

        with pytest.raises(PassageVersionConflict):
            PassageReviewService(session).reject(TenantContext("tenant-a", "writer-a"), passage.id, expected_version=1, rationale="Synthetic rejection")


def test_database_rejects_multiple_current_passage_versions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.add(Passage(
            id="passage-a", tenant_id="tenant-a", study_id="study-a",
            section="study_design", status="draft", current_version=2,
        ))
        session.add_all([
            PassageVersion(
                id="version-a", tenant_id="tenant-a", passage_id="passage-a", version=1,
                text="Synthetic version one.", placeholders=[], is_current=True,
            ),
            PassageVersion(
                id="version-b", tenant_id="tenant-a", passage_id="passage-a", version=2,
                text="Synthetic version two.", placeholders=[], is_current=True,
            ),
        ])

        with pytest.raises(IntegrityError):
            session.commit()
