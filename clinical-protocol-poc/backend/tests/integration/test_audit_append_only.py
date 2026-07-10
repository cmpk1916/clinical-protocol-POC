from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session

from protocol_poc.audit.models import AuditEvent, AppendOnlyViolation
from protocol_poc.audit.service import AuditService
from protocol_poc.common.ids import new_id
from protocol_poc.db import Base
from protocol_poc.tenancy import TenantContext


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def audit_service(db_session: Session) -> AuditService:
    return AuditService(db_session)


@pytest.fixture
def tenant_a() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", actor_id="user-a")


@pytest.fixture
def tenant_b() -> TenantContext:
    return TenantContext(tenant_id="tenant-b", actor_id="user-b")


def test_events_are_scoped_to_tenant(
    audit_service: AuditService, tenant_a: TenantContext, tenant_b: TenantContext
) -> None:
    audit_service.append(tenant_a, "study.created", "study", "s1", {"version": 1})
    assert len(audit_service.list_for(tenant_a, "study", "s1")) == 1
    assert audit_service.list_for(tenant_b, "study", "s1") == []


def test_append_does_not_commit(db_session: Session, tenant_a: TenantContext) -> None:
    event = AuditService(db_session).append(
        tenant_a, "study.created", "study", "s1", {"version": 1}
    )
    assert event in db_session.new


def test_audit_event_cannot_be_updated(
    db_session: Session, tenant_a: TenantContext
) -> None:
    event = AuditService(db_session).append(
        tenant_a, "study.created", "study", "s1", {"version": 1}
    )
    db_session.commit()
    event.event_type = "changed"
    with pytest.raises(AppendOnlyViolation):
        db_session.commit()


@pytest.mark.parametrize("statement", [update(AuditEvent), delete(AuditEvent)])
def test_bulk_mutation_is_blocked(db_session: Session, statement: object) -> None:
    with pytest.raises(AppendOnlyViolation):
        db_session.execute(statement)  # type: ignore[arg-type]


def test_context_is_frozen_and_rejects_blanks() -> None:
    ctx = TenantContext(tenant_id="tenant-a", actor_id="user-a")
    with pytest.raises(FrozenInstanceError):
        ctx.tenant_id = "other"  # type: ignore[misc]
    with pytest.raises(ValueError):
        TenantContext(tenant_id="", actor_id="user-a")


def test_service_rejects_missing_context(db_session: Session) -> None:
    with pytest.raises(TypeError):
        AuditService(db_session).list_for(None, "study", "s1")  # type: ignore[arg-type]


def test_ids_are_fixed_width_sortable_and_unique() -> None:
    ids = [new_id() for _ in range(100)]
    assert all(len(value) == 26 for value in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
