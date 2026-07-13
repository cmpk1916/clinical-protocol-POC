from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class DocumentedControl:
    control_id: str
    module_owner: str
    test_ids: tuple[str, ...]


def _load_controls(safety_case_path: Path) -> list[DocumentedControl]:
    controls: list[DocumentedControl] = []
    for line in safety_case_path.read_text().splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 6:
            continue
        controls.append(
            DocumentedControl(
                control_id=cells[0].strip("`"),
                module_owner=cells[3].strip("`"),
                test_ids=tuple(
                    test_id.strip().strip("`")
                    for test_id in cells[4].split(",")
                    if test_id.strip()
                ),
            )
        )
    return controls


def test_every_safety_invariant_has_control_test_and_owner() -> None:
    safety_case_path = Path(__file__).parents[3] / "docs" / "safety-case.md"
    controls = _load_controls(safety_case_path)
    required = {
        "no_unsupported_export",
        "critical_fact_confirmation",
        "claim_provenance",
        "fact_change_invalidation",
        "validator_failure_closed",
        "tenant_isolation",
    }

    assert required <= {control.control_id for control in controls}
    assert all(control.test_ids and control.module_owner for control in controls)


def test_release_checklist_records_artifact_and_visual_evidence() -> None:
    checklist_path = Path(__file__).parents[3] / "docs" / "release-checklist.md"
    checklist = checklist_path.read_text()

    assert all(
        artifact in checklist
        for artifact in ("protocol.docx", "traceability.csv", "scorecard.html")
    )
    assert "Shared snapshot ID:" in checklist
    assert len(re.findall(r"\b[a-f0-9]{64}\b", checklist)) == 3
    assert "DOCX visual inspection: PASS" in checklist
    assert "synthetic data only" in checklist.lower()
    assert "not a validated system" in checklist.lower()
