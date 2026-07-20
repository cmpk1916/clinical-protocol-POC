from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.drafting.context import DraftContextBuilder
from protocol_poc.drafting.local_composer import LocalComposer
from protocol_poc.drafting.models import Claim, Passage, PassageVersion, SupportLink
from protocol_poc.studies.models import Fact, FactVersion
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext
from protocol_poc.validation.clinical_values import ApprovedClinicalModel
from protocol_poc.validation.findings import Finding
from protocol_poc.validation.service import PassageValidator


class PassageReviewError(RuntimeError):
    pass


class PassageBlocked(PassageReviewError):
    pass


class PassageVersionConflict(PassageReviewError):
    pass


class PassageReviewService:
    def __init__(self, session: Session, validator: Callable[[str], list[Finding]] | None = None) -> None:
        self.session = session
        self.audit = AuditService(session)
        self.validator = validator

    def _passage(self, ctx: TenantContext, passage_id: str, expected_version: int) -> Passage:
        passage = self.session.scalar(select(Passage).where(Passage.id == passage_id, Passage.tenant_id == ctx.tenant_id))
        if passage is None:
            raise PassageReviewError("passage not found")
        StudyService(self.session).require_active(ctx, passage.study_id)
        if passage.current_version != expected_version:
            raise PassageVersionConflict("passage version changed")
        return passage

    def accept(self, ctx: TenantContext, passage_id: str, *, expected_version: int) -> Passage:
        passage = self._passage(ctx, passage_id, expected_version)
        version = self.session.scalar(select(PassageVersion).where(PassageVersion.passage_id == passage.id, PassageVersion.tenant_id == ctx.tenant_id, PassageVersion.is_current.is_(True)))
        if passage.status != "ready_for_review" or version is None or version.placeholders:
            raise PassageBlocked("only blocker-free, current passages can be accepted")
        if any(finding.severity == "blocker" for finding in self._validate(passage, version.text)):
            raise PassageBlocked("deterministic validation produced a blocker")
        passage.status = "accepted"
        passage.invalidation_reason = None
        self.audit.append(ctx, "passage.accepted", "passage", passage.id, {"version": passage.current_version})
        return passage

    def edit(self, ctx: TenantContext, passage_id: str, *, expected_version: int, text: str, support_ids: tuple[str, ...]) -> Passage:
        passage = self._passage(ctx, passage_id, expected_version)
        output = LocalComposer().compose(
            passage.section,
            DraftContextBuilder(self.session).for_section(ctx, passage.study_id, passage.section).facts,
        )
        if output.placeholders or not text.strip() or text != output.text:
            raise PassageBlocked("edited text must exactly match the current deterministic section template")
        findings = self._validate(passage, text)
        if any(item.severity == "blocker" for item in findings):
            raise PassageBlocked("deterministic validation produced a blocker")
        current = self.session.scalar(select(PassageVersion).where(PassageVersion.passage_id == passage.id, PassageVersion.tenant_id == ctx.tenant_id, PassageVersion.is_current.is_(True)))
        if current is None:
            raise PassageReviewError("current passage version missing")
        current.is_current = False
        self.session.flush()
        passage.current_version += 1
        passage.status = "ready_for_review"
        passage.invalidation_reason = None
        version = PassageVersion(tenant_id=ctx.tenant_id, passage_id=passage.id, version=passage.current_version, text=text, placeholders=[], is_current=True)
        self.session.add(version)
        self.session.flush()
        self.session.add_all([
            Claim(tenant_id=ctx.tenant_id, passage_version_id=version.id, text=str(claim["text"]), metadata_json=claim)
            for claim in output.claims
        ])
        self.session.add_all([
            SupportLink(tenant_id=ctx.tenant_id, passage_version_id=version.id, support_type="fact", support_id=support_id)
            for support_id in output.fact_ids
        ])
        self.audit.append(ctx, "passage.edited", "passage", passage.id, {"version": passage.current_version, "finding_codes": [item.code for item in findings]})
        return passage

    def reject(self, ctx: TenantContext, passage_id: str, *, expected_version: int, rationale: str) -> Passage:
        passage = self._passage(ctx, passage_id, expected_version)
        passage.status = "rejected"
        self.audit.append(ctx, "passage.rejected", "passage", passage.id, {"version": passage.current_version, "rationale": rationale})
        return passage

    def regenerate(self, ctx: TenantContext, passage_id: str, *, expected_version: int) -> Passage:
        passage = self._passage(ctx, passage_id, expected_version)
        passage.status = "draft"
        passage.invalidation_reason = None
        self.audit.append(ctx, "passage.regeneration_requested", "passage", passage.id, {"version": passage.current_version})
        return passage

    def _validate(self, passage: Passage, text: str) -> list[Finding]:
        if self.validator is not None:
            return self.validator(text)
        model = ApprovedClinicalModel()
        facts = self.session.execute(
            select(Fact, FactVersion)
            .join(FactVersion, (FactVersion.fact_id == Fact.id) & (FactVersion.tenant_id == Fact.tenant_id))
            .where(
                Fact.tenant_id == passage.tenant_id,
                Fact.study_id == passage.study_id,
                Fact.status == "approved",
                FactVersion.is_current.is_(True),
            )
        ).all()
        for fact, version in facts:
            value = version.value_json
            if fact.kind == "dose" and isinstance(value.get("value"), str) and isinstance(value.get("unit"), str):
                model.doses.add((value["value"], value["unit"]))
            elif fact.kind == "timepoint" and isinstance(value.get("value"), str) and value["value"].casefold().startswith("week "):
                try:
                    model.timepoints.add(int(value["value"].split()[1]))
                except (IndexError, ValueError):
                    continue
            elif fact.kind == "duration" and isinstance(value.get("value"), str):
                parts = value["value"].split()
                if len(parts) == 2 and parts[0].isdigit():
                    model.durations.add((int(parts[0]), parts[1]))
        return PassageValidator().validate_text(text, model)
