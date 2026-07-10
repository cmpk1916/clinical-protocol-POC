from collections.abc import Iterable

from protocol_poc.validation.clinical_values import ApprovedClinicalModel, validate_clinical_values
from protocol_poc.validation.findings import Finding


class PassageValidator:
    def validate_text(
        self,
        text: str,
        approved: ApprovedClinicalModel,
        *,
        semantic_findings: Iterable[Finding] = (),
    ) -> list[Finding]:
        try:
            deterministic = validate_clinical_values(text, approved)
        except Exception:
            deterministic = [Finding("VALIDATOR_EXCEPTION", "blocker", "Deterministic validation failed closed")]
        return [*deterministic, *semantic_findings]
