from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from protocol_poc.audit.models import AuditEvent
from protocol_poc.db import Base
from protocol_poc.studies.service import (
    StudyArchived,
    StudyNotFound,
    StudyService,
    StudyVersionConflict,
)
from protocol_poc.tenancy import TenantContext


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture
def ctx() -> TenantContext:
    return TenantContext("tenant-a", "writer-a")


def test_archive_and_restore_use_optimistic_versions(session: Session, ctx: TenantContext) -> None:
    service = StudyService(session)
    study = service.create(ctx, "Synthetic Alpha")
    archived = service.archive(ctx, study.id, expected_version=1)
    assert (archived.lifecycle, archived.version, archived.archived_at is not None) == (
        "archived",
        2,
        True,
    )
    with pytest.raises(StudyVersionConflict):
        service.restore(ctx, study.id, expected_version=1)
    restored = service.restore(ctx, study.id, expected_version=2)
    assert (restored.lifecycle, restored.version, restored.archived_at) == ("active", 3, None)


def test_create_list_and_detail_are_tenant_scoped_and_audited(
    session: Session, ctx: TenantContext
) -> None:
    service = StudyService(session)
    active = service.create(ctx, "  Synthetic Alpha  ")
    archived = service.create(ctx, "Synthetic Archive")
    service.archive(ctx, archived.id, expected_version=1)

    assert active.name == "Synthetic Alpha"
    assert service.list(ctx, "active") == [active]
    assert service.list(ctx, "archived") == [archived]
    assert service.require_active(ctx, active.id) is active
    with pytest.raises(StudyArchived):
        service.require_active(ctx, archived.id)
    with pytest.raises(StudyNotFound):
        service.require_active(TenantContext("tenant-b", "writer-b"), active.id)

    events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at)))
    assert [event.event_type for event in events] == [
        "study.created",
        "study.created",
        "study.archived",
    ]
    assert all(isinstance(event.payload_json.get("version"), int) for event in events)
    assert isinstance(active.updated_at, datetime)


def test_archive_rejects_an_already_archived_study(session: Session, ctx: TenantContext) -> None:
    service = StudyService(session)
    study = service.create(ctx, "Synthetic Alpha")
    service.archive(ctx, study.id, expected_version=1)

    with pytest.raises(StudyArchived):
        service.archive(ctx, study.id, expected_version=2)


def test_concurrent_archive_rejects_a_stale_session(session: Session, ctx: TenantContext) -> None:
    service = StudyService(session)
    study = service.create(ctx, "Synthetic Alpha")
    session.commit()

    with Session(session.get_bind()) as stale_session:
        stale_service = StudyService(stale_session)
        stale_study = stale_service.get(ctx, study.id)

        service.archive(ctx, study.id, expected_version=1)
        session.commit()

        with pytest.raises(StudyVersionConflict):
            stale_service.archive(ctx, study.id, expected_version=1)
        assert stale_study.version == 2
