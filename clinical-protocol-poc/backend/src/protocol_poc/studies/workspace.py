from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from protocol_poc.drafting.models import Passage
from protocol_poc.export.models import ExportSnapshot
from protocol_poc.files.models import FileVersion, StudyInput
from protocol_poc.quality.service import QualityService
from protocol_poc.studies.models import Fact, ProcessingAttempt, Study
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext, require_tenant_context


WorkspaceStep = Literal[
    "archived", "inputs", "processing", "fact_review", "passage_review", "export"
]
StepStatus = Literal["complete", "current", "blocked", "upcoming"]


@dataclass(frozen=True, slots=True)
class WorkspaceBlocker:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class WorkspaceAction:
    kind: str
    label: str
    target_id: str | None = None
    href: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceStepSummary:
    key: str
    label: str
    status: StepStatus


@dataclass(frozen=True, slots=True)
class WorkspaceInput:
    role: str
    version_id: str
    version: int
    filename: str
    conformance_status: str


@dataclass(frozen=True, slots=True)
class WorkspaceProcessing:
    attempt_id: str
    status: str
    findings: tuple[WorkspaceBlocker, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceCounts:
    candidate_facts: int
    conflicted_facts: int
    approved_facts: int
    accepted_passages: int
    total_passages: int
    stale_passages: int
    blocked_passages: int
    rejected_passages: int
    exports: int


@dataclass(frozen=True, slots=True)
class WorkspaceStudy:
    id: str
    name: str
    lifecycle: str
    version: int


@dataclass(frozen=True, slots=True)
class WorkspaceExportCommand:
    expected_study_version: int
    template_version_id: str
    template_hash: str


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    study: WorkspaceStudy
    step: WorkspaceStep
    read_only: bool
    steps: tuple[WorkspaceStepSummary, ...]
    counts: WorkspaceCounts
    blockers: tuple[WorkspaceBlocker, ...]
    inputs: dict[str, WorkspaceInput | None]
    processing: WorkspaceProcessing | None
    next_action: WorkspaceAction
    export_command: WorkspaceExportCommand | None


class WorkspaceSummaryService:
    """Derive the guided-workspace read model from persisted workflow records."""

    _STEPS = (
        ("inputs", "Inputs"),
        ("processing", "Processing"),
        ("fact_review", "Fact review"),
        ("passage_review", "Passage review"),
        ("export", "Export"),
    )
    _REQUIRED_PASSAGE_SECTIONS = frozenset(
        {"synopsis", "objectives_endpoints", "study_design", "eligibility"}
    )

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, ctx: TenantContext, study_id: str) -> WorkspaceSummary:
        context = require_tenant_context(ctx)
        study = StudyService(self._session).get(context, study_id)
        inputs = self._inputs(context.tenant_id, study_id)
        processing = self._processing(context.tenant_id, study_id, inputs["synopsis"])
        counts = self._counts(context.tenant_id, study_id)
        passages = self._passages(context.tenant_id, study_id)
        passage_structure_blockers = self._passage_structure_blockers(passages)
        passages_ready = (
            not passage_structure_blockers
            and all(status == "accepted" for _, status in passages)
        )
        quality_blockers = (
            tuple(
                WorkspaceBlocker(item.code, item.message)
                for item in QualityService(self._session).calculate(context, study_id).blockers
            )
            if passages_ready
            else ()
        )

        step, blockers, action = self._derive(
            study,
            study_id,
            inputs,
            processing,
            counts,
            passages,
            passage_structure_blockers,
            quality_blockers,
        )
        completion = {
            "inputs": all(inputs.values()),
            "processing": processing is not None and processing.status == "succeeded",
            "fact_review": (
                counts.approved_facts > 0
                and counts.candidate_facts == 0
                and counts.conflicted_facts == 0
            ),
            "passage_review": passages_ready,
            "export": counts.exports > 0,
        }
        steps = tuple(
            WorkspaceStepSummary(
                key,
                label,
                "complete"
                if completion[key]
                else "blocked"
                if study.lifecycle == "active" and blockers and key == step
                else "current"
                if study.lifecycle == "active" and key == step
                else "upcoming",
            )
            for key, label in self._STEPS
        )
        return WorkspaceSummary(
            study=WorkspaceStudy(study.id, study.name, study.lifecycle, study.version),
            step=step,
            read_only=study.lifecycle == "archived",
            steps=steps,
            counts=counts,
            blockers=blockers,
            inputs=inputs,
            processing=processing,
            next_action=action,
            export_command=self._export_command(study, inputs),
        )

    def _export_command(
        self,
        study: Study,
        inputs: dict[str, WorkspaceInput | None],
    ) -> WorkspaceExportCommand | None:
        template = inputs["template"]
        if template is None or template.conformance_status != "conforming":
            return None
        version = self._session.scalar(
            select(FileVersion).where(
                FileVersion.id == template.version_id,
                FileVersion.tenant_id == study.tenant_id,
            )
        )
        if version is None:
            return None
        return WorkspaceExportCommand(study.version, version.id, version.checksum_sha256)

    def _inputs(
        self, tenant_id: str, study_id: str
    ) -> dict[str, WorkspaceInput | None]:
        statement = (
            select(StudyInput, FileVersion)
            .join(
                FileVersion,
                (FileVersion.id == StudyInput.current_file_version_id)
                & (FileVersion.tenant_id == StudyInput.tenant_id),
            )
            .where(StudyInput.tenant_id == tenant_id, StudyInput.study_id == study_id)
        )
        result: dict[str, WorkspaceInput | None] = {"synopsis": None, "template": None}
        for current, version in self._session.execute(statement):
            result[current.role] = WorkspaceInput(
                role=current.role,
                version_id=version.id,
                version=version.version,
                filename=version.display_filename,
                conformance_status=current.conformance_status,
            )
        return result

    def _processing(
        self,
        tenant_id: str,
        study_id: str,
        synopsis: WorkspaceInput | None,
    ) -> WorkspaceProcessing | None:
        if synopsis is None:
            return None
        attempt = self._session.scalar(
            select(ProcessingAttempt)
            .where(
                ProcessingAttempt.tenant_id == tenant_id,
                ProcessingAttempt.study_id == study_id,
                ProcessingAttempt.synopsis_version_id == synopsis.version_id,
            )
            .order_by(ProcessingAttempt.started_at.desc(), ProcessingAttempt.id.desc())
            .limit(1)
        )
        if attempt is None:
            return None
        findings = tuple(
            WorkspaceBlocker(
                str(item.get("code", "PROCESSING_FAILED")),
                str(item.get("message", "Synopsis processing did not complete.")),
            )
            for item in attempt.findings_json
        )
        return WorkspaceProcessing(attempt.id, attempt.status, findings)

    def _counts(self, tenant_id: str, study_id: str) -> WorkspaceCounts:
        fact_counts: dict[str, int] = {
            status: count
            for status, count in self._session.execute(
                select(Fact.status, func.count(Fact.id))
                .where(Fact.tenant_id == tenant_id, Fact.study_id == study_id)
                .group_by(Fact.status)
            ).all()
        }
        passage_counts: dict[str, int] = {
            status: count
            for status, count in self._session.execute(
                select(Passage.status, func.count(Passage.id))
                .where(Passage.tenant_id == tenant_id, Passage.study_id == study_id)
                .group_by(Passage.status)
            ).all()
        }
        exports = self._session.scalar(
            select(func.count(ExportSnapshot.id)).where(
                ExportSnapshot.tenant_id == tenant_id,
                ExportSnapshot.study_id == study_id,
            )
        )
        return WorkspaceCounts(
            candidate_facts=fact_counts.get("candidate", 0),
            conflicted_facts=fact_counts.get("conflicted", 0),
            approved_facts=fact_counts.get("approved", 0),
            accepted_passages=passage_counts.get("accepted", 0),
            total_passages=sum(passage_counts.values()),
            stale_passages=passage_counts.get("stale", 0),
            blocked_passages=passage_counts.get("blocked", 0),
            rejected_passages=passage_counts.get("rejected", 0),
            exports=exports or 0,
        )

    def _passages(self, tenant_id: str, study_id: str) -> tuple[tuple[str, str], ...]:
        return tuple(
            (section, status)
            for section, status in self._session.execute(
                select(Passage.section, Passage.status).where(
                    Passage.tenant_id == tenant_id,
                    Passage.study_id == study_id,
                )
            )
        )

    @classmethod
    def _passage_structure_blockers(
        cls, passages: tuple[tuple[str, str], ...]
    ) -> tuple[WorkspaceBlocker, ...]:
        sections = [section for section, _ in passages]
        missing = cls._REQUIRED_PASSAGE_SECTIONS.difference(sections)
        duplicates = {section for section in sections if sections.count(section) > 1}
        blockers: list[WorkspaceBlocker] = []
        if missing:
            blockers.append(
                WorkspaceBlocker(
                    "PASSAGE_SECTION_MISSING",
                    "Required draft sections are missing: " + ", ".join(sorted(missing)) + ".",
                )
            )
        if duplicates:
            blockers.append(
                WorkspaceBlocker(
                    "PASSAGE_SECTION_DUPLICATE",
                    "Duplicate current draft sections must be resolved: "
                    + ", ".join(sorted(duplicates))
                    + ".",
                )
            )
        return tuple(blockers)

    @staticmethod
    def _derive(
        study: Study,
        study_id: str,
        inputs: dict[str, WorkspaceInput | None],
        processing: WorkspaceProcessing | None,
        counts: WorkspaceCounts,
        passages: tuple[tuple[str, str], ...],
        passage_structure_blockers: tuple[WorkspaceBlocker, ...],
        quality_blockers: tuple[WorkspaceBlocker, ...],
    ) -> tuple[WorkspaceStep, tuple[WorkspaceBlocker, ...], WorkspaceAction]:
        if study.lifecycle == "archived":
            return (
                "archived",
                (WorkspaceBlocker("STUDY_ARCHIVED", "This study is archived and read-only."),),
                WorkspaceAction("restore_study", "Restore from the study dashboard", href="/"),
            )
        missing = [role for role in ("synopsis", "template") if inputs[role] is None]
        if missing:
            blockers = tuple(
                WorkspaceBlocker(
                    f"{role.upper()}_INPUT_MISSING",
                    f"Upload a supported {role} DOCX to continue.",
                )
                for role in missing
            )
            role = missing[0]
            return (
                "inputs",
                blockers,
                WorkspaceAction(f"upload_{role}", f"Upload {role}"),
            )
        synopsis = inputs["synopsis"]
        assert synopsis is not None
        if processing is None:
            return (
                "processing",
                (),
                WorkspaceAction(
                    "process_synopsis", "Process synopsis", target_id=synopsis.version_id
                ),
            )
        if processing.status == "failed":
            blockers = processing.findings or (
                WorkspaceBlocker(
                    "PROCESSING_FAILED", "Synopsis processing did not complete."
                ),
            )
            return (
                "processing",
                blockers,
                WorkspaceAction(
                    "retry_processing",
                    "Retry synopsis processing",
                    target_id=processing.attempt_id,
                ),
            )
        if processing.status in {"pending", "processing"}:
            return (
                "processing",
                (
                    WorkspaceBlocker(
                        "PROCESSING_IN_PROGRESS", "Synopsis processing is in progress."
                    ),
                ),
                WorkspaceAction("refresh_workspace", "Refresh processing status"),
            )
        awaiting_facts = counts.candidate_facts + counts.conflicted_facts
        if awaiting_facts:
            return (
                "fact_review",
                (),
                WorkspaceAction(
                    "review_facts",
                    f"Review {awaiting_facts} candidate facts",
                    href=f"/studies/{study_id}/review",
                ),
            )
        if not passages:
            return (
                "passage_review",
                (),
                WorkspaceAction(
                    "generate_passages",
                    "Generate draft passages",
                    href=f"/studies/{study_id}/draft",
                ),
            )
        if passage_structure_blockers or any(status != "accepted" for _, status in passages):
            if passage_structure_blockers:
                passage_blockers = passage_structure_blockers
            elif counts.stale_passages:
                passage_blockers = (
                    WorkspaceBlocker(
                        "STALE_PASSAGE",
                        "One current draft passage is stale and must be regenerated."
                        if counts.stale_passages == 1
                        else "Current draft passages are stale and must be regenerated.",
                    ),
                )
            elif counts.blocked_passages:
                passage_blockers = (
                    WorkspaceBlocker(
                        "BLOCKED_PASSAGE",
                        "A current draft passage is blocked by validation findings.",
                    ),
                )
            elif counts.rejected_passages:
                passage_blockers = (
                    WorkspaceBlocker(
                        "REJECTED_PASSAGE",
                        "A rejected draft passage must be revised and accepted.",
                    ),
                )
            else:
                passage_blockers = (
                    WorkspaceBlocker(
                        "PASSAGE_REVIEW_INCOMPLETE",
                        "All four current draft passages must be accepted.",
                    ),
                )
            return (
                "passage_review",
                passage_blockers,
                WorkspaceAction(
                    "review_passages",
                    "Review draft passages",
                    href=f"/studies/{study_id}/draft",
                ),
            )
        if quality_blockers:
            return (
                "export",
                quality_blockers,
                WorkspaceAction(
                    "review_quality",
                    "Review export blockers",
                    href=f"/studies/{study_id}/draft",
                ),
            )
        if counts.exports:
            return (
                "export",
                (),
                WorkspaceAction(
                    "view_export", "View export artifacts", href=f"/studies/{study_id}/draft"
                ),
            )
        return (
            "export",
            (),
            WorkspaceAction(
                "create_export", "Create export", href=f"/studies/{study_id}/draft"
            ),
        )
