from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from protocol_poc.drafting.context import DraftContextBuilder
from protocol_poc.drafting.local_composer import ComposedPassage, LocalComposer
from protocol_poc.drafting.models import Claim, Passage, PassageVersion, SupportLink
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext


@dataclass(frozen=True)
class DraftResult:
    passage_id: str
    text: str
    status: str
    version: int


class PassageAlreadyExists(RuntimeError):
    pass


class DraftingService:
    SCOPED_SECTIONS = {"synopsis", "objectives_endpoints", "study_design", "eligibility"}

    def __init__(self, session: Session, composer: LocalComposer | None = None) -> None:
        self.session = session
        self.composer = composer or LocalComposer()

    def generate(self, ctx: TenantContext, study_id: str, *, section: str) -> DraftResult:
        if section not in self.SCOPED_SECTIONS:
            raise ValueError("section is outside the bounded drafting scope")
        StudyService(self.session).require_active(ctx, study_id)
        existing = self._passage_for_section(ctx, study_id, section)
        if existing is not None:
            raise PassageAlreadyExists("a passage already exists for this section")
        output = self.composer.compose(
            section, DraftContextBuilder(self.session).for_section(ctx, study_id, section).facts
        )
        passage = Passage(tenant_id=ctx.tenant_id, study_id=study_id, section=section, status=self._status(output), current_version=1)
        try:
            with self.session.begin_nested():
                self.session.add(passage)
                self.session.flush()
        except IntegrityError as error:
            if self._passage_for_section(ctx, study_id, section) is not None:
                raise PassageAlreadyExists("a passage already exists for this section") from error
            raise
        self._persist_version(ctx, passage, output)
        return DraftResult(passage.id, output.text, passage.status, passage.current_version)

    def regenerate(self, ctx: TenantContext, passage_id: str, *, expected_version: int) -> DraftResult:
        passage = self.session.scalar(
            select(Passage).where(Passage.id == passage_id, Passage.tenant_id == ctx.tenant_id)
        )
        if passage is None:
            raise ValueError("passage not found")
        StudyService(self.session).require_active(ctx, passage.study_id)
        if passage.current_version != expected_version:
            from protocol_poc.drafting.review_service import PassageVersionConflict
            raise PassageVersionConflict("passage version changed")
        current = self.session.scalar(select(PassageVersion).where(
            PassageVersion.passage_id == passage.id,
            PassageVersion.tenant_id == ctx.tenant_id,
            PassageVersion.is_current.is_(True),
        ))
        if current is None:
            raise ValueError("current passage version missing")
        current.is_current = False
        passage.current_version += 1
        output = self.composer.compose(
            passage.section,
            DraftContextBuilder(self.session).for_section(ctx, passage.study_id, passage.section).facts,
        )
        passage.status = self._status(output)
        passage.invalidation_reason = None
        self._persist_version(ctx, passage, output)
        return DraftResult(passage.id, output.text, passage.status, passage.current_version)

    @staticmethod
    def _status(output: ComposedPassage) -> str:
        return "blocked" if output.placeholders else "ready_for_review"

    def _passage_for_section(self, ctx: TenantContext, study_id: str, section: str) -> Passage | None:
        return self.session.scalar(select(Passage).where(
            Passage.tenant_id == ctx.tenant_id,
            Passage.study_id == study_id,
            Passage.section == section,
        ))

    def _persist_version(self, ctx: TenantContext, passage: Passage, output: ComposedPassage) -> None:
        version = PassageVersion(
            tenant_id=ctx.tenant_id,
            passage_id=passage.id,
            version=passage.current_version,
            text=output.text,
            placeholders=list(output.placeholders),
            is_current=True,
        )
        self.session.add(version)
        self.session.flush()
        self.session.add_all([
            Claim(
                tenant_id=ctx.tenant_id,
                passage_version_id=version.id,
                text=str(claim["text"]),
                metadata_json=claim,
            )
            for claim in output.claims
        ])
        self.session.add_all([
            SupportLink(
                tenant_id=ctx.tenant_id,
                passage_version_id=version.id,
                support_type="fact",
                support_id=support_id,
            )
            for support_id in output.fact_ids
        ])
        self.session.flush()
