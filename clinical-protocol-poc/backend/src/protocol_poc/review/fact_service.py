from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.review.conflicts import FactConflict
from protocol_poc.review.impact_service import ImpactService
from protocol_poc.studies.models import Fact, FactVersion
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


class FactReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def _fact(self, ctx: TenantContext, fact_id: str, expected_version: int) -> Fact:
        context = require_tenant_context(ctx)
        fact = self.session.scalar(select(Fact).where(Fact.id == fact_id, Fact.tenant_id == context.tenant_id))
        if fact is None:
            raise FactNotFound(fact_id)
        if fact.current_version != expected_version:
            raise VersionConflict(f"expected version {expected_version}, found {fact.current_version}")
        return fact

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
        self.session.add(FactVersion(tenant_id=ctx.tenant_id, fact_id=fact.id, version=fact.current_version, value_json=value_json, source_evidence_id=current.source_evidence_id, is_current=True, rationale=rationale))
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

    def resolve_conflict(self, ctx: TenantContext, fact_id: str, *, expected_version: int, resolution: str) -> Fact:
        fact = self._fact(ctx, fact_id, expected_version)
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
            else_=2,
        )
        statement = select(Fact).where(
            Fact.tenant_id == context.tenant_id,
            Fact.study_id == study_id,
            Fact.status.in_(("candidate", "conflicted")),
            Fact.deferred.is_(False),
        ).order_by(priority, Fact.id)
        return list(self.session.scalars(statement))
