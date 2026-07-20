from dataclasses import dataclass

import pytest

from protocol_poc.studies.local_extractor import (
    LOCAL_EXTRACTOR_VERSION,
    ExtractionProposal,
    LocalExtractor,
)


@dataclass(frozen=True)
class Evidence:
    id: str
    text: str


def supported_synopsis_evidence() -> tuple[Evidence, ...]:
    lines = (
        ("identity-heading", "Study Identity"),
        ("identity-line-1", "Short title: SYN-1"),
        ("objectives-heading", "Objectives"),
        ("objectives-line-1", "Objective: Evaluate response"),
        ("endpoints-heading", "Endpoints"),
        ("endpoints-line-1", "Endpoint: Response at Week 8"),
        ("arms-heading", "Arms and Interventions"),
        ("arms-line-1", "Arm: Experimental; Intervention: Example drug 10 mg once daily"),
        ("duration-line-1", "Duration: 24 weeks"),
        ("population-heading", "Study Population"),
        ("population-line-1", "Population: Adults with synthetic condition"),
        ("eligibility-heading", "Eligibility Criteria"),
        ("eligibility-line-1", "Eligibility: Age 18 years or older"),
    )
    return tuple(Evidence(item_id, text) for item_id, text in lines)


def test_extracts_required_facts_with_exact_evidence_ids() -> None:
    proposal = LocalExtractor().extract(supported_synopsis_evidence())
    assert proposal.findings == ()
    assert {item.kind for item in proposal.candidates} >= {
        "study_identity", "objective", "endpoint", "timepoint", "arm",
        "intervention", "dose", "duration", "population", "eligibility",
    }
    dose = next(item for item in proposal.candidates if item.kind == "dose")
    assert dose.value_json == {
        "kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"
    }
    assert dose.source_evidence_id == "arms-line-1"
    endpoint = next(item for item in proposal.candidates if item.kind == "endpoint")
    timepoint = next(item for item in proposal.candidates if item.kind == "timepoint")
    assert endpoint.source_evidence_id == timepoint.source_evidence_id == "endpoints-line-1"
    duration = next(item for item in proposal.candidates if item.kind == "duration")
    assert duration.value_json == {"kind": "string", "value": "24 weeks"}
    assert duration.source_evidence_id == "duration-line-1"
    assert proposal.extractor_version == LOCAL_EXTRACTOR_VERSION == "local-rules-v1"


def test_ambiguous_heading_returns_stable_finding_and_no_candidates() -> None:
    evidence = supported_synopsis_evidence() + (Evidence("objectives-heading-2", "Objectives"),)
    proposal = LocalExtractor().extract(evidence)
    assert proposal.candidates == ()
    assert [(item.code, item.field) for item in proposal.findings] == [
        ("SYNOPSIS_HEADING_DUPLICATE", "objectives")
    ]


@pytest.mark.parametrize(
    ("original", "alternative"),
    [
        ("Arms and Interventions", "Arms / Interventions"),
        ("Study Population", "Population"),
        ("Eligibility Criteria", "Eligibility"),
    ],
)
def test_accepts_every_supported_document_contract_heading(
    original: str, alternative: str
) -> None:
    evidence = tuple(
        Evidence(item.id, alternative if item.text == original else item.text)
        for item in supported_synopsis_evidence()
    )

    assert LocalExtractor().extract(evidence).findings == ()


def test_distinct_supported_headings_for_one_field_are_ambiguous() -> None:
    evidence = supported_synopsis_evidence() + (
        Evidence("population-heading-2", "Population"),
    )

    proposal = LocalExtractor().extract(evidence)

    assert proposal.candidates == ()
    assert [(item.code, item.field) for item in proposal.findings] == [
        ("SYNOPSIS_HEADING_AMBIGUOUS", "population")
    ]


def test_missing_supported_heading_has_stable_finding() -> None:
    evidence = tuple(
        item for item in supported_synopsis_evidence() if item.id != "objectives-heading"
    )

    proposal = LocalExtractor().extract(evidence)

    assert proposal.candidates == ()
    assert [(item.code, item.field) for item in proposal.findings] == [
        ("SYNOPSIS_HEADING_MISSING", "objectives")
    ]


def test_unsupported_heading_is_reported_with_the_missing_canonical_heading() -> None:
    evidence = tuple(
        Evidence(item.id, "Goals" if item.id == "objectives-heading" else item.text)
        for item in supported_synopsis_evidence()
    )

    proposal = LocalExtractor().extract(evidence)

    assert [(item.code, item.field) for item in proposal.findings] == [
        ("SYNOPSIS_HEADING_UNSUPPORTED", "synopsis"),
        ("SYNOPSIS_HEADING_MISSING", "objectives"),
    ]


def test_extraction_proposal_rejects_empty_result() -> None:
    with pytest.raises(ValueError, match="candidates or findings"):
        ExtractionProposal((), ())


def test_missing_dose_on_intervention_line_returns_finding_and_no_partial_candidates() -> None:
    evidence = tuple(
        Evidence(item.id, item.text.replace(" 10 mg once daily", ""))
        for item in supported_synopsis_evidence()
    )
    proposal = LocalExtractor().extract(evidence)
    assert proposal.candidates == ()
    assert [(item.code, item.field) for item in proposal.findings] == [
        ("SYNOPSIS_DOSE_MISSING", "arms_interventions")
    ]


def test_missing_or_ambiguous_duration_returns_no_partial_candidates() -> None:
    missing = tuple(item for item in supported_synopsis_evidence() if item.id != "duration-line-1")
    ambiguous = supported_synopsis_evidence() + (Evidence("duration-line-2", "Duration: 12 weeks"),)

    assert [(item.code, item.field) for item in LocalExtractor().extract(missing).findings] == [
        ("SYNOPSIS_VALUE_MISSING", "duration")
    ]
    assert [(item.code, item.field) for item in LocalExtractor().extract(ambiguous).findings] == [
        ("SYNOPSIS_VALUE_AMBIGUOUS", "duration")
    ]


def test_headings_and_labels_are_case_insensitive_and_whitespace_normalized() -> None:
    evidence = tuple(
        Evidence(
            item.id,
            item.text.lower()
            .replace("short title:", "  SHORT   TITLE :  ")
            .replace("objective: evaluate response", " OBJECTIVE : evaluate   response "),
        )
        for item in supported_synopsis_evidence()
    )

    proposal = LocalExtractor().extract(evidence)

    assert proposal.findings == ()
    identity = next(item for item in proposal.candidates if item.kind == "study_identity")
    assert identity.value_json == {"kind": "string", "value": "syn-1"}
    objective = next(item for item in proposal.candidates if item.kind == "objective")
    assert objective.value_json == {"kind": "string", "value": "evaluate response"}
