from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from protocol_poc.reliability.manifest import PilotManifest, load_pilot_manifests


EXPECTED_STUDY_KEYS = [
    "standard",
    "vocabulary-variation",
    "value-variation",
    "missing-dose",
    "broken-template",
    "unsupported-passage-edit",
]


def _valid_manifest(study_key: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "study_key": study_key,
        "study_name": f"Synthetic {study_key}",
        "initial_outcome": "direct_success",
        "inputs": {
            "synopsis": "synopsis.docx",
            "template": "template.docx",
        },
        "input_sha256": {
            "synopsis": "a" * 64,
            "template": "b" * 64,
        },
        "expected_facts": [
            {
                "kind": "study_identity",
                "value": {"kind": "string", "value": "SYN-1"},
                "critical": False,
            }
        ],
        "expected_blockers": [],
        "expected_next_action": "review_facts",
        "correction": None,
        "expected_current_versions": {"synopsis": 1, "template": 1},
        "expected_passages": {
            "synopsis": "SYN-1 is a synthetic study in a synthetic population.",
            "objectives_endpoints": "The objective is synthetic.",
            "study_design": "Synthetic treatment is administered.",
            "eligibility": "Eligibility is synthetic.",
        },
        "unsupported_edit": None,
        "expected_artifacts": [
            {
                "name": "protocol.docx",
                "media_type": (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            },
            {"name": "traceability.csv", "media_type": "text/csv"},
            {"name": "scorecard.html", "media_type": "text/html"},
        ],
    }


def test_manifest_rejects_run_specific_gold_fields() -> None:
    payload = _valid_manifest("standard")
    payload["snapshot_id"] = "run-specific-id"

    with pytest.raises(ValidationError) as captured:
        PilotManifest.model_validate(payload)

    assert captured.value.errors()[0]["loc"] == ("snapshot_id",)
    assert captured.value.errors()[0]["type"] == "extra_forbidden"


def test_manifest_requires_correction_only_for_recovery_studies() -> None:
    direct = _valid_manifest("standard")
    direct["correction"] = {
        "kind": "replace_synopsis",
        "filename": "corrected-synopsis.docx",
    }
    recovery = _valid_manifest("missing-dose")
    recovery["initial_outcome"] = "blocked_then_recover"

    with pytest.raises(ValidationError, match="correction must match initial_outcome"):
        PilotManifest.model_validate(direct)
    with pytest.raises(ValidationError, match="correction must match initial_outcome"):
        PilotManifest.model_validate(recovery)


def test_loader_requires_exactly_six_manifests_in_stable_order(tmp_path: Path) -> None:
    for study_key in reversed(EXPECTED_STUDY_KEYS):
        directory = tmp_path / study_key
        directory.mkdir()
        payload = _valid_manifest(study_key)
        if study_key in {"missing-dose", "broken-template", "unsupported-passage-edit"}:
            payload["initial_outcome"] = "blocked_then_recover"
            payload["correction"] = {
                "kind": (
                    "replace_synopsis"
                    if study_key == "missing-dose"
                    else "upload_corrected_template"
                    if study_key == "broken-template"
                    else "regenerate_passage"
                ),
                "filename": (
                    "corrected-synopsis.docx"
                    if study_key == "missing-dose"
                    else "corrected-template.docx"
                    if study_key == "broken-template"
                    else None
                ),
                "section": "study_design" if study_key == "unsupported-passage-edit" else None,
            }
            if study_key == "missing-dose":
                payload["inputs"]["corrected_synopsis"] = "corrected-synopsis.docx"
                payload["input_sha256"]["corrected_synopsis"] = "c" * 64
            elif study_key == "broken-template":
                payload["inputs"]["corrected_template"] = "corrected-template.docx"
                payload["input_sha256"]["corrected_template"] = "d" * 64
        (directory / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    manifests = load_pilot_manifests(tmp_path)

    assert [item.study_key for item in manifests] == EXPECTED_STUDY_KEYS

    (tmp_path / "standard" / "manifest.json").unlink()
    with pytest.raises(ValueError, match="exactly the six declared studies"):
        load_pilot_manifests(tmp_path)


def test_loader_rejects_manifest_key_that_differs_from_its_directory(
    tmp_path: Path,
) -> None:
    for study_key in EXPECTED_STUDY_KEYS:
        directory = tmp_path / study_key
        directory.mkdir()
        payload = _valid_manifest(
            "standard" if study_key == "value-variation" else study_key
        )
        if study_key in {"missing-dose", "broken-template", "unsupported-passage-edit"}:
            payload["initial_outcome"] = "blocked_then_recover"
            payload["correction"] = {
                "kind": "regenerate_passage",
                "section": "study_design",
            }
        (directory / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="must match its directory"):
        load_pilot_manifests(tmp_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["input_sha256"].pop("template"),
            "inputs and input_sha256 must use identical keys",
        ),
        (
            lambda payload: payload.__setitem__(
                "expected_artifacts", payload["expected_artifacts"][:2]
            ),
            "expected_artifacts must contain the exact three-artifact set",
        ),
        (
            lambda payload: payload.__setitem__(
                "expected_passages", {"synopsis": "Only one section"}
            ),
            "expected_passages must contain the exact four-section set",
        ),
    ],
)
def test_manifest_rejects_cross_field_mismatches(mutation, message: str) -> None:
    payload = _valid_manifest("standard")
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        PilotManifest.model_validate(payload)


@pytest.mark.parametrize(
    "correction",
    [
        {"kind": "replace_synopsis"},
        {"kind": "upload_corrected_template"},
        {"kind": "regenerate_passage"},
    ],
)
def test_recovery_correction_requires_its_file_or_section(
    correction: dict[str, str],
) -> None:
    payload = _valid_manifest("missing-dose")
    payload["initial_outcome"] = "blocked_then_recover"
    payload["correction"] = correction

    with pytest.raises(ValidationError, match="correction is incomplete"):
        PilotManifest.model_validate(payload)
