from dataclasses import dataclass
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


@dataclass(frozen=True)
class ExportSnapshotBuild:
    snapshot: ExportSnapshot
    template_version: FileVersion
    scorecard: QualityScorecard


class ExportService:
    _REQUIRED_SECTIONS = frozenset({
        "synopsis", "objectives_endpoints", "study_design", "eligibility",
    })

    def __init__(self, session: Session, quality_service: QualityCalculator | None = None) -> None:
        self.session = session
        self.quality = quality_service or QualityService(session)
        self.audit = AuditService(session)

    def create_snapshot(
        self,
        ctx: TenantContext,
        study_id: str,
        *,
        expected_study_version: int,
        template_version_id: str,
        template_hash: str,
        renderer_version: str = "pending",
    ) -> ExportSnapshot:
        return self.create_snapshot_build(
            ctx,
            study_id,
            expected_study_version=expected_study_version,
            template_version_id=template_version_id,
            template_hash=template_hash,
            renderer_version=renderer_version,
        ).snapshot

    def create_snapshot_build(
        self,
        ctx: TenantContext,
        study_id: str,
        *,
        expected_study_version: int,
        template_version_id: str,
        template_hash: str,
        renderer_version: str,
    ) -> ExportSnapshotBuild:
        if self.session.get_bind().dialect.name == "sqlite":
            self.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        study = self.session.scalar(
            select(Study)
            .where(Study.id == study_id, Study.tenant_id == ctx.tenant_id)
            .with_for_update()
        )
        state = ExportState()
        if study is None or study.version != expected_study_version:
            state.add_blocker("STUDY_VERSION_CHANGED")
        elif study.lifecycle != "active":
            state.add_blocker("STUDY_ARCHIVED")

        template, facts, passages = self._materialize_authority(
            ctx, study_id, template_version_id, template_hash, state
        )
        try:
            scorecard = self.quality.calculate(ctx, study_id)
            for blocker in scorecard.blockers:
                state.add_quality_blocker(blocker.code)
        except Exception:
            state.validator_exception = True
            scorecard = None
        decision = ExportGate().evaluate(state)
        if not decision.allowed or study is None or template is None or scorecard is None:
            self.audit.append(
                ctx, "export.denied", "study", study_id,
                {"blocker_codes": list(decision.blocker_codes)},
            )
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
        self.session.add_all([
            SnapshotFact(
                tenant_id=ctx.tenant_id,
                snapshot_id=snapshot.id,
                source_fact_id=fact.id,
                source_version=version.version,
                value_json=version.value_json,
            )
            for fact, version in facts
        ])
        self.session.add_all([
            SnapshotPassage(
                tenant_id=ctx.tenant_id,
                snapshot_id=snapshot.id,
                source_passage_id=passage.id,
                source_version=version.version,
                section=passage.section,
                text=version.text,
                review_state=passage.status,
            )
            for passage, version in passages
        ])
        self.session.add(SnapshotTemplate(
            tenant_id=ctx.tenant_id,
            snapshot_id=snapshot.id,
            template_version_id=template.id,
            content_hash=template.checksum_sha256,
        ))
        self.audit.append(
            ctx, "export.snapshot_created", "export_snapshot", snapshot.id,
            {"study_id": study_id, "study_version": study.version},
        )
        self.session.flush()
        return ExportSnapshotBuild(snapshot, template, scorecard)

    def _materialize_authority(
        self,
        ctx: TenantContext,
        study_id: str,
        template_version_id: str,
        template_hash: str,
        state: ExportState,
    ) -> tuple[FileVersion | None, list[tuple[Fact, FactVersion]], list[tuple[Passage, PassageVersion]]]:
        inputs = {
            item.role: item
            for item in self.session.scalars(
                select(StudyInput)
                .where(StudyInput.tenant_id == ctx.tenant_id, StudyInput.study_id == study_id)
                .with_for_update()
            )
        }
        template = self._current_template(
            ctx, inputs.get("template"), template_version_id, template_hash, state
        )
        synopsis = inputs.get("synopsis")
        attempts = list(self.session.scalars(
            select(ProcessingAttempt).where(
                ProcessingAttempt.tenant_id == ctx.tenant_id,
                ProcessingAttempt.study_id == study_id,
                ProcessingAttempt.synopsis_version_id == (
                    synopsis.current_file_version_id if synopsis is not None else ""
                ),
            ).with_for_update()
        ))
        if synopsis is None or not any(item.status == "succeeded" for item in attempts):
            state.add_blocker("INPUT_PROCESSING_INCOMPLETE")

        facts = list(self.session.scalars(
            select(Fact).where(
                Fact.tenant_id == ctx.tenant_id,
                Fact.study_id == study_id,
                Fact.status.in_(("approved", "candidate", "conflicted")),
            ).with_for_update()
        ))
        if any(item.status in {"candidate", "conflicted"} for item in facts):
            state.add_blocker("FACT_REVIEW_INCOMPLETE")
        fact_versions = list(self.session.scalars(
            select(FactVersion).where(
                FactVersion.tenant_id == ctx.tenant_id,
                FactVersion.fact_id.in_([item.id for item in facts]),
                FactVersion.is_current.is_(True),
            ).with_for_update()
        )) if facts else []
        fact_pairs = self._current_fact_pairs(facts, fact_versions, state)

        passages = list(self.session.scalars(
            select(Passage).where(
                Passage.tenant_id == ctx.tenant_id,
                Passage.study_id == study_id,
            ).with_for_update()
        ))
        versions = list(self.session.scalars(
            select(PassageVersion).where(
                PassageVersion.tenant_id == ctx.tenant_id,
                PassageVersion.passage_id.in_([item.id for item in passages]),
                PassageVersion.is_current.is_(True),
            ).with_for_update()
        )) if passages else []
        passage_pairs = self._current_passage_pairs(passages, versions, state)
        return template, fact_pairs, passage_pairs

    def _current_template(
        self,
        ctx: TenantContext,
        template: StudyInput | None,
        template_version_id: str,
        template_hash: str,
        state: ExportState,
    ) -> FileVersion | None:
        if template is None:
            state.add_blocker("TEMPLATE_VERSION_INVALID")
            return None
        if template.conformance_status != "conforming":
            state.add_blocker("TEMPLATE_NOT_CONFORMED")
            return None
        if template.current_file_version_id != template_version_id:
            state.add_blocker("TEMPLATE_VERSION_INVALID")
            return None
        version = self.session.scalar(
            select(FileVersion).where(
                FileVersion.id == template.current_file_version_id,
                FileVersion.tenant_id == ctx.tenant_id,
            ).with_for_update()
        )
        if version is None:
            state.add_blocker("TEMPLATE_VERSION_INVALID")
        elif version.checksum_sha256 != template_hash:
            state.add_blocker("TEMPLATE_HASH_MISMATCH")
        return version

    @staticmethod
    def _current_fact_pairs(
        facts: list[Fact],
        versions: list[FactVersion],
        state: ExportState,
    ) -> list[tuple[Fact, FactVersion]]:
        by_fact: dict[str, list[FactVersion]] = {}
        for version in versions:
            by_fact.setdefault(version.fact_id, []).append(version)
        pairs: list[tuple[Fact, FactVersion]] = []
        for fact in facts:
            current = by_fact.get(fact.id, [])
            if len(current) != 1 or current[0].version != fact.current_version:
                state.add_blocker("FACT_REVIEW_INCOMPLETE")
            elif fact.status == "approved":
                pairs.append((fact, current[0]))
        return pairs

    def _current_passage_pairs(
        self,
        passages: list[Passage],
        versions: list[PassageVersion],
        state: ExportState,
    ) -> list[tuple[Passage, PassageVersion]]:
        by_passage: dict[str, list[PassageVersion]] = {}
        for version in versions:
            by_passage.setdefault(version.passage_id, []).append(version)
        if (
            len(passages) != len(self._REQUIRED_SECTIONS)
            or {item.section for item in passages} != self._REQUIRED_SECTIONS
            or any(item.status != "accepted" for item in passages)
        ):
            state.add_blocker("PASSAGE_REVIEW_INCOMPLETE")
            return []
        pairs: list[tuple[Passage, PassageVersion]] = []
        for passage in passages:
            current = by_passage.get(passage.id, [])
            if len(current) != 1 or current[0].version != passage.current_version:
                state.add_blocker("PASSAGE_REVIEW_INCOMPLETE")
                return []
            pairs.append((passage, current[0]))
        return pairs
