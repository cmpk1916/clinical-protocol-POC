from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Delete, Float, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, Update, event, inspect, text
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, mapped_column

from protocol_poc.common.ids import new_id
from protocol_poc.db import Base
from protocol_poc.files.models import SourceEvidence as _SourceEvidence  # noqa: F401


def now() -> datetime:
    return datetime.now(timezone.utc)


class ImmutableProcessingAttemptError(RuntimeError):
    """Raised when processing attempt history is mutated outside its workflow."""


class Study(Base):
    __tablename__ = "studies"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_study_id_tenant"),
        CheckConstraint("lifecycle IN ('active','archived')", name="ck_study_lifecycle"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class ProcessingAttempt(Base):
    __tablename__ = "processing_attempts"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_processing_attempt_id_tenant"),
        ForeignKeyConstraint(
            ["study_id", "tenant_id"],
            ["studies.id", "studies.tenant_id"],
            name="fk_processing_attempt_study_tenant",
        ),
        ForeignKeyConstraint(
            ["synopsis_version_id", "tenant_id"],
            ["file_versions.id", "file_versions.tenant_id"],
            name="fk_processing_attempt_version_tenant",
        ),
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed')",
            name="ck_processing_attempt_status",
        ),
        Index(
            "uq_processing_attempt_active",
            "tenant_id",
            "study_id",
            "synopsis_version_id",
            unique=True,
            sqlite_where=text("status IN ('pending','processing')"),
            postgresql_where=text("status IN ('pending','processing')"),
        ),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    synopsis_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    findings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_fact_id_tenant"),
        ForeignKeyConstraint(["study_id", "tenant_id"], ["studies.id", "studies.tenant_id"], name="fk_fact_study_tenant"),
        ForeignKeyConstraint(
            ["processing_attempt_id", "tenant_id"],
            ["processing_attempts.id", "processing_attempts.tenant_id"],
            name="fk_fact_processing_attempt_tenant",
        ),
        CheckConstraint("status IN ('candidate','approved','rejected','superseded','conflicted')", name="ck_fact_status"),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    study_id: Mapped[str] = mapped_column(String(128), nullable=False)
    processing_attempt_id: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FactVersion(Base):
    __tablename__ = "fact_versions"
    __table_args__ = (
        UniqueConstraint("fact_id", "version", name="uq_fact_version_number"),
        CheckConstraint(
            "(source_evidence_id IS NULL AND source_evidence_version_id IS NULL) "
            "OR (source_evidence_id IS NOT NULL AND source_evidence_version_id IS NOT NULL)",
            name="ck_fact_version_evidence_pair",
        ),
        ForeignKeyConstraint(["fact_id", "tenant_id"], ["facts.id", "facts.tenant_id"], name="fk_fact_version_fact_tenant"),
        ForeignKeyConstraint(
            ["source_evidence_id", "tenant_id", "source_evidence_version_id"],
            [
                "source_evidence.id",
                "source_evidence.tenant_id",
                "source_evidence.file_version_id",
            ],
            name="fk_fact_version_evidence_tenant_version",
        ),
        Index("uq_fact_version_current", "fact_id", unique=True, sqlite_where=text("is_current = 1"), postgresql_where=text("is_current")),
    )
    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_evidence_id: Mapped[str | None] = mapped_column(String(128))
    source_evidence_version_id: Mapped[str | None] = mapped_column(String(26))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


_PROCESSING_ATTEMPT_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"processing", "failed"}),
    "processing": frozenset({"succeeded", "failed"}),
}
_PROCESSING_ATTEMPT_MUTATION_KEY = "processing_attempt_transition_ids"


def complete_processing_attempt(
    session: Session,
    attempt: ProcessingAttempt,
    *,
    status: str,
    error_code: str | None,
    findings_json: list[dict[str, Any]],
) -> None:
    """Perform the sole supported active-to-terminal history transition."""
    if status not in _PROCESSING_ATTEMPT_TRANSITIONS.get(attempt.status, frozenset()):
        raise ImmutableProcessingAttemptError(
            f"processing attempt cannot transition from {attempt.status} to {status}"
        )
    allowed = session.info.setdefault(_PROCESSING_ATTEMPT_MUTATION_KEY, set())
    allowed.add(attempt.id)
    try:
        attempt.status = status
        attempt.error_code = error_code
        attempt.findings_json = findings_json
        attempt.completed_at = now()
        session.flush()
    finally:
        allowed.discard(attempt.id)


@event.listens_for(Session, "before_flush")
def _protect_processing_attempt_history(session: Session, *_: object) -> None:
    allowed = session.info.get(_PROCESSING_ATTEMPT_MUTATION_KEY, set())
    for instance in session.deleted:
        if isinstance(instance, ProcessingAttempt) and inspect(instance).persistent:
            raise ImmutableProcessingAttemptError(
                "processing attempts cannot be deleted"
            )
    for instance in session.dirty:
        if not isinstance(instance, ProcessingAttempt) or not inspect(instance).persistent:
            continue
        state = inspect(instance)
        previous = state.attrs.status.history.deleted
        previous_status = previous[0] if previous else instance.status
        if previous_status in {"succeeded", "failed"} or instance.id not in allowed:
            raise ImmutableProcessingAttemptError(
                "processing attempts are immutable outside controlled transitions"
            )
        if instance.status not in _PROCESSING_ATTEMPT_TRANSITIONS.get(
            previous_status, frozenset()
        ):
            raise ImmutableProcessingAttemptError(
                f"processing attempt cannot transition from {previous_status} to {instance.status}"
            )
        changed = {
            attribute.key
            for attribute in state.attrs
            if attribute.history.has_changes()
        }
        if changed - {"status", "error_code", "findings_json", "completed_at"}:
            raise ImmutableProcessingAttemptError(
                "processing attempt identity and provenance are immutable"
            )


@event.listens_for(Session, "do_orm_execute")
def _prevent_bulk_processing_attempt_mutation(state: ORMExecuteState) -> None:
    statement = state.statement
    if isinstance(statement, (Update, Delete)) and getattr(
        statement.table, "name", None
    ) == ProcessingAttempt.__tablename__:
        raise ImmutableProcessingAttemptError(
            "bulk processing attempt mutation is not allowed"
        )
