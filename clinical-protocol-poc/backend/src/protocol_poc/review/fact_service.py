from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.review.conflicts import FactConflict
from protocol_poc.review.impact_service import ImpactService
from protocol_poc.files.models import SourceEvidence
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext, require_tenant_context


class FactReviewError(RuntimeError):
    pass


class FactNotFound(FactReviewError):
    pass


class ExplicitConfirmationRequired(FactReviewError):
    pass


class UnresolvedConflict(FactReviewError):
    pass


class VersionConflict(FactReviewError):
    pass


class EvidenceUnavailable(FactReviewError):
    pass


@dataclass(frozen=True, slots=True)
class FactReviewItem:
    fact: Fact
    value: dict[str, Any]
    confidence: float | None
    evidence_id: str | None
    evidence_location: dict[str, Any] | None
    evidence_text: str | None
    extractor_version: str | None
    synopsis_version_id: str | None
    downstream_impact: tuple[str, ...]
    evidence_valid: bool


class FactReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def require_active_fact(self, ctx: TenantContext, fact_id: str) -> Fact:
        context = require_tenant_context(ctx)
        fact = self.session.scalar(select(Fact).where(Fact.id == fact_id, Fact.tenant_id == context.tenant_id))
        if fact is None:
            raise FactNotFound(fact_id)
        StudyService(self.session).require_active(context, fact.study_id)
        return fact

    def _fact(self, ctx: TenantContext, fact_id: str, expected_version: int) -> Fact:
        context = require_tenant_context(ctx)
        fact = self.require_active_fact(context, fact_id)
        if fact.current_version != expected_version:
            raise VersionConflict(f"expected version {expected_version}, found {fact.current_version}")
        if not self._evidence_is_exact(context, fact):
            raise EvidenceUnavailable("exact source evidence could not be verified")
        return fact

    def _evidence_is_exact(self, ctx: TenantContext, fact: Fact) -> bool:
        if fact.processing_attempt_id is None:
            return True
        row = self.session.execute(
            select(FactVersion, SourceEvidence, ProcessingAttempt)
            .outerjoin(
                SourceEvidence,
                (SourceEvidence.id == FactVersion.source_evidence_id)
                & (SourceEvidence.tenant_id == FactVersion.tenant_id),
            )
            .join(
                ProcessingAttempt,
                (ProcessingAttempt.id == fact.processing_attempt_id)
                & (ProcessingAttempt.tenant_id == FactVersion.tenant_id),
            )
            .where(
                FactVersion.fact_id == fact.id,
                FactVersion.tenant_id == ctx.tenant_id,
                FactVersion.is_current.is_(True),
            )
        ).one_or_none()
        if row is None:
            return False
        version, evidence, attempt = row
        return bool(
            evidence is not None
            and evidence.file_version_id == attempt.synopsis_version_id
            and version.source_evidence_version_id == attempt.synopsis_version_id
        )

    @staticmethod
    def _require_confirmation(fact: Fact, explicitly_confirmed: bool) -> None:
        if fact.critical and not explicitly_confirmed:
            raise ExplicitConfirmationRequired("critical facts require explicit confirmation")

    def approve(self, ctx: TenantContext, fact_id: str, *, expected_version: int, explicitly_confirmed: bool) -> Fact:
        fact = self._fact(ctx, fact_id, expected_version)
        if fact.status == "conflicted":
            raise UnresolvedConflict("conflicting facts must be resolved before approval")
        self._require_confirmation(fact, explicitly_confirmed)
        fact.status = "approved"
        fact.deferred = False
        self.audit.append(ctx, "fact.approved", "fact", fact.id, {"version": fact.current_version, "explicitly_confirmed": explicitly_confirmed})
        return fact

    def correct_and_approve(self, ctx: TenantContext, fact_id: str, *, expected_version: int, value_json: dict[str, Any], rationale: str, explicitly_confirmed: bool) -> Fact:
        fact = self._fact(ctx, fact_id, expected_version)
        if fact.status == "conflicted":
            raise UnresolvedConflict("conflicting facts must be resolved before correction")
        self._require_confirmation(fact, explicitly_confirmed)
        current = self.session.scalar(select(FactVersion).where(FactVersion.fact_id == fact.id, FactVersion.tenant_id == ctx.tenant_id, FactVersion.is_current.is_(True)))
        if current is None:
            raise FactReviewError("current fact version is missing")
        current.is_current = False
        self.session.flush()
        fact.current_version += 1
        fact.status = "approved"
        fact.deferred = False
        self.session.add(FactVersion(tenant_id=ctx.tenant_id, fact_id=fact.id, version=fact.current_version, value_json=value_json, confidence=current.confidence, source_evidence_id=current.source_evidence_id, source_evidence_version_id=current.source_evidence_version_id, is_current=True, rationale=rationale))
        self.audit.append(ctx, "fact.corrected_and_approved", "fact", fact.id, {"version": fact.current_version, "rationale": rationale, "explicitly_confirmed": explicitly_confirmed})
        ImpactService(self.session).invalidate_for_fact(ctx, fact.id)
        return fact

    def reject(self, ctx: TenantContext, fact_id: str, *, expected_version: int, rationale: str) -> Fact:
        fact = self._fact(ctx, fact_id, expected_version)
        fact.status = "rejected"
        fact.deferred = False
        self.audit.append(ctx, "fact.rejected", "fact", fact.id, {"version": fact.current_version, "rationale": rationale})
        return fact

    def defer(self, ctx: TenantContext, fact_id: str, *, expected_version: int, rationale: str) -> Fact:
        fact = self._fact(ctx, fact_id, expected_version)
        fact.deferred = True
        self.audit.append(ctx, "fact.deferred", "fact", fact.id, {"version": fact.current_version, "rationale": rationale})
        return fact

    def resume(self, ctx: TenantContext, fact_id: str, *, expected_version: int, rationale: str) -> Fact:
        fact = self._fact(ctx, fact_id, expected_version)
        fact.deferred = False
        self.audit.append(
            ctx,
            "fact.review_resumed",
            "fact",
            fact.id,
            {"version": fact.current_version, "rationale": rationale},
        )
        return fact

    def resolve_conflict(self, ctx: TenantContext, fact_id: str, *, expected_version: int, resolution: str) -> Fact:
        fact = self._fact(ctx, fact_id, expected_version)
        if not resolution.strip():
            raise FactReviewError("conflict resolution rationale is required")
        conflicts = list(self.session.scalars(select(FactConflict).where(FactConflict.fact_id == fact.id, FactConflict.tenant_id == ctx.tenant_id, FactConflict.status == "open")))
        if not conflicts and fact.status != "conflicted":
            raise UnresolvedConflict("fact has no open conflict")
        for conflict in conflicts:
            conflict.resolve(ctx.actor_id, resolution)
        fact.status = "candidate"
        self.audit.append(ctx, "fact.conflict_resolved", "fact", fact.id, {"version": fact.current_version, "resolution": resolution})
        return fact

    def review_queue(self, ctx: TenantContext, study_id: str) -> list[Fact]:
        context = require_tenant_context(ctx)
        priority = case(
            (Fact.status == "conflicted", 0),
            (Fact.critical.is_(True), 1),
            (Fact.deferred.is_(True), 3),
            else_=2,
        )
        statement = select(Fact).where(
            Fact.tenant_id == context.tenant_id,
            Fact.study_id == study_id,
            Fact.status.in_(("candidate", "conflicted")),
        ).order_by(priority, Fact.id)
        return list(self.session.scalars(statement))

    def review_items(self, ctx: TenantContext, study_id: str) -> list[FactReviewItem]:
        facts = self.review_queue(ctx, study_id)
        if not facts:
            return []
        fact_ids = [fact.id for fact in facts]
        statement = (
            select(FactVersion, SourceEvidence, ProcessingAttempt)
            .outerjoin(
                SourceEvidence,
                (SourceEvidence.id == FactVersion.source_evidence_id)
                & (SourceEvidence.tenant_id == FactVersion.tenant_id),
            )
            .join(
                Fact,
                (Fact.id == FactVersion.fact_id) & (Fact.tenant_id == FactVersion.tenant_id),
            )
            .outerjoin(
                ProcessingAttempt,
                (ProcessingAttempt.id == Fact.processing_attempt_id)
                & (ProcessingAttempt.tenant_id == Fact.tenant_id),
            )
            .where(FactVersion.fact_id.in_(fact_ids), FactVersion.is_current.is_(True))
        )
        by_fact = {version.fact_id: (version, evidence, attempt) for version, evidence, attempt in self.session.execute(statement)}
        items: list[FactReviewItem] = []
        for fact in facts:
            row = by_fact.get(fact.id)
            if row is None:
                continue
            version, evidence, attempt = row
            evidence_valid = attempt is None or not (
                evidence is None
                or evidence.file_version_id != attempt.synopsis_version_id
                or version.source_evidence_version_id != attempt.synopsis_version_id
            )
            embedded_confidence = version.value_json.get("confidence")
            confidence = version.confidence
            if confidence is None and isinstance(embedded_confidence, (int, float)):
                confidence = float(embedded_confidence)
            items.append(
                FactReviewItem(
                    fact=fact,
                    value=version.value_json,
                    confidence=confidence,
                    evidence_id=evidence.id if evidence_valid and evidence is not None else None,
                    evidence_location=evidence.location_json if evidence_valid and evidence is not None else None,
                    evidence_text=evidence.text if evidence_valid and evidence is not None else None,
                    extractor_version=attempt.extractor_version if attempt is not None else None,
                    synopsis_version_id=attempt.synopsis_version_id if attempt is not None else None,
                    downstream_impact=self._downstream_impact(fact.kind),
                    evidence_valid=evidence_valid,
                )
            )
        return items

    @staticmethod
    def _downstream_impact(kind: str) -> tuple[str, ...]:
        by_kind = {
            "study_identity": ("synopsis",),
            "population": ("synopsis",),
            "objective": ("objectives_endpoints",),
            "endpoint": ("objectives_endpoints",),
            "timepoint": ("objectives_endpoints",),
            "arm": ("study_design",),
            "intervention": ("study_design",),
            "dose": ("study_design",),
            "eligibility": ("eligibility",),
        }
        return by_kind.get(kind, ())
