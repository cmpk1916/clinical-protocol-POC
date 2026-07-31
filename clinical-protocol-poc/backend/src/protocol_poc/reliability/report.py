from __future__ import annotations

from collections.abc import Mapping
import json
from typing import cast

from protocol_poc.reliability.results import (
    CheckResult,
    PilotRunResult,
    deterministic_projection,
)


SAFETY_NOTICE = (
    "Synthetic POC evaluation only. This report does not establish clinical, "
    "regulatory, submission, operational, production, or readiness status."
)


def json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((json_value(item) for item in value), key=repr)
    return value


def result_payload(result: PilotRunResult) -> dict[str, object]:
    return {
        "passed": result.passed,
        "exported_unsupported_clinical_fact_count": (
            result.exported_unsupported_clinical_fact_count
        ),
        "studies": [
            {
                "study_key": study.study_key,
                "passed": study.passed,
                "initial_export_denied": study.initial_export_denied,
                "checks": [
                    {
                        "name": check.name,
                        "passed": check.passed,
                        "expected": json_value(check.expected),
                        "actual": json_value(check.actual),
                        "volatile": check.volatile,
                    }
                    for check in study.checks
                ],
                "input_history": json_value(study.input_history),
                "facts": json_value(study.facts),
                "passages": (
                    None if study.passages is None else json_value(study.passages)
                ),
                "artifacts": [
                    {
                        "name": artifact.name,
                        "media_type": artifact.media_type,
                        "sha256": artifact.sha256,
                        "snapshot_id": artifact.snapshot_id,
                        "size_bytes": artifact.size_bytes,
                    }
                    for artifact in study.artifacts
                ],
                "study_id": study.study_id,
                "snapshot_id": study.snapshot_id,
                "exported_unsupported_clinical_fact_count": (
                    study.exported_unsupported_clinical_fact_count
                ),
            }
            for study in result.studies
        ],
    }


def render_json(result: PilotRunResult) -> str:
    return json.dumps(result_payload(result), indent=2, sort_keys=True) + "\n"


def _display(value: object) -> str:
    rendered = json_value(value)
    if isinstance(rendered, str):
        return rendered
    return json.dumps(rendered, sort_keys=True)


def render_markdown(result: PilotRunResult) -> str:
    passed_count = sum(study.passed for study in result.studies)
    lines = [
        "# Six-Study Synthetic Reliability Pilot",
        "",
        SAFETY_NOTICE,
        "",
        f"Result: {'PASS' if result.passed else 'FAIL'}",
        f"Studies passed: {passed_count} of {len(result.studies)}",
        (
            "unsupported clinical facts exported: "
            f"{result.exported_unsupported_clinical_fact_count}"
        ),
    ]
    for study in result.studies:
        lines.extend((
            "",
            f"## {study.study_key} — {'PASS' if study.passed else 'FAIL'}",
            "",
            f"Study ID: {study.study_id or 'not created'}",
            f"Snapshot ID: {study.snapshot_id or 'not exported'}",
            f"Initial export denied: {'yes' if study.initial_export_denied else 'no'}",
            "",
            "### Input history",
        ))
        if study.input_history:
            for item in study.input_history:
                lines.append(
                    "- "
                    f"{item.get('role', 'input')}: {item.get('filename', 'unknown')}; "
                    f"version {item.get('version', 'unknown')}; "
                    f"status {item.get('status', 'unknown')}; "
                    f"SHA-256 {item.get('checksum_sha256', 'unknown')}"
                )
        else:
            lines.append("- No input history recorded.")

        evidence = [
            check for check in study.checks
            if check.name.startswith((
                "template.",
                "processing.",
                "synopsis.",
                "passage.",
            ))
            or check.name in {"input.current_versions", "initial_export"}
        ]
        lines.extend(("", "### Blocker, action, and correction evidence"))
        if evidence:
            for check in evidence:
                lines.append(
                    f"- {check.name}: {'PASS' if check.passed else 'FAIL'}; "
                    f"Expected: {_display(check.expected)}; "
                    f"Actual: {_display(check.actual)}"
                )
        else:
            lines.append("- No correction was required.")

        lines.extend(("", "### Passages"))
        if study.passages:
            for section, passage in study.passages.items():
                lines.append(f"- {section}: {passage}")
        else:
            lines.append("- No passages recorded.")

        lines.extend(("", "### Artifacts"))
        if study.artifacts:
            for artifact in study.artifacts:
                lines.append(
                    f"- {artifact.name}; {artifact.media_type}; "
                    f"SHA-256 {artifact.sha256}; snapshot {artifact.snapshot_id}; "
                    f"{artifact.size_bytes} bytes"
                )
        else:
            lines.append("- No artifacts exported.")

        failed = [check for check in study.checks if not check.passed]
        lines.extend(("", "### Failed checks"))
        if failed:
            for check in failed:
                lines.extend((
                    f"- {check.name}",
                    f"  - Expected: {_display(check.expected)}",
                    f"  - Actual: {_display(check.actual)}",
                ))
        else:
            lines.append("- None.")
    return "\n".join(lines) + "\n"


def compare_repeatability(
    first: PilotRunResult, second: PilotRunResult
) -> tuple[CheckResult, ...]:
    first_projection = deterministic_projection(first)
    second_projection = deterministic_projection(second)
    checks = [
        CheckResult(
            f"repeatability.{field}",
            first_projection[field] == second_projection[field],
            first_projection[field],
            second_projection[field],
        )
        for field in ("passed", "exported_unsupported_clinical_fact_count")
    ]
    first_studies = {
        str(study["study_key"]): study
        for study in cast(list[dict[str, object]], first_projection["studies"])
    }
    second_studies = {
        str(study["study_key"]): study
        for study in cast(list[dict[str, object]], second_projection["studies"])
    }
    checks.append(CheckResult(
        "repeatability.study_keys",
        tuple(first_studies) == tuple(second_studies),
        tuple(first_studies),
        tuple(second_studies),
    ))
    for study_key in sorted(first_studies.keys() & second_studies.keys()):
        first_study = first_studies[study_key]
        second_study = second_studies[study_key]
        for field in sorted(first_study.keys() | second_study.keys()):
            if field == "study_key":
                continue
            expected = first_study.get(field)
            actual = second_study.get(field)
            checks.append(CheckResult(
                f"repeatability.{study_key}.{field}",
                expected == actual,
                expected,
                actual,
            ))
    return tuple(checks)
