from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.files.models import StudyInput
from protocol_poc.ingest.service import IngestResult, IngestService, UploadInput
from protocol_poc.studies.document_contract import ContractFinding, DocumentContract
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
