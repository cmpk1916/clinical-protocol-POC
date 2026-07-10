from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base


class FactConflict(Base):
    __tablename__ = "fact_conflicts"
    __table_args__ = (
        ForeignKeyConstraint(["fact_id", "tenant_id"], ["facts.id", "facts.tenant_id"], name="fk_conflict_fact_tenant"),
        CheckConstraint("status IN ('open','resolved')", name="ck_fact_conflict_status"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conflicting_fact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    resolution: Mapped[str | None] = mapped_column(String(512))
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def resolve(self, actor_id: str, resolution: str) -> None:
        self.status = "resolved"
        self.resolution = resolution
        self.resolved_by = actor_id
        self.resolved_at = datetime.now(timezone.utc)
