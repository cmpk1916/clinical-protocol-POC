import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.studies.models import EndpointRecord, ObjectiveRecord, Study


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_relationships_reject_dangling_objective(session: Session) -> None:
    session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
    session.flush()
    session.add(
        EndpointRecord(
            id="endpoint-a", tenant_id="tenant-a", study_id="study-a",
            name="HbA1c change", hierarchy="primary", objective_id="missing"
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_relationships_reject_cross_tenant_links(session: Session) -> None:
    session.add_all([
        Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"),
        Study(id="study-b", tenant_id="tenant-b", name="Other synthetic study"),
    ])
    session.flush()
    session.add(
        ObjectiveRecord(
            id="objective-b", tenant_id="tenant-b", study_id="study-b",
            name="Evaluate efficacy"
        )
    )
    session.flush()
    session.add(
        EndpointRecord(
            id="endpoint-a", tenant_id="tenant-a", study_id="study-a",
            name="HbA1c change", hierarchy="primary", objective_id="objective-b"
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
