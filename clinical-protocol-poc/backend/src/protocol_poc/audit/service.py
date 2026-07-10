from typing import Any

from sqlalchemy import Delete, Update, event, inspect, select
from sqlalchemy.orm import ORMExecuteState, Session

from protocol_poc.audit.models import AppendOnlyViolation, AuditEvent
from protocol_poc.tenancy import TenantContext, require_tenant_context


@event.listens_for(Session, "before_flush")
def _prevent_persisted_audit_mutation(session: Session, *_: object) -> None:
    for instance in session.dirty.union(session.deleted):
        if isinstance(instance, AuditEvent) and inspect(instance).persistent:
            raise AppendOnlyViolation("audit events are append-only")


@event.listens_for(Session, "do_orm_execute")
def _prevent_bulk_audit_mutation(state: ORMExecuteState) -> None:
    statement = state.statement
    # ORM DML clones the mapped Table, so object identity is not preserved here.
    if (
        isinstance(statement, (Update, Delete))
        and getattr(statement.table, "name", None) == AuditEvent.__tablename__
        and getattr(statement.table, "schema", None) == AuditEvent.__table__.schema
    ):
        raise AppendOnlyViolation("audit events are append-only")


class AuditService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        ctx: TenantContext,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> AuditEvent:
        context = require_tenant_context(ctx)
        audit_event = AuditEvent(
            tenant_id=context.tenant_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload_json=payload,
            actor_type="user",
            actor_id=context.actor_id,
        )
        self._session.add(audit_event)
        return audit_event

    def list_for(
        self, ctx: TenantContext, aggregate_type: str, aggregate_id: str
    ) -> list[AuditEvent]:
        context = require_tenant_context(ctx)
        statement = (
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == context.tenant_id,
                AuditEvent.aggregate_type == aggregate_type,
                AuditEvent.aggregate_id == aggregate_id,
            )
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        )
        return list(self._session.scalars(statement))
