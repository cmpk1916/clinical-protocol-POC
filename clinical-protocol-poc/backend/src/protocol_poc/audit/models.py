from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base


class AppendOnlyViolation(RuntimeError):
    """Raised when existing audit history is mutated."""


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index(
            "ix_audit_events_tenant_aggregate_occurred",
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
