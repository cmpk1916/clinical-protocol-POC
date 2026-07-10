from protocol_poc.validation.clinical_values import ApprovedClinicalModel
from protocol_poc.validation.findings import Finding
from protocol_poc.validation.service import PassageValidator


def test_semantic_review_cannot_dismiss_deterministic_blocker() -> None:
    approved = ApprovedClinicalModel(doses={("10", "mg")})
    semantic = [Finding(code="UNSUPPORTED_DOSE", severity="info", message="Looks acceptable", source="semantic")]

    findings = PassageValidator().validate_text("Dose is 20 mg.", approved, semantic_findings=semantic)

    assert any(item.code == "UNSUPPORTED_DOSE" and item.severity == "blocker" and item.source == "deterministic" for item in findings)
