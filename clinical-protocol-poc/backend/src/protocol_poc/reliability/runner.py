from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from typing import cast
from zipfile import ZipFile

from protocol_poc.reliability.client import (
    InputRole,
    PassageSection,
    PilotClient,
    PilotHttpError,
)
from protocol_poc.reliability.manifest import PilotManifest
from protocol_poc.reliability.results import (
    ArtifactResult,
    CheckResult,
    PilotRunResult,
    StudyRunResult,
)


SECTIONS = ("synopsis", "objectives_endpoints", "study_design", "eligibility")
TRACEABILITY_FIELDS = (
    "section",
    "passage",
    "claim",
    "fact_value",
    "evidence_location",
    "guidance_release",
    "review_state",
    "validation_status",
)
SCORECARD_DIMENSIONS = (
    "completeness",
    "consistency",
    "traceability",
    "template_conformance",
    "writer_review_status",
    "approved_guidance_coverage",
)
SCORECARD_DISCLAIMER = (
    "Synthetic POC output only; not validated and no clinical, regulatory, "
    "submission, operational, or readiness claim is made."
)


@dataclass(frozen=True, slots=True)
class StudyState:
    study_id: str
    study_version: int
    uploads: dict[str, dict[str, object]]
    workspace: dict[str, object]


def _check(
    name: str, expected: object, actual: object, *, volatile: bool = False
) -> CheckResult:
    return CheckResult(name, expected == actual, expected, actual, volatile)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _items(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return [_mapping(item, label) for item in value]


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    return value


def _fact_projection(queue: dict[str, object]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "kind": item["kind"],
            "value": item["current_value"],
            "critical": item["critical"],
        }
        for item in _items(queue.get("items"), "fact review items")
    )


class PilotRunner:
    def __init__(self, client: PilotClient, fixture_root: Path) -> None:
        self.client = client
        self.fixture_root = fixture_root

    def run(self, manifests: tuple[PilotManifest, ...]) -> PilotRunResult:
        studies: list[StudyRunResult] = []
        for manifest in manifests:
            try:
                studies.append(self._run_manifest(manifest))
            except Exception as error:
                studies.append(StudyRunResult(
                    manifest.study_key,
                    (CheckResult(
                        "INFRASTRUCTURE_FAILURE",
                        False,
                        "no infrastructure failure",
                        f"{type(error).__name__}: {error}",
                    ),),
                ))
        return PilotRunResult(tuple(studies))

    def _run_manifest(self, manifest: PilotManifest) -> StudyRunResult:
        checks = list(self._verify_fixture_hashes(manifest))
        if not all(item.passed for item in checks):
            return StudyRunResult(manifest.study_key, tuple(checks))

        state, create_checks, history = self._create_and_upload(manifest)
        checks.extend(create_checks)
        if not all(item.passed for item in create_checks):
            return StudyRunResult(
                manifest.study_key,
                tuple(checks),
                input_history=tuple(history),
                study_id=state.study_id,
            )
        state, queue, processing_checks, denied, correction_history = (
            self._process_and_compare_facts(state, manifest)
        )
        checks.extend(processing_checks)
        history.extend(correction_history)
        stable_facts = _fact_projection(queue)
        if not all(item.passed for item in processing_checks):
            return StudyRunResult(
                manifest.study_key,
                tuple(checks),
                initial_export_denied=denied,
                input_history=tuple(history),
                facts=stable_facts,
                study_id=state.study_id,
            )
        review_checks = self._review_facts(state, queue)
        checks.extend(review_checks)
        if not all(item.passed for item in review_checks):
            return StudyRunResult(
                manifest.study_key,
                tuple(checks),
                initial_export_denied=denied,
                input_history=tuple(history),
                facts=stable_facts,
                study_id=state.study_id,
            )
        (
            draft_checks,
            artifacts,
            passages,
            snapshot_id,
            unsupported_count,
            passage_denied,
        ) = self._draft_review_and_export(state, manifest)
        checks.extend(draft_checks)
        return StudyRunResult(
            manifest.study_key,
            tuple(checks),
            initial_export_denied=denied or passage_denied,
            input_history=tuple(history),
            facts=stable_facts,
            passages=passages,
            artifacts=artifacts,
            study_id=state.study_id,
            snapshot_id=snapshot_id,
            exported_unsupported_clinical_fact_count=unsupported_count,
        )

    def _verify_fixture_hashes(
        self, manifest: PilotManifest
    ) -> tuple[CheckResult, ...]:
        pack_root = (self.fixture_root / manifest.study_key).resolve()
        checks: list[CheckResult] = []
        for role, filename in manifest.inputs.items():
            resolved = (pack_root / filename).resolve()
            expected = manifest.input_sha256[role]
            if not resolved.is_relative_to(pack_root):
                actual = "PATH_TRAVERSAL"
            elif not resolved.is_file():
                actual = "FILE_MISSING"
            else:
                actual = sha256(resolved.read_bytes()).hexdigest()
            checks.append(_check(
                f"fixture_hash.{role}", expected, actual, volatile=True
            ))
        return tuple(checks)

    def _fixture(self, manifest: PilotManifest, role: str) -> Path:
        return self.fixture_root / manifest.study_key / manifest.inputs[role]

    @staticmethod
    def _history(role: str, filename: str, upload: dict[str, object]) -> dict[str, object]:
        return {
            "role": role,
            "filename": filename,
            "version_id": upload.get("version_id"),
            "version": upload.get("version"),
            "status": upload.get("status"),
            "current_file_version_id": upload.get("current_file_version_id"),
            "checksum_sha256": upload.get("checksum_sha256"),
        }

    def _create_and_upload(
        self, manifest: PilotManifest
    ) -> tuple[StudyState, tuple[CheckResult, ...], list[dict[str, object]]]:
        study = self.client.create_study(manifest.study_name)
        study_id = str(study["id"])
        uploads: dict[str, dict[str, object]] = {}
        checks: list[CheckResult] = []
        history: list[dict[str, object]] = []
        for role in ("synopsis", "template"):
            upload = self.client.upload_input(
                study_id,
                cast(InputRole, role),
                self._fixture(manifest, role),
            )
            uploads[role] = upload
            history.append(self._history(role, manifest.inputs[role], upload))
            checks.append(_check(
                f"upload_hash.{role}",
                manifest.input_sha256[role],
                upload.get("checksum_sha256"),
                volatile=True,
            ))
        workspace = self.client.get_workspace(study_id)
        workspace_study = _mapping(workspace.get("study"), "workspace study")
        return (
            StudyState(
                study_id,
                _integer(workspace_study["version"], "study version"),
                uploads,
                workspace,
            ),
            tuple(checks),
            history,
        )

    def _process_and_compare_facts(
        self, state: StudyState, manifest: PilotManifest
    ) -> tuple[
        StudyState,
        dict[str, object],
        tuple[CheckResult, ...],
        bool,
        list[dict[str, object]],
    ]:
        checks: list[CheckResult] = []
        history: list[dict[str, object]] = []
        denied = False
        workspace = state.workspace
        uploads = dict(state.uploads)

        if manifest.correction and manifest.correction.kind == "upload_corrected_template":
            template = uploads["template"]
            template_findings = tuple(
                (str(item.get("code")), str(item.get("field")))
                for item in _items(template.get("findings"), "template findings")
            )
            expected = tuple(
                (item.code, item.affected_area) for item in manifest.expected_blockers
            )
            checks.extend((
                _check("template.status", "conformance_failed", template.get("status")),
                _check("template.findings", expected, template_findings),
                _check(
                    "template.current",
                    None,
                    _mapping(workspace.get("inputs"), "workspace inputs").get("template"),
                ),
                _check("template.export_command", None, workspace.get("export_command")),
            ))
            denied = True
            if not all(item.passed for item in checks):
                return state, {"items": []}, tuple(checks), denied, history
            corrected = self.client.upload_input(
                state.study_id,
                "template",
                self._fixture(manifest, "corrected_template"),
            )
            uploads["corrected_template"] = corrected
            history.append(self._history(
                "template", manifest.inputs["corrected_template"], corrected
            ))
            checks.append(_check("template.corrected_status", "activated", corrected.get("status")))
            workspace = self.client.get_workspace(state.study_id)
            if not all(item.passed for item in checks):
                return (
                    replace(state, uploads=uploads, workspace=workspace),
                    {"items": []},
                    tuple(checks),
                    denied,
                    history,
                )

        inputs = _mapping(workspace.get("inputs"), "workspace inputs")
        synopsis = _mapping(inputs.get("synopsis"), "current synopsis")
        processing = self.client.process_synopsis(
            state.study_id, str(synopsis["version_id"])
        )

        if manifest.correction and manifest.correction.kind == "replace_synopsis":
            processing_findings = _items(
                processing.get("findings"), "processing findings"
            )
            actual_blockers = tuple(
                (str(item.get("code")), str(item.get("field")))
                for item in processing_findings
            )
            expected_blockers = tuple(
                (item.code, item.affected_area) for item in manifest.expected_blockers
            )
            workspace = self.client.get_workspace(state.study_id)
            next_action = _mapping(workspace.get("next_action"), "next action")
            checks.extend((
                _check("processing.blockers", expected_blockers, actual_blockers),
                _check(
                    "processing.next_action",
                    manifest.expected_next_action,
                    next_action.get("kind"),
                ),
            ))
            export_command = workspace.get("export_command")
            if isinstance(export_command, dict):
                try:
                    self.client.create_export(state.study_id, export_command)
                    denial_result: object = (200, "EXPORT_ALLOWED")
                except PilotHttpError as error:
                    denial_result = (error.status_code, error.code)
            else:
                denial_result = "EXPORT_COMMAND_MISSING"
            checks.append(_check(
                "initial_export", (409, "EXPORT_BLOCKED"), denial_result
            ))
            denied = denial_result == (409, "EXPORT_BLOCKED")
            if not all(item.passed for item in checks):
                return state, {"items": []}, tuple(checks), denied, history
            corrected = self.client.upload_input(
                state.study_id,
                "synopsis",
                self._fixture(manifest, "corrected_synopsis"),
            )
            uploads["corrected_synopsis"] = corrected
            history.append(self._history(
                "synopsis", manifest.inputs["corrected_synopsis"], corrected
            ))
            checks.append(_check(
                "synopsis.replacement_status",
                "replacement_confirmation_required",
                corrected.get("status"),
            ))
            proposed_id = str(corrected["version_id"])
            current_id = str(synopsis["version_id"])
            preview = self.client.preview_replacement(
                state.study_id, "synopsis", proposed_version_id=proposed_id
            )
            checks.append(_check(
                "synopsis.preview_version",
                proposed_id,
                preview.get("proposed_version_id"),
                volatile=True,
            ))
            confirmation = self.client.confirm_replacement(
                state.study_id,
                "synopsis",
                proposed_version_id=proposed_id,
                expected_current_version_id=current_id,
                expected_study_version=state.study_version,
            )
            checks.extend((
                _check(
                    "synopsis.replaced_version",
                    proposed_id,
                    confirmation.get("current_version_id"),
                    volatile=True,
                ),
                _check("synopsis.history_preserved", False, current_id == proposed_id),
            ))
            workspace = self.client.get_workspace(state.study_id)
            if not all(item.passed for item in checks):
                return (
                    replace(state, uploads=uploads, workspace=workspace),
                    {"items": []},
                    tuple(checks),
                    denied,
                    history,
                )
        else:
            checks.append(_check("processing.status", "succeeded", processing.get("status")))
            workspace = self.client.get_workspace(state.study_id)

        queue = self.client.get_review_queue(state.study_id)
        actual_facts = _fact_projection(queue)
        expected_facts = tuple(item.model_dump() for item in manifest.expected_facts)
        checks.append(_check("facts", expected_facts, actual_facts))

        workspace_inputs = _mapping(workspace.get("inputs"), "workspace inputs")
        actual_versions = {
            role: _integer(
                _mapping(workspace_inputs.get(role), role)["version"],
                f"{role} version",
            )
            for role in ("synopsis", "template")
        }
        checks.append(_check(
            "input.current_versions", manifest.expected_current_versions, actual_versions
        ))
        workspace_study = _mapping(workspace.get("study"), "workspace study")
        return (
            replace(
                state,
                study_version=_integer(
                    workspace_study["version"], "study version"
                ),
                uploads=uploads,
                workspace=workspace,
            ),
            queue,
            tuple(checks),
            denied,
            history,
        )

    def _review_facts(
        self, state: StudyState, queue: dict[str, object]
    ) -> tuple[CheckResult, ...]:
        items = _items(queue.get("items"), "fact review items")
        for item in items:
            self.client.review_fact(
                str(item["id"]),
                action="approve",
                expected_version=_integer(item["version"], "fact version"),
                explicitly_confirmed=bool(item["critical"]),
            )
        final = self.client.get_review_queue(state.study_id)
        return (_check("fact_review.remaining", 0, len(_items(final.get("items"), "final fact review items"))),)

    def _draft_review_and_export(
        self, state: StudyState, manifest: PilotManifest
    ) -> tuple[
        tuple[CheckResult, ...],
        tuple[ArtifactResult, ...],
        dict[str, str],
        str | None,
        int,
        bool,
    ]:
        checks: list[CheckResult] = []
        for section in SECTIONS:
            self.client.generate_passage(
                state.study_id,
                cast(PassageSection, section),
            )
        listed = self.client.list_passages(state.study_id)
        passages = _items(listed.get("passages"), "passages")
        by_section = {str(item["section"]): item for item in passages}
        actual_text = {section: str(by_section[section]["text"]) for section in SECTIONS}
        passage_text_check = _check("passages", manifest.expected_passages, actual_text)
        checks.append(passage_text_check)
        if not passage_text_check.passed:
            return tuple(checks), (), actual_text, None, 0, False

        passage_denied = False
        if manifest.correction and manifest.correction.kind == "regenerate_passage":
            edit = manifest.unsupported_edit or {}
            section = str(edit["section"])
            passage = by_section[section]
            edited_text = str(passage["text"]).replace(
                str(edit["supported_value"]), str(edit["unsupported_value"])
            )
            self.client.review_passage(
                str(passage["id"]),
                action="edit",
                expected_version=_integer(passage["version"], "passage version"),
                text=edited_text,
                support_ids=tuple(str(item) for item in cast(list[object], passage.get("fact_support_ids", []))),
            )
            blocked_list = self.client.list_passages(state.study_id)
            blocked_passages = _items(blocked_list.get("passages"), "blocked passages")
            blocked = next(item for item in blocked_passages if item["section"] == section)
            actual_findings = tuple(
                (str(item.get("code")), str(blocked["section"]))
                for item in _items(blocked.get("findings"), "passage findings")
            )
            expected_findings = tuple(
                (item.code, item.affected_area) for item in manifest.expected_blockers
            )
            checks.extend((
                _check("passage.blocked_status", "blocked", blocked.get("status")),
                _check(
                    "passage.blocked_findings", expected_findings, actual_findings
                ),
            ))
            workspace = self.client.get_workspace(state.study_id)
            blockers = tuple(
                str(item.get("code"))
                for item in _items(workspace.get("blockers"), "workspace blockers")
            )
            action = _mapping(workspace.get("next_action"), "next action")
            actual_action = action.get("kind")
            checks.extend((
                _check("passage.workspace_blocker", ("BLOCKED_PASSAGE",), blockers),
                _check(
                    "passage.next_action",
                    tuple(item.next_action for item in manifest.expected_blockers),
                    (actual_action,),
                ),
                _check(
                    "passage.declared_next_action",
                    manifest.expected_next_action,
                    actual_action,
                ),
            ))
            if not all(item.passed for item in checks):
                return tuple(checks), (), actual_text, None, 0, passage_denied
            export_command = _mapping(workspace.get("export_command"), "export command")
            try:
                self.client.create_export(state.study_id, export_command)
                denial_result: object = (200, "EXPORT_ALLOWED")
            except PilotHttpError as error:
                denial_result = (error.status_code, error.code)
            checks.append(_check(
                "initial_export", (409, "EXPORT_BLOCKED"), denial_result
            ))
            passage_denied = denial_result == (409, "EXPORT_BLOCKED")
            if not all(item.passed for item in checks):
                return tuple(checks), (), actual_text, None, 0, passage_denied
            self.client.review_passage(
                str(blocked["id"]),
                action="regenerate",
                expected_version=_integer(blocked["version"], "blocked passage version"),
            )
            recovered_list = self.client.list_passages(state.study_id)
            passages = _items(recovered_list.get("passages"), "recovered passages")
            by_section = {str(item["section"]): item for item in passages}
            recovered = by_section[section]
            checks.extend((
                _check("passage.recovered_status", "ready_for_review", recovered.get("status")),
                _check("passage.recovered_findings", (), tuple(_items(recovered.get("findings"), "recovered findings"))),
                _check(
                    "passage.recovered_version",
                    _integer(blocked["version"], "blocked passage version") + 1,
                    recovered.get("version"),
                ),
            ))
            if not all(item.passed for item in checks):
                recovered_text = {
                    name: str(item["text"]) for name, item in by_section.items()
                }
                return (
                    tuple(checks), (), recovered_text, None, 0, passage_denied
                )

        final_text = {section: str(by_section[section]["text"]) for section in SECTIONS}
        final_text_check = _check(
            "passages.after_recovery", manifest.expected_passages, final_text
        )
        checks.append(final_text_check)
        for section in SECTIONS:
            passage = by_section[section]
            findings = _items(passage.get("findings"), "passage findings")
            checks.append(_check(f"passage.{section}.findings", 0, len(findings)))
        if not all(item.passed for item in checks):
            return tuple(checks), (), final_text, None, 0, passage_denied

        for section in SECTIONS:
            passage = by_section[section]
            self.client.review_passage(
                str(passage["id"]),
                action="accept",
                expected_version=_integer(
                    passage["version"], "passage version"
                ),
            )

        workspace = self.client.get_workspace(state.study_id)
        export_command = _mapping(workspace.get("export_command"), "export command")
        export_payload = self.client.create_export(state.study_id, export_command)
        artifact_checks, artifacts, unsupported_count = self._verify_artifacts(
            manifest, export_payload
        )
        checks.extend(artifact_checks)
        snapshot_id = str(export_payload["snapshotId"])
        final_passages = self.client.list_passages(state.study_id)
        final_items = _items(final_passages.get("passages"), "final passages")
        final_text = {str(item["section"]): str(item["text"]) for item in final_items}
        return (
            tuple(checks),
            artifacts,
            final_text,
            snapshot_id,
            unsupported_count,
            passage_denied,
        )

    def _verify_artifacts(
        self, manifest: PilotManifest, export_payload: dict[str, object]
    ) -> tuple[tuple[CheckResult, ...], tuple[ArtifactResult, ...], int]:
        checks: list[CheckResult] = []
        results: list[ArtifactResult] = []
        items = _items(export_payload.get("artifacts"), "export artifacts")
        expected_descriptors = tuple(
            (item.name, item.media_type) for item in manifest.expected_artifacts
        )
        actual_descriptors = tuple(
            (str(item["name"]), str(item["mediaType"]).split(";", 1)[0])
            for item in items
        )
        checks.append(_check("artifacts.descriptors", expected_descriptors, actual_descriptors))
        snapshot_id = str(export_payload["snapshotId"])
        bodies: dict[str, bytes] = {}
        for item in items:
            body = self.client.download_artifact(str(item["downloadUrl"]))
            name = str(item["name"])
            bodies[name] = body
            digest = sha256(body).hexdigest()
            checks.extend((
                _check(
                    f"artifact.{name}.sha256",
                    item["sha256"],
                    digest,
                    volatile=True,
                ),
                _check(
                    f"artifact.{name}.snapshot",
                    snapshot_id,
                    item["snapshotId"],
                    volatile=True,
                ),
            ))
            results.append(ArtifactResult(
                name,
                str(item["mediaType"]),
                digest,
                str(item["snapshotId"]),
                len(body),
            ))

        with ZipFile(BytesIO(bodies["protocol.docx"])) as package:
            names = package.namelist()
            document = package.read("word/document.xml") if "word/document.xml" in names else b""
        checks.extend((
            _check("protocol.document_xml", True, "word/document.xml" in names),
            _check("protocol.unresolved_tokens", False, b"[[" in document),
        ))

        traceability = bodies["traceability.csv"].decode("utf-8")
        reader = csv.DictReader(StringIO(traceability))
        rows = list(reader)
        checks.extend((
            _check("traceability.columns", TRACEABILITY_FIELDS, tuple(reader.fieldnames or ())),
            _check("traceability.sections", set(SECTIONS), {row["section"] for row in rows}),
            _check("traceability.validation", {"pass"}, {row["validation_status"] for row in rows}),
        ))
        approved_values = [item.value for item in manifest.expected_facts]
        unsupported_count = 0
        for row in rows:
            serialized_values = row["fact_value"].split("; ")
            for serialized in serialized_values:
                try:
                    value = json.loads(serialized)
                except (json.JSONDecodeError, TypeError):
                    unsupported_count += 1
                    continue
                if value not in approved_values:
                    unsupported_count += 1
        checks.append(_check("export.unsupported_clinical_facts", 0, unsupported_count))

        scorecard = bodies["scorecard.html"].decode("utf-8")
        missing_dimensions = tuple(
            name for name in SCORECARD_DIMENSIONS
            if name.replace("_", " ").title() not in scorecard
        )
        checks.extend((
            _check("scorecard.dimensions", (), missing_dimensions),
            _check("scorecard.disclaimer", True, SCORECARD_DISCLAIMER in scorecard),
            _check("scorecard.readiness_percentage", False, "readiness percentage" in scorecard.casefold()),
        ))
        return tuple(checks), tuple(results), unsupported_count
