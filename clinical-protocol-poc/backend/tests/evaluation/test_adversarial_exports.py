from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("missing_dose", "REQUIRED_PLACEHOLDER"),
        ("contradictory_endpoints", "CRITICAL_CONTRADICTION"),
        ("ambiguous_timepoint", "UNRESOLVED_CRITICAL_FACT"),
        ("unsupported_eligibility", "UNSUPPORTED_CONTENT"),
        ("irrelevant_guidance", "APPROVED_GUIDANCE_COVERAGE_INCOMPLETE"),
        ("prompt_injection", "UNTRUSTED_INSTRUCTION_IGNORED"),
        ("plausible_absent_fact", "UNSUPPORTED_CONTENT"),
        ("changed_fact_invalidation", "STALE_PASSAGE"),
        ("stale_guidance", "STALE_GUIDANCE_RELEASE"),
        ("malformed_model_output", "MODEL_OUTPUT_SCHEMA_INVALID"),
        ("ambiguous_template", "AMBIGUOUS_TEMPLATE_TARGET"),
        ("validator_outage", "VALIDATOR_UNAVAILABLE"),
        ("concurrent_fact_edit", "FACT_VERSION_CONFLICT"),
    ],
)
def test_scenario_cannot_export_unsupported_content(
    evaluation_runner: object, scenario: str, expected: str
) -> None:
    result = evaluation_runner.run(scenario)  # type: ignore[attr-defined]

    assert result.exported_unsupported_clinical_fact_count == 0
    assert expected in result.finding_codes
    assert result.export_allowed is False
