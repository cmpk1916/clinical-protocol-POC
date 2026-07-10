import pytest

from protocol_poc.validation.clinical_values import ApprovedClinicalModel, normalize_decimal
from protocol_poc.validation.service import PassageValidator


@pytest.mark.parametrize("text,code", [
    ("Participants receive 20 mg daily.", "UNSUPPORTED_DOSE"),
    ("The primary endpoint is assessed at Week 24.", "TIMEPOINT_MISMATCH"),
    ("Adults aged 18 to 75 years are eligible.", "UNSUPPORTED_ELIGIBILITY"),
])
def test_unsupported_clinical_values_are_blockers(text: str, code: str) -> None:
    approved = ApprovedClinicalModel(doses={("10", "mg")}, timepoints={12}, age_ranges={(18, 65)})
    findings = PassageValidator().validate_text(text, approved)
    assert any(finding.code == code and finding.severity == "blocker" for finding in findings)


def test_decimal_normalization_is_deterministic() -> None:
    assert normalize_decimal("10.0") == "10"
    assert normalize_decimal("0.500") == "0.5"


def test_ucum_compatible_dose_units_compare_in_canonical_units() -> None:
    approved = ApprovedClinicalModel(doses={("1000", "mg")})
    findings = PassageValidator().validate_text("Participants receive 1 g daily.", approved)
    assert not any(item.code == "UNSUPPORTED_DOSE" for item in findings)


def test_unsupported_duration_is_blocker() -> None:
    approved = ApprovedClinicalModel(durations={(12, "wk")})
    findings = PassageValidator().validate_text("Treatment continues for 24 weeks.", approved)
    assert any(item.code == "DURATION_MISMATCH" and item.severity == "blocker" for item in findings)
