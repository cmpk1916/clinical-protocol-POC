from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Study(Base):
    __tablename__ = "studies"
    __table_args__ = (UniqueConstraint("id", "tenant_id", name="uq_study_id_tenant"),)
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class _StudyEntity:
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


def _entity_args(name: str) -> tuple[object, ...]:
    return (
        UniqueConstraint("id", "tenant_id", name=f"uq_{name}_id_tenant"),
        ForeignKeyConstraint(["study_id", "tenant_id"], ["studies.id", "studies.tenant_id"], name=f"fk_{name}_study_tenant"),
    )


class ObjectiveRecord(_StudyEntity, Base):
    __tablename__ = "objectives"
    __table_args__ = _entity_args("objective")


class TimepointRecord(_StudyEntity, Base):
    __tablename__ = "timepoints"
    __table_args__ = _entity_args("timepoint")


class PopulationRecord(_StudyEntity, Base):
    __tablename__ = "populations"
    __table_args__ = _entity_args("population")


class ArmRecord(_StudyEntity, Base):
    __tablename__ = "arms"
    __table_args__ = _entity_args("arm")


class InterventionRecord(_StudyEntity, Base):
    __tablename__ = "interventions"
    __table_args__ = _entity_args("intervention")


class EligibilityCriterionRecord(_StudyEntity, Base):
    __tablename__ = "eligibility_criteria"
    __table_args__ = _entity_args("eligibility_criterion")


class ScheduleConceptRecord(_StudyEntity, Base):
    __tablename__ = "schedule_concepts"
    __table_args__ = _entity_args("schedule_concept")


class EndpointRecord(_StudyEntity, Base):
    __tablename__ = "endpoints"
    __table_args__ = (
        *_entity_args("endpoint"),
        ForeignKeyConstraint(["objective_id", "tenant_id"], ["objectives.id", "objectives.tenant_id"], name="fk_endpoint_objective_tenant"),
        ForeignKeyConstraint(["timepoint_id", "tenant_id"], ["timepoints.id", "timepoints.tenant_id"], name="fk_endpoint_timepoint_tenant"),
        CheckConstraint("hierarchy IN ('primary', 'secondary', 'exploratory')", name="ck_endpoint_hierarchy"),
    )
    hierarchy: Mapped[str] = mapped_column(String(16), nullable=False)
    objective_id: Mapped[str | None] = mapped_column(String(128))
    timepoint_id: Mapped[str | None] = mapped_column(String(128))


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_fact_id_tenant"),
        ForeignKeyConstraint(["study_id", "tenant_id"], ["studies.id", "studies.tenant_id"], name="fk_fact_study_tenant"),
        CheckConstraint("status IN ('candidate','approved','rejected','superseded','conflicted')", name="ck_fact_status"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FactVersion(Base):
    __tablename__ = "fact_versions"
    __table_args__ = (
        UniqueConstraint("fact_id", "version", name="uq_fact_version_number"),
        ForeignKeyConstraint(["fact_id", "tenant_id"], ["facts.id", "facts.tenant_id"], name="fk_fact_version_fact_tenant"),
        Index("uq_fact_version_current", "fact_id", unique=True, sqlite_where=text("is_current = 1"), postgresql_where=text("is_current")),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_evidence_id: Mapped[str | None] = mapped_column(String(128))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
