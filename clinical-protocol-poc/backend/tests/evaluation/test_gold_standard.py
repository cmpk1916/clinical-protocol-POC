from __future__ import annotations

import json
from pathlib import Path


def test_gold_standard_contains_stable_required_facts(synthetic_fixture_dir: Path) -> None:
    payload = json.loads((synthetic_fixture_dir / "gold-facts.json").read_text())
    fact_ids = {fact["id"] for fact in payload["facts"]}
    required = {
        "study.identity.short_title",
        "study.objective.primary",
        "study.endpoint.primary",
        "study.timepoint.week_24",
        "study.arm.active",
        "study.intervention.synthetic_a",
        "study.intervention.synthetic_a.dose",
        "study.population.adults",
        "study.eligibility.age",
        "study.eligibility.diagnosis",
    }

    assert required <= fact_ids
    assert all(fact["location"].startswith("Synopsis >") for fact in payload["facts"])
    assert payload["review"]["reviewer_role"] == "qualified medical writer"
    assert payload["review"]["reviewed_on"]
    assert payload["fixture_version"]


def test_synthetic_docx_inputs_exist(synthetic_fixture_dir: Path) -> None:
    assert (synthetic_fixture_dir / "synopsis.docx").is_file()
    assert (synthetic_fixture_dir / "template.docx").is_file()
