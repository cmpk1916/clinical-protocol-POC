from __future__ import annotations

import json

from protocol_poc.reliability.report import (
    compare_repeatability,
    render_json,
    render_markdown,
)
from protocol_poc.reliability.results import (
    ArtifactResult,
    CheckResult,
    PilotRunResult,
    StudyRunResult,
)


def _study(
    study_key: str,
    *,
    study_id: str,
    snapshot_id: str,
    passage: str = "Synthetic passage.",
    mismatch: bool = False,
) -> StudyRunResult:
    checks = (
        CheckResult("workflow.complete", True, True, True),
        CheckResult(
            "processing.blockers",
            not mismatch,
            "SYNOPSIS_DOSE_MISSING" if mismatch else (),
            "PROCESSING_FAILED" if mismatch else (),
        ),
        CheckResult(
            "artifact.protocol.docx.sha256",
            True,
            f"expected-{study_id}",
            f"actual-{study_id}",
            volatile=True,
        ),
    )
    return StudyRunResult(
        study_key,
        checks,
        initial_export_denied=mismatch,
        input_history=({
            "role": "synopsis",
            "filename": "synopsis.docx",
            "version": 1,
            "status": "activated",
            "checksum_sha256": f"input-{study_id}",
        },),
        facts=({"kind": "dose", "value": {"value": "10", "unit": "mg"}},),
        passages={"synopsis": passage},
        artifacts=(ArtifactResult(
            "protocol.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"artifact-{study_id}",
            snapshot_id,
            123,
        ),),
        study_id=study_id,
        snapshot_id=snapshot_id,
    )


def test_reports_include_full_evidence_and_exact_safety_language() -> None:
    result = PilotRunResult((
        _study("standard", study_id="study-a", snapshot_id="snapshot-a"),
        _study(
            "missing-dose",
            study_id="study-b",
            snapshot_id="snapshot-b",
            mismatch=True,
        ),
    ))

    markdown = render_markdown(result)
    payload = json.loads(render_json(result))

    assert "unsupported clinical facts exported: 0" in markdown
    assert "Expected: SYNOPSIS_DOSE_MISSING" in markdown
    assert "Actual: PROCESSING_FAILED" in markdown
    assert "input-study-a" in markdown
    assert "snapshot-a" in markdown
    assert "artifact-study-a" in markdown
    assert payload["studies"][1]["checks"][1]["passed"] is False
    assert payload["studies"][0]["study_id"] == "study-a"
    assert payload["studies"][0]["artifacts"][0]["sha256"] == "artifact-study-a"
    assert render_json(result) == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    for forbidden in (
        "clinical readiness",
        "regulatory readiness",
        "submission readiness",
        "readiness percentage",
    ):
        assert forbidden not in markdown.casefold()
    assert "%" not in markdown


def test_markdown_renders_blocker_version_and_passage_status_evidence() -> None:
    study = StudyRunResult(
        "broken-template",
        (
            CheckResult("template.status", True, "conformance_failed", "conformance_failed"),
            CheckResult(
                "template.findings",
                True,
                (("TEMPLATE_TOKEN_MISSING", "eligibility"),),
                (("TEMPLATE_TOKEN_MISSING", "eligibility"),),
            ),
            CheckResult(
                "input.current_versions",
                True,
                {"synopsis": 1, "template": 2},
                {"synopsis": 1, "template": 2},
            ),
            CheckResult("passage.study_design.blocked_status", True, "blocked", "blocked"),
            CheckResult("passage.study_design.final_status", True, "accepted", "accepted"),
        ),
        input_history=(
            {"role": "template", "filename": "template.docx", "version": 1},
            {"role": "template", "filename": "corrected-template.docx", "version": 2},
        ),
    )

    markdown = render_markdown(PilotRunResult((study,)))

    for evidence_name in (
        "template.status",
        "template.findings",
        "input.current_versions",
        "passage.study_design.blocked_status",
        "passage.study_design.final_status",
    ):
        assert evidence_name in markdown
    assert "TEMPLATE_TOKEN_MISSING" in markdown
    assert '"template": 2' in markdown


def test_repeatability_ignores_run_specific_ids_and_hashes() -> None:
    first = PilotRunResult((
        _study("standard", study_id="study-a", snapshot_id="snapshot-a"),
    ))
    second = PilotRunResult((
        _study("standard", study_id="study-b", snapshot_id="snapshot-b"),
    ))

    checks = compare_repeatability(first, second)

    assert checks
    assert all(check.passed for check in checks)


def test_repeatability_names_single_changed_passage_field() -> None:
    first = PilotRunResult((
        _study("standard", study_id="study-a", snapshot_id="snapshot-a"),
    ))
    second = PilotRunResult((
        _study(
            "standard",
            study_id="study-b",
            snapshot_id="snapshot-b",
            passage="Changed synthetic passage.",
        ),
    ))

    failed = [
        check for check in compare_repeatability(first, second) if not check.passed
    ]

    assert len(failed) == 1
    assert failed[0].name == "repeatability.standard.passages"
    assert failed[0].expected == {"synopsis": "Synthetic passage."}
    assert failed[0].actual == {"synopsis": "Changed synthetic passage."}


def test_repeatability_check_order_is_deterministic() -> None:
    first = PilotRunResult((
        _study("zeta", study_id="first-z", snapshot_id="first-z"),
        _study("alpha", study_id="first-a", snapshot_id="first-a"),
    ))
    second = PilotRunResult((
        _study("zeta", study_id="second-z", snapshot_id="second-z"),
        _study("alpha", study_id="second-a", snapshot_id="second-a"),
    ))

    names = [check.name for check in compare_repeatability(first, second)][3:]

    alpha = [name for name in names if name.startswith("repeatability.alpha.")]
    zeta = [name for name in names if name.startswith("repeatability.zeta.")]
    assert names == alpha + zeta
    assert alpha == sorted(alpha)
    assert zeta == sorted(zeta)
