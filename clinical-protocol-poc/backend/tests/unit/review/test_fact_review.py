import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from protocol_poc.audit.models import AuditEvent
from protocol_poc.db import Base
from protocol_poc.review.fact_service import ExplicitConfirmationRequired, FactReviewService, UnresolvedConflict
from protocol_poc.studies.service import StudyArchived
from protocol_poc.studies.models import Fact, FactVersion, Study
from protocol_poc.tenancy import TenantContext


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.commit()
        yield session


def add_fact(session: Session, *, fact_id: str, status: str = "candidate", critical: bool = False) -> Fact:
    fact = Fact(id=fact_id, tenant_id="tenant-a", study_id="study-a", kind="dose", status=status, critical=critical)
    session.add_all([fact, FactVersion(tenant_id="tenant-a", fact_id=fact_id, version=1, value_json={"value": "10 mg"}, is_current=True)])
    session.commit()
    return fact


def test_critical_fact_requires_explicit_confirmation(session: Session) -> None:
    fact = add_fact(session, fact_id="critical", critical=True)
    with pytest.raises(ExplicitConfirmationRequired):
        FactReviewService(session).approve(TenantContext("tenant-a", "writer-a"), fact.id, expected_version=1, explicitly_confirmed=False)


def test_conflicting_candidate_cannot_be_approved(session: Session) -> None:
    fact = add_fact(session, fact_id="conflict", status="conflicted")
    with pytest.raises(UnresolvedConflict):
        FactReviewService(session).approve(TenantContext("tenant-a", "writer-a"), fact.id, expected_version=1, explicitly_confirmed=True)


def test_correction_supersedes_version_and_appends_audit(session: Session) -> None:
    fact = add_fact(session, fact_id="correct-me")
    result = FactReviewService(session).correct_and_approve(
        TenantContext("tenant-a", "writer-a"), fact.id, expected_version=1,
        value_json={"kind": "dose", "value": "12", "unit": "mg"}, rationale="Source correction",
        explicitly_confirmed=True,
    )
    session.commit()

    versions = list(session.scalars(select(FactVersion).where(FactVersion.fact_id == fact.id).order_by(FactVersion.version)))
    assert result.status == "approved"
    assert [version.is_current for version in versions] == [False, True]
    assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "fact.corrected_and_approved")) is not None


def test_archived_guard_precedes_fact_version_validation(session: Session) -> None:
    fact = add_fact(session, fact_id="archived")
    study = session.get(Study, "study-a")
    assert study is not None
    study.lifecycle = "archived"
    session.commit()

    with pytest.raises(StudyArchived):
        FactReviewService(session).approve(
            TenantContext("tenant-a", "writer-a"),
            fact.id,
            expected_version=999,
            explicitly_confirmed=True,
        )


def test_deferred_fact_remains_visible_and_can_be_resumed(session: Session) -> None:
    fact = add_fact(session, fact_id="deferred")
    service = FactReviewService(session)
    ctx = TenantContext("tenant-a", "writer-a")

    service.defer(ctx, fact.id, expected_version=1, rationale="Review later")
    assert [item.id for item in service.review_queue(ctx, "study-a")] == [fact.id]

    resumed = service.resume(ctx, fact.id, expected_version=1, rationale="Evidence checked")

    assert resumed.deferred is False
