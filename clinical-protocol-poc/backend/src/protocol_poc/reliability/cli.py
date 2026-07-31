from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import re

from protocol_poc.reliability.client import PilotClient
from protocol_poc.reliability.manifest import load_pilot_manifests
from protocol_poc.reliability.report import (
    SAFETY_NOTICE,
    compare_repeatability,
    json_value,
    render_json,
    render_markdown,
)
from protocol_poc.reliability.results import (
    ArtifactResult,
    CheckResult,
    PilotRunResult,
    StudyRunResult,
)
from protocol_poc.reliability.runner import PilotRunner


RUN_LABEL_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def result_from_json(document: str) -> PilotRunResult:
    payload = _mapping(json.loads(document), "pilot result")
    studies: list[StudyRunResult] = []
    for raw_study in _list(payload.get("studies"), "studies"):
        study = _mapping(raw_study, "study")
        checks = tuple(
            CheckResult(
                _string(check["name"], "check name"),
                _boolean(check["passed"], "check passed"),
                check.get("expected"),
                check.get("actual"),
                _boolean(check.get("volatile", False), "check volatile"),
            )
            for check in (
                _mapping(item, "check")
                for item in _list(study.get("checks"), "checks")
            )
        )
        history = tuple(
            _mapping(item, "input history")
            for item in _list(study.get("input_history"), "input history")
        )
        facts = tuple(
            _mapping(item, "fact")
            for item in _list(study.get("facts"), "facts")
        )
        raw_passages = study.get("passages")
        passages = None if raw_passages is None else {
            str(key): _string(value, "passage")
            for key, value in _mapping(raw_passages, "passages").items()
        }
        artifacts = tuple(
            ArtifactResult(
                _string(artifact["name"], "artifact name"),
                _string(artifact["media_type"], "artifact media type"),
                _string(artifact["sha256"], "artifact sha256"),
                _string(artifact["snapshot_id"], "artifact snapshot id"),
                _integer(artifact["size_bytes"], "artifact size"),
            )
            for artifact in (
                _mapping(item, "artifact")
                for item in _list(study.get("artifacts"), "artifacts")
            )
        )
        studies.append(StudyRunResult(
            _string(study["study_key"], "study key"),
            checks,
            initial_export_denied=_boolean(
                study.get("initial_export_denied"), "initial export denied"
            ),
            input_history=history,
            facts=facts,
            passages=passages,
            artifacts=artifacts,
            study_id=_optional_string(study.get("study_id"), "study id"),
            snapshot_id=_optional_string(study.get("snapshot_id"), "snapshot id"),
            exported_unsupported_clinical_fact_count=_integer(
                study.get("exported_unsupported_clinical_fact_count"),
                "unsupported clinical fact count",
            ),
        ))
    return PilotRunResult(tuple(studies))


def run_pilot(base_url: str, fixtures: Path) -> PilotRunResult:
    manifests = load_pilot_manifests(fixtures)
    with PilotClient(base_url, "pilot-tenant", "pilot-runner") as client:
        return PilotRunner(client, fixtures).run(manifests)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_run_reports(output: Path, label: str, result: PilotRunResult) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{label}.json"
    markdown_path = output / f"{label}.md"
    _atomic_write(json_path, render_json(result))
    _atomic_write(markdown_path, render_markdown(result))
    return json_path, markdown_path


def _accepted(result: PilotRunResult) -> bool:
    return (
        len(result.studies) == 6
        and result.passed
        and result.exported_unsupported_clinical_fact_count == 0
    )


def _comparison_payload(checks: tuple[CheckResult, ...]) -> dict[str, object]:
    return {
        "passed": bool(checks) and all(check.passed for check in checks),
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "expected": json_value(check.expected),
                "actual": json_value(check.actual),
            }
            for check in checks
        ],
    }


def _comparison_markdown(checks: tuple[CheckResult, ...]) -> str:
    passed = bool(checks) and all(check.passed for check in checks)
    lines = [
        "# Reliability Pilot Repeatability",
        "",
        SAFETY_NOTICE,
        "",
        f"Repeatability: {'PASS' if passed else 'FAIL'}",
        "",
        "## Mismatches",
    ]
    failed = [check for check in checks if not check.passed]
    if failed:
        for check in failed:
            lines.extend((
                f"- {check.name}",
                f"  - Expected: {json.dumps(json_value(check.expected), sort_keys=True)}",
                f"  - Actual: {json.dumps(json_value(check.actual), sort_keys=True)}",
            ))
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def _run_command(args: argparse.Namespace) -> int:
    label = str(args.run_label)
    if not RUN_LABEL_PATTERN.fullmatch(label):
        raise ValueError("run label must contain lowercase letters, numbers, and hyphens")
    result = run_pilot(str(args.base_url), Path(args.fixtures))
    json_path, markdown_path = _write_run_reports(Path(args.output), label, result)
    passed_count = sum(study.passed for study in result.studies)
    print(json_path)
    print(markdown_path)
    print(f"Studies passed: {passed_count} of {len(result.studies)}")
    print(
        "unsupported clinical facts exported: "
        f"{result.exported_unsupported_clinical_fact_count}"
    )
    return 0 if _accepted(result) else 1


def _compare_command(args: argparse.Namespace) -> int:
    first = result_from_json(Path(args.first).read_text(encoding="utf-8"))
    second = result_from_json(Path(args.second).read_text(encoding="utf-8"))
    checks = compare_repeatability(first, second)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "repeatability.json"
    markdown_path = output / "repeatability.md"
    _atomic_write(
        json_path,
        json.dumps(_comparison_payload(checks), indent=2, sort_keys=True) + "\n",
    )
    _atomic_write(markdown_path, _comparison_markdown(checks))
    print(json_path)
    print(markdown_path)
    print(f"Repeatability: {'PASS' if all(check.passed for check in checks) else 'FAIL'}")
    return 0 if (
        _accepted(first)
        and _accepted(second)
        and bool(checks)
        and all(check.passed for check in checks)
    ) else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the synthetic reliability pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--fixtures", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--run-label", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--first", required=True)
    compare.add_argument("--second", required=True)
    compare.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        return _run_command(args)
    return _compare_command(args)
