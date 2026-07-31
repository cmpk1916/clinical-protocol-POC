from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


STUDY_ORDER = (
    "standard",
    "vocabulary-variation",
    "value-variation",
    "missing-dose",
    "broken-template",
    "unsupported-passage-edit",
)
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedFact(StrictModel):
    kind: str = Field(min_length=1)
    value: dict[str, object]
    critical: bool = False


class ExpectedBlocker(StrictModel):
    code: str = Field(min_length=1)
    affected_area: str = Field(min_length=1)
    next_action: str = Field(min_length=1)


class CorrectionSpec(StrictModel):
    kind: Literal[
        "replace_synopsis",
        "upload_corrected_template",
        "regenerate_passage",
    ]
    filename: str | None = None
    section: str | None = None

    @model_validator(mode="after")
    def require_file_or_section(self) -> "CorrectionSpec":
        if self.kind in {"replace_synopsis", "upload_corrected_template"}:
            if self.filename is None or not self.filename.strip() or self.section is not None:
                raise ValueError("correction is incomplete for a source replacement")
        elif self.section is None or not self.section.strip() or self.filename is not None:
            raise ValueError("correction is incomplete for passage regeneration")
        return self


class ExpectedArtifact(StrictModel):
    name: Literal["protocol.docx", "traceability.csv", "scorecard.html"]
    media_type: str = Field(min_length=1)


class PilotManifest(StrictModel):
    schema_version: Literal[1]
    study_key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    study_name: str = Field(min_length=1)
    initial_outcome: Literal["direct_success", "blocked_then_recover"]
    inputs: dict[str, str]
    input_sha256: dict[str, Sha256]
    expected_facts: tuple[ExpectedFact, ...]
    expected_blockers: tuple[ExpectedBlocker, ...]
    expected_next_action: str = Field(min_length=1)
    correction: CorrectionSpec | None
    expected_current_versions: dict[str, int]
    expected_passages: dict[str, str]
    unsupported_edit: dict[str, str] | None = None
    expected_artifacts: tuple[ExpectedArtifact, ...]

    @model_validator(mode="after")
    def correction_matches_outcome(self) -> "PilotManifest":
        requires_correction = self.initial_outcome == "blocked_then_recover"
        if requires_correction != (self.correction is not None):
            raise ValueError("correction must match initial_outcome")
        if set(self.inputs) != set(self.input_sha256):
            raise ValueError("inputs and input_sha256 must use identical keys")
        if not {"synopsis", "template"}.issubset(self.inputs):
            raise ValueError("inputs must include synopsis and template")
        if set(self.expected_current_versions) != {"synopsis", "template"}:
            raise ValueError("expected_current_versions must cover synopsis and template")
        if set(self.expected_passages) != {
            "synopsis",
            "objectives_endpoints",
            "study_design",
            "eligibility",
        }:
            raise ValueError("expected_passages must contain the exact four-section set")
        expected_artifacts = (
            (
                "protocol.docx",
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document",
            ),
            ("traceability.csv", "text/csv"),
            ("scorecard.html", "text/html"),
        )
        actual_artifacts = tuple(
            (artifact.name, artifact.media_type) for artifact in self.expected_artifacts
        )
        if actual_artifacts != expected_artifacts:
            raise ValueError("expected_artifacts must contain the exact three-artifact set")
        if self.correction is not None:
            corrected_input = {
                "replace_synopsis": "corrected_synopsis",
                "upload_corrected_template": "corrected_template",
            }.get(self.correction.kind)
            if corrected_input is not None and (
                self.inputs.get(corrected_input) != self.correction.filename
            ):
                raise ValueError("correction filename must identify its declared input")
        return self


def load_manifest(path: Path) -> PilotManifest:
    return PilotManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_pilot_manifests(root: Path) -> tuple[PilotManifest, ...]:
    by_key: dict[str, PilotManifest] = {}
    for path in root.glob("*/manifest.json"):
        manifest = load_manifest(path)
        directory_key = path.parent.name
        if manifest.study_key != directory_key:
            raise ValueError(
                f"manifest study_key {manifest.study_key!r} must match its directory "
                f"{directory_key!r}"
            )
        by_key[directory_key] = manifest
    if set(by_key) != set(STUDY_ORDER):
        raise ValueError("reliability pilot must contain exactly the six declared studies")
    return tuple(by_key[key] for key in STUDY_ORDER)
