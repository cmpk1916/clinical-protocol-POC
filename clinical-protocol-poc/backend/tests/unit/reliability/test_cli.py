from __future__ import annotations

import json
from pathlib import Path

import pytest

from protocol_poc.reliability import cli
from protocol_poc.reliability.report import render_json
from protocol_poc.reliability.results import CheckResult, PilotRunResult, StudyRunResult


def _passing_result(prefix: str = "run") -> PilotRunResult:
    return PilotRunResult(tuple(
        StudyRunResult(
            f"study-{index}",
            (CheckResult("workflow.complete", True, True, True),),
            passages={"synopsis": "Synthetic passage."},
            study_id=f"{prefix}-study-{index}",
            snapshot_id=f"{prefix}-snapshot-{index}",
        )
        for index in range(6)
    ))


def test_run_command_writes_reports_atomically_and_reports_acceptance(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        cli, "run_pilot", lambda _base_url, _fixtures: _passing_result()
    )

    exit_code = cli.main([
        "run",
        "--base-url", "http://example.test",
        "--fixtures", str(tmp_path / "fixtures"),
        "--output", str(tmp_path / "reports"),
        "--run-label", "run-a",
    ])

    output = tmp_path / "reports"
    assert exit_code == 0
    assert json.loads((output / "run-a.json").read_text())["passed"] is True
    assert (output / "run-a.md").read_text().startswith(
        "# Six-Study Synthetic Reliability Pilot"
    )
    assert list(output.glob("*.tmp")) == []
    printed = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Studies passed: 6 of 6" in printed
    assert "unsupported clinical facts exported: 0" in printed


def test_run_command_returns_failure_unless_exactly_six_studies_pass(
    tmp_path: Path, monkeypatch: object
) -> None:
    incomplete = PilotRunResult(_passing_result().studies[:5])
    monkeypatch.setattr(  # type: ignore[attr-defined]
        cli, "run_pilot", lambda _base_url, _fixtures: incomplete
    )

    exit_code = cli.main([
        "run",
        "--base-url", "http://example.test",
        "--fixtures", str(tmp_path / "fixtures"),
        "--output", str(tmp_path / "reports"),
        "--run-label", "incomplete",
    ])

    assert exit_code == 1
    assert (tmp_path / "reports" / "incomplete.json").is_file()


def test_run_command_fails_when_unsupported_content_was_exported(
    tmp_path: Path, monkeypatch: object
) -> None:
    passing = _passing_result()
    unsafe = PilotRunResult((
        *passing.studies[:-1],
        StudyRunResult(
            passing.studies[-1].study_key,
            passing.studies[-1].checks,
            exported_unsupported_clinical_fact_count=1,
        ),
    ))
    monkeypatch.setattr(  # type: ignore[attr-defined]
        cli, "run_pilot", lambda _base_url, _fixtures: unsafe
    )

    exit_code = cli.main([
        "run",
        "--base-url", "http://example.test",
        "--fixtures", str(tmp_path / "fixtures"),
        "--output", str(tmp_path / "reports"),
        "--run-label", "unsafe",
    ])

    assert exit_code == 1


def test_compare_command_loads_full_reports_and_writes_repeatability_evidence(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "run-a.json"
    second_path = tmp_path / "run-b.json"
    first_path.write_text(render_json(_passing_result("a")))
    second_path.write_text(render_json(_passing_result("b")))

    exit_code = cli.main([
        "compare",
        "--first", str(first_path),
        "--second", str(second_path),
        "--output", str(tmp_path / "comparison"),
    ])

    payload = json.loads(
        (tmp_path / "comparison" / "repeatability.json").read_text()
    )
    markdown = (tmp_path / "comparison" / "repeatability.md").read_text()
    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["checks"]
    assert "Repeatability: PASS" in markdown
    assert "%" not in markdown


def test_compare_command_fails_for_stable_passage_mismatch(tmp_path: Path) -> None:
    first = _passing_result("a")
    changed_study = StudyRunResult(
        first.studies[0].study_key,
        first.studies[0].checks,
        passages={"synopsis": "Changed synthetic passage."},
        study_id="b-study-0",
        snapshot_id="b-snapshot-0",
    )
    second = PilotRunResult((changed_study, *_passing_result("b").studies[1:]))
    first_path = tmp_path / "run-a.json"
    second_path = tmp_path / "run-b.json"
    first_path.write_text(render_json(first))
    second_path.write_text(render_json(second))

    exit_code = cli.main([
        "compare",
        "--first", str(first_path),
        "--second", str(second_path),
        "--output", str(tmp_path / "comparison"),
    ])

    payload = json.loads(
        (tmp_path / "comparison" / "repeatability.json").read_text()
    )
    assert exit_code == 1
    assert payload["passed"] is False
    assert [
        check["name"] for check in payload["checks"] if not check["passed"]
    ] == ["repeatability.study-0.passages"]


def test_full_json_round_trip_preserves_unreached_passage_stage() -> None:
    result = PilotRunResult((StudyRunResult(
        "early-failure",
        (CheckResult("INFRASTRUCTURE_FAILURE", False, "none", "network"),),
        passages=None,
    ),))

    restored = cli.result_from_json(render_json(result))

    assert restored.studies[0].passages is None
    assert render_json(restored) == render_json(result)


def test_atomic_write_preserves_existing_report_when_temp_write_fails(
    tmp_path: Path, monkeypatch: object
) -> None:
    destination = tmp_path / "run.json"
    destination.write_text("previous complete report")
    original_write_text = Path.write_text

    def fail_after_partial_write(path: Path, content: str, **kwargs: object) -> int:
        original_write_text(path, content[:7], **kwargs)
        raise OSError("synthetic write failure")

    monkeypatch.setattr(Path, "write_text", fail_after_partial_write)  # type: ignore[attr-defined]

    with pytest.raises(OSError, match="synthetic write failure"):
        cli._atomic_write(destination, "replacement report")

    assert destination.read_text() == "previous complete report"
    assert list(tmp_path.glob("*.tmp")) == []


def test_make_target_uses_two_disposable_stacks_and_ignored_output() -> None:
    app_root = Path(__file__).parents[4]
    makefile = (app_root / "Makefile").read_text()
    recipe = makefile.partition("\nreliability-pilot:")[2].partition("\nup:")[0]
    gitignore = (app_root.parent / ".gitignore").read_text()

    assert "protocol-poc-reliability-a" in recipe
    assert "protocol-poc-reliability-b" in recipe
    assert recipe.count("down --volumes") >= 4
    assert "API_PORT=8301" in recipe
    assert "API_PORT=8302" in recipe
    assert "run-a" in recipe
    assert "run-b" in recipe
    assert "protocol_poc.reliability compare" in recipe
    assert recipe.count("PYTHONPATH=src .venv/bin/python") == 3
    assert "clinical-protocol-poc/work/reliability-pilot/" in gitignore
