from dataclasses import dataclass

from protocol_poc.studies.local_extractor import LOCAL_EXTRACTOR_VERSION, LocalExtractor


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
        "intervention", "dose", "population", "eligibility",
    }
    dose = next(item for item in proposal.candidates if item.kind == "dose")
    assert dose.value_json == {
        "kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"
    }
    assert dose.source_evidence_id == "arms-line-1"
    endpoint = next(item for item in proposal.candidates if item.kind == "endpoint")
    timepoint = next(item for item in proposal.candidates if item.kind == "timepoint")
    assert endpoint.source_evidence_id == timepoint.source_evidence_id == "endpoints-line-1"
    assert proposal.extractor_version == LOCAL_EXTRACTOR_VERSION == "local-rules-v1"


def test_ambiguous_heading_returns_stable_finding_and_no_candidates() -> None:
    evidence = supported_synopsis_evidence() + (Evidence("objectives-heading-2", "Objectives"),)
    proposal = LocalExtractor().extract(evidence)
    assert proposal.candidates == ()
    assert [(item.code, item.field) for item in proposal.findings] == [
        ("SYNOPSIS_HEADING_AMBIGUOUS", "objectives")
    ]


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
