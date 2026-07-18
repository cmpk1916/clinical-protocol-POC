from dataclasses import dataclass

from protocol_poc.studies.document_contract import DocumentContract


@dataclass(frozen=True)
class EvidenceItem:
    text: str


def evidence(*lines: str) -> tuple[EvidenceItem, ...]:
    return tuple(EvidenceItem(line) for line in lines)


def test_template_requires_each_allowlisted_token_once() -> None:
    valid = evidence(
        "[[SECTION:synopsis]]",
        "[[SECTION:objectives_endpoints]]",
        "[[SECTION:study_design]]",
        "[[SECTION:eligibility]]",
        "[[POC_DISCLAIMER]]",
    )
    assert DocumentContract().validate_template(valid) == ()

    duplicate = (*valid, EvidenceItem("[[SECTION:synopsis]]"))
    assert [finding.code for finding in DocumentContract().validate_template(duplicate)] == [
        "TEMPLATE_TOKEN_DUPLICATE"
    ]


def test_template_reports_missing_tokens_in_allowlist_order() -> None:
    findings = DocumentContract().validate_template(evidence("[[SECTION:synopsis]]"))

    assert [finding.field for finding in findings] == [
        "objectives_endpoints",
        "study_design",
        "eligibility",
        "poc_disclaimer",
    ]
    assert {finding.code for finding in findings} == {"TEMPLATE_TOKEN_MISSING"}


def test_synopsis_reports_all_missing_sections() -> None:
    findings = DocumentContract().validate_synopsis(
        evidence("Study identity", "Short title: SYN-1")
    )

    assert {finding.field for finding in findings} == {
        "objectives",
        "endpoints",
        "arms_interventions",
        "population",
        "eligibility",
    }


def test_synopsis_recognizes_supported_headings_and_fields_case_insensitively() -> None:
    supported = evidence(
        "  STUDY   IDENTITY ",
        "short TITLE: SYN-1",
        "Objectives",
        "Objective: Evaluate response",
        "ENDPOINTS",
        "Endpoint: Response at Week 8",
        "Arms and Interventions",
        "Arm: Experimental; Intervention: Example drug 10 mg once daily",
        "Study Population",
        "Population: Adults with synthetic condition",
        "Eligibility Criteria",
        "Eligibility: Age 18 years or older",
    )

    assert DocumentContract().validate_synopsis(supported) == ()
