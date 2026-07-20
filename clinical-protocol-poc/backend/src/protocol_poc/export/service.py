from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.drafting.models import Passage, PassageVersion
from protocol_poc.export.gate import ExportGate, ExportState
from protocol_poc.export.models import ExportSnapshot, SnapshotFact, SnapshotPassage, SnapshotTemplate
from protocol_poc.files.models import FileVersion, StudyInput
from protocol_poc.quality.models import QualityScorecard
from protocol_poc.quality.service import QualityService
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, Study
from protocol_poc.tenancy import TenantContext


class QualityCalculator(Protocol):
    def calculate(self, ctx: TenantContext, study_id: str) -> QualityScorecard: ...


class ExportDenied(RuntimeError):
    def __init__(self, codes: tuple[str, ...]) -> None:
        self.codes = codes
        super().__init__(f"export denied: {', '.join(codes)}")


class ExportService:
    def __init__(self, session: Session, quality_service: QualityCalculator | None = None) -> None:
        self.session = session
        self.quality = quality_service or QualityService(session)
        self.audit = AuditService(session)

    def create_snapshot(self, ctx: TenantContext, study_id: str, *, expected_study_version: int, template_version_id: str, template_hash: str, renderer_version: str = "pending") -> ExportSnapshot:
        study = self.session.scalar(select(Study).where(Study.id == study_id, Study.tenant_id == ctx.tenant_id).with_for_update())
        state = ExportState()
        if study is None or study.version != expected_study_version:
            state.add_blocker("STUDY_VERSION_CHANGED")
        elif study.lifecycle != "active":
            state.add_blocker("STUDY_ARCHIVED")
        if study is not None:
            self._check_current_workspace_authority(
                ctx,
                study_id,
                template_version_id,
                template_hash,
                state,
            )
        try:
            card = self.quality.calculate(ctx, study_id)
            for blocker in card.blockers:
                state.add_quality_blocker(blocker.code)
        except Exception:
            state.validator_exception = True
        decision = ExportGate().evaluate(state)
        if not decision.allowed or study is None:
            self.audit.append(ctx, "export.denied", "study", study_id, {"blocker_codes": list(decision.blocker_codes)})
            self.session.flush()
            raise ExportDenied(decision.blocker_codes)
        snapshot = ExportSnapshot(
            tenant_id=ctx.tenant_id,
            study_id=study_id,
            study_version=study.version,
            renderer_version=renderer_version,
        )
        self.session.add(snapshot)
        self.session.flush()
        facts = self.session.execute(select(Fact, FactVersion).join(FactVersion, (FactVersion.fact_id == Fact.id) & (FactVersion.tenant_id == Fact.tenant_id)).where(Fact.tenant_id == ctx.tenant_id, Fact.study_id == study_id, Fact.status == "approved", FactVersion.is_current.is_(True))).all()
        self.session.add_all([SnapshotFact(tenant_id=ctx.tenant_id, snapshot_id=snapshot.id, source_fact_id=fact.id, source_version=version.version, value_json=version.value_json) for fact, version in facts])
        passages = self.session.execute(select(Passage, PassageVersion).join(PassageVersion, (PassageVersion.passage_id == Passage.id) & (PassageVersion.tenant_id == Passage.tenant_id)).where(Passage.tenant_id == ctx.tenant_id, Passage.study_id == study_id, Passage.status == "accepted", PassageVersion.is_current.is_(True))).all()
        self.session.add_all([SnapshotPassage(tenant_id=ctx.tenant_id, snapshot_id=snapshot.id, source_passage_id=passage.id, source_version=version.version, section=passage.section, text=version.text, review_state=passage.status) for passage, version in passages])
        self.session.add(SnapshotTemplate(tenant_id=ctx.tenant_id, snapshot_id=snapshot.id, template_version_id=template_version_id, content_hash=template_hash))
        self.audit.append(ctx, "export.snapshot_created", "export_snapshot", snapshot.id, {"study_id": study_id, "study_version": study.version})
        self.session.flush()
        return snapshot

    def _check_current_workspace_authority(
        self,
        ctx: TenantContext,
        study_id: str,
        template_version_id: str,
        template_hash: str,
        state: ExportState,
    ) -> None:
        inputs = {
            item.role: item
            for item in self.session.scalars(
                select(StudyInput)
                .where(StudyInput.tenant_id == ctx.tenant_id, StudyInput.study_id == study_id)
                .with_for_update()
            )
        }
        template = inputs.get("template")
        if template is None:
            state.add_blocker("TEMPLATE_VERSION_INVALID")
        elif template.conformance_status != "conforming":
            state.add_blocker("TEMPLATE_NOT_CONFORMED")
        elif template.current_file_version_id != template_version_id:
            state.add_blocker("TEMPLATE_VERSION_INVALID")
        else:
            version = self.session.scalar(
                select(FileVersion).where(
                    FileVersion.id == template.current_file_version_id,
                    FileVersion.tenant_id == ctx.tenant_id,
                )
            )
            if version is None:
                state.add_blocker("TEMPLATE_VERSION_INVALID")
            elif version.checksum_sha256 != template_hash:
                state.add_blocker("TEMPLATE_HASH_MISMATCH")

        synopsis = inputs.get("synopsis")
        if synopsis is None or self.session.scalar(
            select(ProcessingAttempt.id).where(
                ProcessingAttempt.tenant_id == ctx.tenant_id,
                ProcessingAttempt.study_id == study_id,
                ProcessingAttempt.synopsis_version_id == synopsis.current_file_version_id,
                ProcessingAttempt.status == "succeeded",
            )
        ) is None:
            state.add_blocker("INPUT_PROCESSING_INCOMPLETE")

        if self.session.scalar(
            select(Fact.id).where(
                Fact.tenant_id == ctx.tenant_id,
                Fact.study_id == study_id,
                Fact.status.in_(("candidate", "conflicted")),
            ).limit(1)
        ) is not None:
            state.add_blocker("FACT_REVIEW_INCOMPLETE")

        passages = list(self.session.scalars(
            select(Passage).where(Passage.tenant_id == ctx.tenant_id, Passage.study_id == study_id)
        ))
        required_sections = {"synopsis", "objectives_endpoints", "study_design", "eligibility"}
        if (
            len(passages) != len(required_sections)
            or {passage.section for passage in passages} != required_sections
            or any(passage.status != "accepted" for passage in passages)
        ):
            state.add_blocker("PASSAGE_REVIEW_INCOMPLETE")
