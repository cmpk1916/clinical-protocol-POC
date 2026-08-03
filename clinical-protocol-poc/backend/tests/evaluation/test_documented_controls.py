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
        "six_study_reliability",
    }

    assert required <= {control.control_id for control in controls}
    assert all(control.test_ids and control.module_owner for control in controls)
    reliability = next(
        control for control in controls
        if control.control_id == "six_study_reliability"
    )
    assert reliability.module_owner == "protocol_poc.reliability"
    assert {
        "tests/integration/reliability/test_six_study_pilot.py",
        "tests/unit/reliability/test_report.py",
        "tests/unit/reliability/test_cli.py",
    } <= set(reliability.test_ids)


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


def test_reliability_pilot_documents_stable_controls_and_non_claims() -> None:
    document_path = Path(__file__).parents[3] / "docs" / "reliability-pilot.md"
    document = document_path.read_text()
    required = {
        "six synthetic self-service studies",
        "three direct-success studies",
        "three mistake-and-recovery studies",
        "SYNOPSIS_DOSE_MISSING",
        "TEMPLATE_TOKEN_MISSING",
        "UNSUPPORTED_DOSE",
        "two clean-stack runs",
        "unsupported clinical facts exported: 0",
        "passed both clean stacks at 6 of 6 studies",
        "all three pre-correction denials",
        "deterministic repeatability comparison with no mismatches",
        "synthetic POC reliability evidence only",
        "not system validation",
        (
            "does not establish a clinical, regulatory, submission, operational, "
            "production, or readiness claim"
        ),
    }
    forbidden_claims = {
        "clinically ready",
        "clinical readiness",
        "regulatorily ready",
        "regulatory readiness",
        "submission ready",
        "submission readiness",
        "operationally ready",
        "operational readiness",
        "production ready",
        "production readiness",
        "validated system",
    }

    assert all(item in document for item in required)
    assert "readiness percentage" not in document.casefold()
    assert all(claim not in document.casefold() for claim in forbidden_claims)


def test_guided_review_workspace_is_documented_and_local_only() -> None:
    app_root = Path(__file__).parents[3]
    repository_root = app_root.parent
    review_readme = (app_root / "docs" / "guided-review" / "README.md").read_text()
    gitignore = (repository_root / ".gitignore").read_text()

    required = {
        "presenter-controlled virtual review",
        "synthetic proof of concept",
        "system-validation readiness",
        "fixtures/reliability-pilot/standard/",
        "fixtures/reliability-pilot/missing-dose/",
        "work/guided-review/",
        "completed reviewer records remain local",
        "may be recorded only with explicit reviewer permission",
        "separate direct observations from interpretation and feature requests",
        "no public link",
        "no remote control",
    }

    assert all(item in review_readme for item in required)
    assert "clinical-protocol-poc/work/guided-review/" in gitignore


def test_guided_review_presenter_materials_cover_both_workflows() -> None:
    review_root = Path(__file__).parents[3] / "docs" / "guided-review"
    guide = (review_root / "presenter-guide.md").read_text()
    preflight = (review_root / "preflight-checklist.md").read_text()
    combined = f"{guide}\n{preflight}"

    required = {
        "35 to 45 minutes",
        "Opening: 5 minutes",
        "Successful workflow: 10 to 15 minutes",
        "Mistake and recovery: 10 minutes",
        "Role-specific discussion: 10 to 15 minutes",
        "protocol.docx",
        "traceability.csv",
        "scorecard.html",
        "corrected-synopsis.docx",
        "Do not upload any document supplied by a reviewer",
        "Do not conceal unexpected behavior",
        "Do not record the call without explicit permission",
    }

    assert all(item in combined for item in required)
