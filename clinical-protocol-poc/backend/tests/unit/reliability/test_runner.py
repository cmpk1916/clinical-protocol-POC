from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from protocol_poc.reliability.manifest import PilotManifest
from protocol_poc.reliability.results import (
    ArtifactResult,
    CheckResult,
    PilotRunResult,
    StudyRunResult,
    deterministic_projection,
)
from protocol_poc.reliability.runner import PilotRunner


def _manifest(
    key: str,
    *,
    expected_blocker: str | None = None,
    hashes: dict[str, str] | None = None,
) -> PilotManifest:
    blocked = expected_blocker is not None
    inputs = {"synopsis": "synopsis.docx", "template": "template.docx"}
    if blocked:
        inputs["corrected_synopsis"] = "corrected-synopsis.docx"
    return PilotManifest.model_validate({
        "schema_version": 1,
        "study_key": key,
        "study_name": f"Synthetic {key}",
        "initial_outcome": "blocked_then_recover" if blocked else "direct_success",
        "inputs": inputs,
        "input_sha256": hashes or {role: "0" * 64 for role in inputs},
        "expected_facts": [],
        "expected_blockers": ([{
            "code": expected_blocker,
            "affected_area": "synopsis",
            "next_action": "upload_synopsis",
        }] if blocked else []),
        "expected_next_action": "upload_synopsis" if blocked else "review_facts",
        "correction": ({
            "kind": "replace_synopsis",
            "filename": "corrected-synopsis.docx",
            "section": None,
        } if blocked else None),
        "expected_current_versions": {"synopsis": 1, "template": 1},
        "expected_passages": {
            "synopsis": "Synthetic synopsis.",
            "objectives_endpoints": "Synthetic objectives.",
            "study_design": "Synthetic design.",
            "eligibility": "Synthetic eligibility.",
        },
        "unsupported_edit": None,
        "expected_artifacts": [
            {
                "name": "protocol.docx",
                "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
            {"name": "traceability.csv", "media_type": "text/csv"},
            {"name": "scorecard.html", "media_type": "text/html"},
        ],
    })


def test_hash_mismatch_fails_before_upload(tmp_path: Path) -> None:
    pack = tmp_path / "hash-mismatch"
    pack.mkdir()
    synopsis = b"synthetic synopsis"
    template = b"synthetic template"
    (pack / "synopsis.docx").write_bytes(synopsis)
    (pack / "template.docx").write_bytes(template)
    manifest = _manifest(
        "hash-mismatch",
        hashes={
            "synopsis": "f" * 64,
            "template": sha256(template).hexdigest(),
        },
    )

    class UploadSpy:
        uploads = 0

        def upload_input(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            self.uploads += 1
            return {}

    client = UploadSpy()
    result = PilotRunner(client, tmp_path).run((manifest,))

    assert result.passed is False
    assert client.uploads == 0
    assert result.studies[0].checks[0].name == "fixture_hash.synopsis"
    assert result.studies[0].checks[0].passed is False


def test_deterministic_projection_excludes_run_ids_and_hashes() -> None:
    result = PilotRunResult((StudyRunResult(
        "standard",
        (
            CheckResult("workflow.complete", True, True, True),
            CheckResult(
                "fixture_hash.synopsis",
                True,
                "secret-hash",
                "secret-hash",
                volatile=True,
            ),
            CheckResult(
                "opaque-run-value",
                True,
                "snapshot-secret",
                "snapshot-secret",
                volatile=True,
            ),
        ),
        input_history=({
            "role": "synopsis",
            "filename": "synopsis.docx",
            "version": 1,
            "version_id": "version-secret",
            "current_file_version_id": "version-secret",
            "checksum_sha256": "secret-hash",
        },),
        facts=({"kind": "dose", "value": {"value": "10", "unit": "mg"}},),
        passages={"study_design": "Synthetic design."},
        artifacts=(ArtifactResult(
            "protocol.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "secret-hash",
            "snapshot-secret",
            123,
        ),),
        study_id="study-secret",
        snapshot_id="snapshot-secret",
    ),))

    projection = deterministic_projection(result)
    rendered = repr(projection)

    assert "Synthetic design." in rendered
    assert "study-secret" not in rendered
    assert "snapshot-secret" not in rendered
    assert "secret-hash" not in rendered
    assert "version-secret" not in rendered


def test_run_results_are_deeply_immutable() -> None:
    result = StudyRunResult(
        "standard",
        (CheckResult("facts", True, {"value": ["10 mg"]}, {"value": ["10 mg"]}),),
        input_history=({"role": "synopsis", "metadata": {"version": 1}},),
        facts=({"kind": "dose", "value": {"value": "10", "unit": "mg"}},),
        passages={"study_design": "Synthetic design."},
    )

    with pytest.raises(TypeError):
        cast(dict[str, object], result.input_history[0])["role"] = "template"
    with pytest.raises(TypeError):
        cast(dict[str, object], result.facts[0]["value"])["value"] = "99"
    with pytest.raises(TypeError):
        cast(dict[str, str], result.passages)["study_design"] = "Changed."
    with pytest.raises(AttributeError):
        cast(list[str], result.checks[0].expected["value"]).append("99 mg")  # type: ignore[index]
