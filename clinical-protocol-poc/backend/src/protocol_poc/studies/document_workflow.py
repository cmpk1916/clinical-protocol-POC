from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.files.models import FileRecord, FileVersion, SourceEvidence, StudyInput
from protocol_poc.ingest.service import IngestResult, IngestService, UploadInput
from protocol_poc.studies.document_contract import ContractFinding, DocumentContract
from protocol_poc.studies.local_extractor import (
    LOCAL_EXTRACTOR_VERSION,
    ExtractionFinding,
    ExtractionProposal,
    LocalExtractor,
)
from protocol_poc.studies.models import (
    Fact,
    FactVersion,
    ProcessingAttempt,
    complete_processing_attempt,
)
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
        attempt = ProcessingAttempt(
            tenant_id=ctx.tenant_id,
            study_id=study_id,
            synopsis_version_id=file_version_id,
            extractor_name="local-rules",
            extractor_version=LOCAL_EXTRACTOR_VERSION,
            status="processing",
            findings_json=[],
        )
        self._session.add(attempt)
        try:
            # Commit the active claim before reading evidence or running extraction.
            # The partial unique index then protects the expensive portion of work.
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ProcessingConflict("processing is already active") from error

        try:
            evidence = self._ingest.evidence_for_version(ctx, file_version_id)
        except Exception:
            return self._fail_attempt(
                ctx,
                attempt,
                "evidence_load_failed",
                ExtractionFinding(
                    "PROCESSING_EVIDENCE_LOAD_FAILED",
                    "synopsis",
                    "Synopsis evidence could not be loaded for deterministic processing.",
                ),
            )
        try:
            proposal = self._extractor.extract(evidence)
        except Exception:
            return self._fail_attempt(
                ctx,
                attempt,
                "extractor_failed",
                ExtractionFinding(
                    "PROCESSING_EXTRACTOR_FAILED",
                    "synopsis",
                    "The deterministic synopsis extractor could not complete.",
                ),
            )

        provenance_finding = self._validate_provenance(
            ctx, file_version_id, evidence, proposal
        )
        if provenance_finding is not None:
            return self._fail_attempt(
                ctx,
                attempt,
                "invalid_evidence_provenance",
                provenance_finding,
            )
        if proposal.findings:
            return self._fail_attempt(
                ctx, attempt, "extraction_findings", *proposal.findings
            )

        current = self._session.scalar(
            select(StudyInput)
            .where(
                StudyInput.tenant_id == ctx.tenant_id,
                StudyInput.study_id == study_id,
                StudyInput.role == "synopsis",
            )
            .with_for_update()
        )
        if current is None or current.current_file_version_id != file_version_id:
            return self._fail_attempt(
                ctx,
                attempt,
                "synopsis_no_longer_current",
                ExtractionFinding(
                    "PROCESSING_SYNOPSIS_NO_LONGER_CURRENT",
                    "synopsis",
                    "The synopsis changed before extracted candidates could be persisted.",
                ),
            )

        evidence_by_id = {item.id: item for item in evidence}
        try:
            self._persist_candidates(
                ctx,
                study_id,
                attempt,
                proposal,
                evidence_by_id,
            )
            complete_processing_attempt(
                self._session,
                attempt,
                status="succeeded",
                error_code=None,
                findings_json=[],
            )
            AuditService(self._session).append(
                ctx,
                "synopsis.processing_succeeded",
                "processing_attempt",
                attempt.id,
                {"candidate_count": len(proposal.candidates)},
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            persisted_attempt = self._session.get(ProcessingAttempt, attempt.id)
            if persisted_attempt is None:
                raise
            return self._fail_attempt(
                ctx,
                persisted_attempt,
                "candidate_persistence_failed",
                ExtractionFinding(
                    "PROCESSING_CANDIDATE_PERSISTENCE_FAILED",
                    "synopsis",
                    "Extracted candidates could not be persisted atomically.",
                ),
            )
        return self._processing_outcome(attempt)

    def _persist_candidates(
        self,
        ctx: TenantContext,
        study_id: str,
        attempt: ProcessingAttempt,
        proposal: ExtractionProposal,
        evidence_by_id: dict[str, SourceEvidence],
    ) -> None:
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
                    source_evidence_version_id=evidence_by_id[
                        candidate.source_evidence_id
                    ].file_version_id,
                    is_current=True,
                )
            )

    def _fail_attempt(
        self,
        ctx: TenantContext,
        attempt: ProcessingAttempt,
        error_code: str,
        *findings: ExtractionFinding,
    ) -> ProcessingOutcome:
        complete_processing_attempt(
            self._session,
            attempt,
            status="failed",
            error_code=error_code,
            findings_json=[asdict(finding) for finding in findings],
        )
        AuditService(self._session).append(
            ctx,
            "synopsis.processing_failed",
            "processing_attempt",
            attempt.id,
            {"finding_codes": [finding.code for finding in findings]},
        )
        self._session.commit()
        return self._processing_outcome(attempt, tuple(findings))

    @staticmethod
    def _validate_provenance(
        ctx: TenantContext,
        file_version_id: str,
        evidence: tuple[SourceEvidence, ...],
        proposal: ExtractionProposal,
    ) -> ExtractionFinding | None:
        evidence_by_id = {item.id: item for item in evidence}
        evidence_is_exact = all(
            item.tenant_id == ctx.tenant_id
            and item.file_version_id == file_version_id
            for item in evidence
        )
        candidate_ids_are_exact = all(
            candidate.source_evidence_id in evidence_by_id
            for candidate in proposal.candidates
        )
        if evidence_is_exact and candidate_ids_are_exact:
            return None
        return ExtractionFinding(
            "PROCESSING_EVIDENCE_PROVENANCE_INVALID",
            "synopsis",
            "Candidate evidence must belong to the exact processed synopsis version.",
        )

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
