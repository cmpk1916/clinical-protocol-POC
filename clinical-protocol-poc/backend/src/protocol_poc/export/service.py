from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.drafting.models import Passage, PassageVersion
from protocol_poc.export.gate import ExportGate, ExportState
from protocol_poc.export.models import ExportSnapshot, SnapshotFact, SnapshotPassage, SnapshotTemplate
from protocol_poc.quality.models import QualityScorecard
from protocol_poc.quality.service import QualityService
from protocol_poc.studies.models import Fact, FactVersion, Study
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

    def create_snapshot(self, ctx: TenantContext, study_id: str, *, expected_study_version: int, template_version_id: str, template_hash: str) -> ExportSnapshot:
        study = self.session.scalar(select(Study).where(Study.id == study_id, Study.tenant_id == ctx.tenant_id).with_for_update())
        state = ExportState()
        if study is None or study.version != expected_study_version:
            state.add_blocker("STUDY_VERSION_CHANGED")
        try:
            card = self.quality.calculate(ctx, study_id)
            state.blocker_codes.extend(item.code for item in card.blockers)
        except Exception:
            state.validator_exception = True
        decision = ExportGate().evaluate(state)
        if not decision.allowed or study is None:
            self.audit.append(ctx, "export.denied", "study", study_id, {"blocker_codes": list(decision.blocker_codes)})
            self.session.flush()
            raise ExportDenied(decision.blocker_codes)
        snapshot = ExportSnapshot(tenant_id=ctx.tenant_id, study_id=study_id, study_version=study.version)
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
