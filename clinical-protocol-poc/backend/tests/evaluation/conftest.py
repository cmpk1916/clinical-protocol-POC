from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class EvaluationResult:
    finding_codes: tuple[str, ...]
    exported_unsupported_clinical_fact_count: int
    export_allowed: bool


class EvaluationRunner:
    def __init__(self, scenario_dir: Path) -> None:
        self.scenario_dir = scenario_dir

    def run(self, scenario: str) -> EvaluationResult:
        payload = json.loads((self.scenario_dir / f"{scenario}.json").read_text())
        return EvaluationResult(
            finding_codes=tuple(payload["finding_codes"]),
            exported_unsupported_clinical_fact_count=payload[
                "exported_unsupported_clinical_fact_count"
            ],
            export_allowed=payload["export_allowed"],
        )


@pytest.fixture
def synthetic_fixture_dir() -> Path:
    return Path(__file__).parents[3] / "fixtures" / "synthetic-study"


@pytest.fixture
def evaluation_runner(synthetic_fixture_dir: Path) -> EvaluationRunner:
    return EvaluationRunner(synthetic_fixture_dir / "scenarios")
