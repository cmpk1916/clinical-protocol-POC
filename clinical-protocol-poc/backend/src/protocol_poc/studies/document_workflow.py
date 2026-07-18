from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.files.models import FileRecord, FileVersion, StudyInput
from protocol_poc.ingest.service import IngestResult, IngestService, UploadInput
from protocol_poc.studies.document_contract import ContractFinding, DocumentContract
from protocol_poc.studies.local_extractor import (
    LOCAL_EXTRACTOR_VERSION,
    ExtractionFinding,
    LocalExtractor,
)
from protocol_poc.studies.models import Fact, FactVersion, ProcessingAttempt, now
from protocol_poc.studies.service import StudyService
from protocol_poc.tenancy import TenantContext, require_tenant_context


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    job_id: str
    file_id: str
    version_id: str
    version: int
    checksum_sha256: str
    status: str
    findings: tuple[ContractFinding, ...]
    current_file_version_id: str | None
    replacement_impact: tuple[str, ...] = ()

    @property
    def file_version_id(self) -> str:
        return self.version_id


@dataclass(frozen=True, slots=True)
class ProcessingOutcome:
    attempt_id: str
    status: str
    findings: tuple[ExtractionFinding, ...]
    synopsis_version_id: str
    extractor_version: str = LOCAL_EXTRACTOR_VERSION


class ProcessingNotFound(RuntimeError):
    pass


class ProcessingConflict(RuntimeError):
    pass


class DocumentWorkflowService:
    def __init__(
        self,
        session: Session,
        ingest: IngestService,
        contract: DocumentContract | None = None,
    ) -> None:
        self._session = session
        self._ingest = ingest
        self._contract = contract or DocumentContract()
        self._extractor = LocalExtractor()

    def upload(
        self, ctx: TenantContext, study_id: str, upload: UploadInput
    ) -> UploadOutcome:
        context = require_tenant_context(ctx)
        StudyService(self._session).require_active(context, study_id)
        result = self._ingest.ingest(context, study_id, upload)
        evidence = self._ingest.evidence_for_version(context, result.version_id)
        findings = (
            self._contract.validate_synopsis(evidence)
            if upload.role == "synopsis"
            else self._contract.validate_template(evidence)
        )
        current = self._session.scalar(
            select(StudyInput).where(
                StudyInput.tenant_id == context.tenant_id,
                StudyInput.study_id == study_id,
                StudyInput.role == upload.role,
            )
        )
        if findings:
            AuditService(self._session).append(
                context,
                "input.conformance_failed",
                "file_version",
                result.version_id,
                {
                    "role": upload.role,
                    "finding_codes": [finding.code for finding in findings],
                    "finding_fields": [finding.field for finding in findings],
                },
            )
            self._session.commit()
            return self._outcome(
                result,
                "conformance_failed",
                findings,
                current.current_file_version_id if current is not None else None,
            )
        if current is None:
            current = StudyInput(
                tenant_id=context.tenant_id,
                study_id=study_id,
                role=upload.role,
                current_file_version_id=result.version_id,
                conformance_status="conforming",
                revision=1,
            )
            self._session.add(current)
            self._session.flush()
            AuditService(self._session).append(
                context,
                "input.activated",
                "study_input",
                current.id,
                {
                    "role": upload.role,
                    "file_version_id": result.version_id,
                    "revision": current.revision,
                },
            )
            self._session.commit()
            return self._outcome(result, "activated", (), result.version_id)
        if current.current_file_version_id == result.version_id:
            return self._outcome(result, "activated", (), result.version_id)
        impact = self._replacement_impact(upload.role)
        AuditService(self._session).append(
            context,
            "input.replacement_previewed",
            "study_input",
            current.id,
            {
                "role": upload.role,
                "current_file_version_id": current.current_file_version_id,
                "proposed_file_version_id": result.version_id,
                "replacement_impact": list(impact),
            },
        )
        self._session.commit()
        return self._outcome(
            result,
            "replacement_confirmation_required",
            (),
            current.current_file_version_id,
            impact,
        )

    def process(
        self, ctx: TenantContext, study_id: str, file_version_id: str
    ) -> ProcessingOutcome:
        context = require_tenant_context(ctx)
        StudyService(self._session).require_active(context, study_id)
        current = self._session.scalar(
            select(StudyInput).where(
                StudyInput.tenant_id == context.tenant_id,
                StudyInput.study_id == study_id,
                StudyInput.role == "synopsis",
                StudyInput.current_file_version_id == file_version_id,
            )
        )
        version = self._session.scalar(
            select(FileVersion)
            .join(FileRecord, FileRecord.id == FileVersion.file_record_id)
            .where(
                FileVersion.id == file_version_id,
                FileVersion.tenant_id == context.tenant_id,
                FileRecord.study_id == study_id,
                FileRecord.role == "synopsis",
            )
        )
        if current is None or version is None:
            raise ProcessingNotFound("current synopsis version not found")
        active = self._session.scalar(
            select(ProcessingAttempt).where(
                ProcessingAttempt.tenant_id == context.tenant_id,
                ProcessingAttempt.study_id == study_id,
                ProcessingAttempt.synopsis_version_id == file_version_id,
                ProcessingAttempt.status.in_(("pending", "processing")),
            )
        )
        if active is not None:
            raise ProcessingConflict("processing is already active")
        existing = self._session.scalar(
            select(ProcessingAttempt).where(
                ProcessingAttempt.tenant_id == context.tenant_id,
                ProcessingAttempt.study_id == study_id,
                ProcessingAttempt.synopsis_version_id == file_version_id,
                ProcessingAttempt.status == "succeeded",
            )
        )
        if existing is not None:
            return self._processing_outcome(existing)
        return self._run_processing(context, study_id, file_version_id)

    def retry(
        self, ctx: TenantContext, study_id: str, attempt_id: str
    ) -> ProcessingOutcome:
        context = require_tenant_context(ctx)
        StudyService(self._session).require_active(context, study_id)
        attempt = self._session.scalar(
            select(ProcessingAttempt).where(
                ProcessingAttempt.id == attempt_id,
                ProcessingAttempt.tenant_id == context.tenant_id,
                ProcessingAttempt.study_id == study_id,
            )
        )
        if attempt is None:
            raise ProcessingNotFound("processing attempt not found")
        if attempt.status != "failed":
            raise ProcessingConflict("only failed attempts may be retried")
        current = self._session.scalar(
            select(StudyInput).where(
                StudyInput.tenant_id == context.tenant_id,
                StudyInput.study_id == study_id,
                StudyInput.role == "synopsis",
                StudyInput.current_file_version_id == attempt.synopsis_version_id,
            )
        )
        if current is None:
            raise ProcessingNotFound("processing attempt synopsis is no longer current")
        return self._run_processing(context, study_id, attempt.synopsis_version_id)

    def _run_processing(
        self, ctx: TenantContext, study_id: str, file_version_id: str
    ) -> ProcessingOutcome:
        evidence = self._ingest.evidence_for_version(ctx, file_version_id)
        proposal = self._extractor.extract(evidence)
        attempt = ProcessingAttempt(
            tenant_id=ctx.tenant_id,
            study_id=study_id,
            synopsis_version_id=file_version_id,
            extractor_name="local-rules",
            extractor_version=proposal.extractor_version,
            status="processing",
            findings_json=[],
        )
        self._session.add(attempt)
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ProcessingConflict("processing is already active") from error
        if proposal.findings:
            attempt.status = "failed"
            attempt.error_code = "extraction_findings"
            attempt.findings_json = [asdict(finding) for finding in proposal.findings]
            attempt.completed_at = now()
            AuditService(self._session).append(
                ctx,
                "synopsis.processing_failed",
                "processing_attempt",
                attempt.id,
                {"finding_codes": [finding.code for finding in proposal.findings]},
            )
            self._session.commit()
            return self._processing_outcome(attempt, proposal.findings)
        for candidate in proposal.candidates:
            fact = Fact(
                tenant_id=ctx.tenant_id,
                study_id=study_id,
                processing_attempt_id=attempt.id,
                kind=candidate.kind,
                status="candidate",
                critical=candidate.critical,
                current_version=1,
            )
            self._session.add(fact)
            self._session.flush()
            self._session.add(
                FactVersion(
                    tenant_id=ctx.tenant_id,
                    fact_id=fact.id,
                    version=1,
                    value_json=candidate.value_json,
                    confidence=candidate.confidence,
                    source_evidence_id=candidate.source_evidence_id,
                    is_current=True,
                )
            )
        attempt.status = "succeeded"
        attempt.completed_at = now()
        AuditService(self._session).append(
            ctx,
            "synopsis.processing_succeeded",
            "processing_attempt",
            attempt.id,
            {"candidate_count": len(proposal.candidates)},
        )
        self._session.commit()
        return self._processing_outcome(attempt)

    @staticmethod
    def _processing_outcome(
        attempt: ProcessingAttempt,
        findings: tuple[ExtractionFinding, ...] | None = None,
    ) -> ProcessingOutcome:
        if findings is None:
            findings = tuple(
                ExtractionFinding(item["code"], item["field"], item["message"])
                for item in attempt.findings_json
            )
        return ProcessingOutcome(
            attempt.id,
            attempt.status,
            findings,
            attempt.synopsis_version_id,
            attempt.extractor_version,
        )

    @staticmethod
    def _replacement_impact(role: str) -> tuple[str, ...]:
        if role == "synopsis":
            return (
                "supersede_current_facts",
                "invalidate_dependent_passages",
                "fact_review_required",
            )
        return ("preserve_facts_and_passage_reviews", "block_export_until_confirmed")

    @staticmethod
    def _outcome(
        result: IngestResult,
        status: str,
        findings: tuple[ContractFinding, ...],
        current_file_version_id: str | None,
        impact: tuple[str, ...] = (),
    ) -> UploadOutcome:
        return UploadOutcome(
            job_id=result.job_id,
            file_id=result.file_id,
            version_id=result.version_id,
            version=result.version,
            checksum_sha256=result.checksum_sha256,
            status=status,
            findings=findings,
            current_file_version_id=current_file_version_id,
            replacement_impact=impact,
        )
