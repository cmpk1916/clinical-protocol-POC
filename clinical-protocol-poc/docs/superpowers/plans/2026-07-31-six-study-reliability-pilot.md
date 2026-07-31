# Six-Study Reliability Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a deterministic six-study, self-service reliability pilot that proves valid synthetic studies export directly and expected mistakes fail closed, explain the correction, preserve history, and recover without exporting unsupported clinical content.

**Architecture:** Add versioned manifest-driven DOCX packs and a synchronous HTTP pilot client that exercises the same FastAPI interfaces as the local application. Strengthen workspace correction guidance and passage validation persistence, then compare every observed fact, blocker, action, passage, version, and artifact with checked-in gold expectations. Render per-run JSON and Markdown reports and require two clean-stack runs to agree on deterministic outputs.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, SQLAlchemy 2, Alembic, httpx, Pytest, deterministic OOXML/DOCX generation, TypeScript 5.8, React 19, Next.js 15, Node test runner, Testing Library, Docker Compose, Make.

## Global Constraints

- The pilot contains exactly six synthetic self-service study packs: three direct-success studies and three mistake-and-recovery studies.
- All pilot studies enter through the real document upload, processing, review, drafting, validation, and export HTTP interfaces; seeded database scenarios do not count as pilot results.
- All clinical content is synthetic. Real sponsor, patient, confidential, clinical, regulatory, or production documents are prohibited.
- Corrections are explicit user-equivalent actions; the application never invents facts, changes source meaning, accepts reviews, or rewrites unsupported clinical content automatically.
- Deterministic synopsis content findings recommend `Upload corrected synopsis`; only transient technical processing failures recommend retry.
- Template contract failures keep the invalid version noncurrent and recommend uploading a corrected template.
- Unsupported passage edits are persisted as blocked versions with exact deterministic findings; they cannot be accepted or exported until explicitly regenerated or corrected and revalidated.
- Every successful export contains exactly `protocol.docx`, `traceability.csv`, and `scorecard.html` linked to one snapshot, with verified SHA-256 hashes and no unresolved template tokens.
- The pass threshold is exactly 6/6 studies, all expected pre-correction denials, all expected recoveries, `unsupported clinical facts exported: 0`, and agreement across two clean-stack runs.
- Run-specific study IDs, file IDs, timestamps, snapshot IDs, artifact IDs, and artifact hashes are recorded but excluded from deterministic cross-run comparison.
- Reports never claim clinical, regulatory, submission, operational, production, or readiness status and never display a composite readiness percentage.
- No live model calls, web retrieval, new protocol sections, multiple-arm extraction, new dose units, new frequency vocabularies, multi-user behavior, or remote hosting are added.

---

### Task 1: Versioned Manifests and Deterministic DOCX Packs

**Files:**
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/__init__.py`
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/manifest.py`
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/fixtures.py`
- Create: `clinical-protocol-poc/backend/tests/unit/reliability/test_manifests.py`
- Create: `clinical-protocol-poc/backend/tests/unit/reliability/test_fixtures.py`
- Create: `clinical-protocol-poc/fixtures/reliability-pilot/standard/*`
- Create: `clinical-protocol-poc/fixtures/reliability-pilot/vocabulary-variation/*`
- Create: `clinical-protocol-poc/fixtures/reliability-pilot/value-variation/*`
- Create: `clinical-protocol-poc/fixtures/reliability-pilot/missing-dose/*`
- Create: `clinical-protocol-poc/fixtures/reliability-pilot/broken-template/*`
- Create: `clinical-protocol-poc/fixtures/reliability-pilot/unsupported-passage-edit/*`

**Interfaces:**
- Produces `PilotManifest`, `ExpectedFact`, `ExpectedBlocker`, `CorrectionSpec`, and `ExpectedArtifact` Pydantic models with `extra="forbid"`.
- Produces `load_manifest(path: Path) -> PilotManifest` and `load_pilot_manifests(root: Path) -> tuple[PilotManifest, ...]`.
- Produces `build_reliability_fixtures(root: Path) -> tuple[Path, ...]`, which writes byte-identical DOCX files and canonical JSON manifests.
- Uses existing `build_template(sections: list[str]) -> bytes` and `deterministic_package(entries: dict[str, bytes]) -> bytes`.

- [ ] **Step 1: Write failing schema tests for the exact six-pack contract**

Create `test_manifests.py` with these assertions:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from protocol_poc.reliability.manifest import PilotManifest, load_pilot_manifests


FIXTURES = Path(__file__).parents[4] / "fixtures" / "reliability-pilot"


def test_loads_exactly_six_versioned_manifests() -> None:
    manifests = load_pilot_manifests(FIXTURES)

    assert [item.study_key for item in manifests] == [
        "standard",
        "vocabulary-variation",
        "value-variation",
        "missing-dose",
        "broken-template",
        "unsupported-passage-edit",
    ]
    assert all(item.schema_version == 1 for item in manifests)
    assert sum(item.initial_outcome == "direct_success" for item in manifests) == 3
    assert sum(item.initial_outcome == "blocked_then_recover" for item in manifests) == 3


def test_manifest_rejects_run_specific_gold_values() -> None:
    with pytest.raises(ValidationError):
        PilotManifest.model_validate({
            "schema_version": 1,
            "study_key": "standard",
            "study_name": "Synthetic standard",
            "initial_outcome": "direct_success",
            "inputs": {},
            "expected_facts": [],
            "expected_blockers": [],
            "expected_next_action": "review_facts",
            "correction": None,
            "expected_passages": {},
            "expected_artifacts": [],
            "snapshot_id": "run-specific-id",
        })
```

- [ ] **Step 2: Run the manifest tests and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/reliability/test_manifests.py -v
```

Expected: collection fails because `protocol_poc.reliability.manifest` does not exist.

- [ ] **Step 3: Implement strict manifest models and stable loading order**

In `manifest.py`, define the core contract:

```python
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedFact(StrictModel):
    kind: str
    value: dict[str, object]
    critical: bool = False


class ExpectedBlocker(StrictModel):
    code: str
    affected_area: str
    next_action: str


class CorrectionSpec(StrictModel):
    kind: Literal["replace_synopsis", "upload_corrected_template", "regenerate_passage"]
    filename: str | None = None
    section: str | None = None


class ExpectedArtifact(StrictModel):
    name: Literal["protocol.docx", "traceability.csv", "scorecard.html"]
    media_type: str


class PilotManifest(StrictModel):
    schema_version: Literal[1]
    study_key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    study_name: str
    initial_outcome: Literal["direct_success", "blocked_then_recover"]
    inputs: dict[str, str]
    input_sha256: dict[str, str]
    expected_facts: tuple[ExpectedFact, ...]
    expected_blockers: tuple[ExpectedBlocker, ...]
    expected_next_action: str
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
        return self


def load_manifest(path: Path) -> PilotManifest:
    return PilotManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_pilot_manifests(root: Path) -> tuple[PilotManifest, ...]:
    by_key = {path.parent.name: load_manifest(path) for path in root.glob("*/manifest.json")}
    order = (
        "standard", "vocabulary-variation", "value-variation",
        "missing-dose", "broken-template", "unsupported-passage-edit",
    )
    if set(by_key) != set(order):
        raise ValueError("reliability pilot must contain exactly the six declared studies")
    return tuple(by_key[key] for key in order)
```

- [ ] **Step 4: Write failing deterministic fixture tests**

In `test_fixtures.py`, build twice in separate temporary directories and require identical bytes and hashes:

```python
from hashlib import sha256

from protocol_poc.reliability.fixtures import build_reliability_fixtures
from protocol_poc.reliability.manifest import load_pilot_manifests


def test_builder_is_byte_identical_and_hashes_match_manifests(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_reliability_fixtures(first)
    build_reliability_fixtures(second)

    assert {
        path.relative_to(first): path.read_bytes() for path in first.rglob("*") if path.is_file()
    } == {
        path.relative_to(second): path.read_bytes() for path in second.rglob("*") if path.is_file()
    }
    for manifest in load_pilot_manifests(first):
        pack = first / manifest.study_key
        for logical_name, filename in manifest.inputs.items():
            digest = sha256((pack / filename).read_bytes()).hexdigest()
            assert digest == manifest.input_sha256[logical_name]
```

- [ ] **Step 5: Implement the parameterized deterministic DOCX builder and six declarations**

In `fixtures.py`, reuse the existing OOXML pattern but parameterize headings, values, optional duration, and template tokens:

```python
@dataclass(frozen=True)
class SynopsisSource:
    identity_heading: str
    short_title: str
    objectives_heading: str
    objective: str
    endpoints_heading: str
    endpoint: str
    arms_heading: str
    arm_line: str
    population_heading: str
    population: str
    eligibility_heading: str
    eligibility: str
    duration: str | None


def build_synopsis(source: SynopsisSource) -> bytes:
    lines = [
        source.identity_heading, f"Short title: {source.short_title}",
        source.objectives_heading, f"Objective: {source.objective}",
        source.endpoints_heading, f"Endpoint: {source.endpoint}",
        source.arms_heading, source.arm_line,
        source.population_heading, f"Population: {source.population}",
        source.eligibility_heading, f"Eligibility: {source.eligibility}",
    ]
    if source.duration is not None:
        lines.append(f"Duration: {source.duration}")
    return _document(lines)
```

Declare all six packs in a stable tuple. Use supported variations only:

- `standard`: ten facts and all canonical headings.
- `vocabulary-variation`: `Arms / Interventions`, `Study Population`, and `Eligibility Criteria`, with varied capitalization and whitespace.
- `value-variation`: `7.5 mg once daily`, `Week 12`, and a singular `1 week` duration.
- `missing-dose`: initial arm line without dose/frequency plus `corrected-synopsis.docx` with `12 mg once daily`.
- `broken-template`: initial template missing only `[[SECTION:eligibility]]` plus a fully conforming `corrected-template.docx`.
- `unsupported-passage-edit`: valid inputs plus an `unsupported_edit` changing the supported dose to `99 mg` in `study_design`.

Write each manifest only after calculating all input SHA-256 hashes. Serialize with `model_dump_json(indent=2)` plus a trailing newline. The four expected passage strings must match `LocalComposer` output for that pack exactly.

- [ ] **Step 6: Build the checked-in packs and verify tests GREEN**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -c 'from pathlib import Path; from protocol_poc.reliability.fixtures import build_reliability_fixtures; build_reliability_fixtures(Path("../fixtures/reliability-pilot"))'
.venv/bin/python -m pytest tests/unit/reliability/test_manifests.py tests/unit/reliability/test_fixtures.py -v
.venv/bin/ruff check src/protocol_poc/reliability tests/unit/reliability
.venv/bin/mypy src/protocol_poc/reliability
```

Expected: all tests and static checks pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add clinical-protocol-poc/backend/src/protocol_poc/reliability clinical-protocol-poc/backend/tests/unit/reliability clinical-protocol-poc/fixtures/reliability-pilot
git commit -m "test: add six reliability study packs"
```

---

### Task 2: Safe Backend Correction Classification

**Files:**
- Modify: `clinical-protocol-poc/backend/src/protocol_poc/studies/workspace.py`
- Modify: `clinical-protocol-poc/backend/tests/unit/studies/test_workspace.py`
- Modify: `clinical-protocol-poc/backend/tests/integration/studies/test_workspace_api.py`

**Interfaces:**
- Expands `WorkspaceBlocker` to `WorkspaceBlocker(code: str, message: str, affected_area: str | None = None, blocking_reason: str = "Progress is blocked until this finding is resolved.")`.
- Produces `_failed_processing_action(processing: WorkspaceProcessing) -> WorkspaceAction`.
- Deterministic `SYNOPSIS_*` findings produce action kind `upload_synopsis` and label `Upload corrected synopsis`.
- Empty/technical failed attempts produce action kind `retry_processing` and preserve the failed attempt ID.

- [ ] **Step 1: Replace the existing retry expectation with failing source-versus-technical tests**

Update `test_workspace.py` so `SYNOPSIS_DOSE_MISSING` expects:

```python
assert summary.next_action.kind == "upload_synopsis"
assert summary.next_action.label == "Upload corrected synopsis"
assert summary.next_action.target_id is None
assert summary.blockers[0].affected_area == "arms_interventions"
assert summary.blockers[0].blocking_reason == (
    "Synopsis processing cannot succeed until the source content is corrected."
)
```

Add a separate attempt with `error_code="processor_unavailable"` and no deterministic findings:

```python
assert summary.next_action.kind == "retry_processing"
assert summary.next_action.target_id == "attempt-technical"
```

Add an API assertion that the response contains `affected_area` and `blocking_reason` and does not recommend unchanged-file retry for `SYNOPSIS_DOSE_MISSING`.

- [ ] **Step 2: Run targeted backend tests and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/studies/test_workspace.py tests/integration/studies/test_workspace_api.py -v
```

Expected: the deterministic finding still returns `retry_processing`, and the detail fields are absent.

- [ ] **Step 3: Preserve finding fields and classify failed processing actions**

Change processing finding conversion to retain `field`:

```python
WorkspaceBlocker(
    code=str(item.get("code", "PROCESSING_FAILED")),
    message=str(item.get("message", "Synopsis processing did not complete.")),
    affected_area=str(item["field"]) if item.get("field") else "synopsis",
    blocking_reason=(
        "Synopsis processing cannot succeed until the source content is corrected."
        if str(item.get("code", "")).startswith("SYNOPSIS_")
        else "Synopsis processing did not complete, so downstream review and export remain blocked."
    ),
)
```

Add the classifier:

```python
@staticmethod
def _failed_processing_action(processing: WorkspaceProcessing) -> WorkspaceAction:
    if any(item.code.startswith("SYNOPSIS_") for item in processing.findings):
        return WorkspaceAction("upload_synopsis", "Upload corrected synopsis")
    return WorkspaceAction(
        "retry_processing",
        "Retry synopsis processing",
        target_id=processing.attempt_id,
    )
```

Use it only for `processing.status == "failed"`. Do not change retry behavior for transient failures.

- [ ] **Step 4: Run targeted tests and backend static checks GREEN**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/studies/test_workspace.py tests/integration/studies/test_workspace_api.py -v
.venv/bin/ruff check src/protocol_poc/studies/workspace.py tests/unit/studies/test_workspace.py tests/integration/studies/test_workspace_api.py
.venv/bin/mypy src/protocol_poc/studies/workspace.py
```

Expected: all commands pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add clinical-protocol-poc/backend/src/protocol_poc/studies/workspace.py clinical-protocol-poc/backend/tests/unit/studies/test_workspace.py clinical-protocol-poc/backend/tests/integration/studies/test_workspace_api.py
git commit -m "fix: recommend corrected source for extraction findings"
```

---

### Task 3: Clear Correction Guidance in the Workspace

**Files:**
- Modify: `clinical-protocol-poc/frontend/src/lib/types.ts`
- Modify: `clinical-protocol-poc/frontend/src/lib/api.ts`
- Modify: `clinical-protocol-poc/frontend/src/features/studies/WorkspaceGuide.tsx`
- Modify: `clinical-protocol-poc/frontend/tests/studies/WorkspaceGuide.test.tsx`

**Interfaces:**
- Expands `WorkspaceBlocker` to `{ code: string; message: string; affectedArea: string | null; blockingReason: string }`.
- Maps backend `affected_area` and `blocking_reason` exactly once in `toWorkspaceSummary()`.
- Displays the affected area and blocking reason beside each finding while keeping the synopsis upload card enabled.

- [ ] **Step 1: Write a failing component test for corrected-source guidance**

Change the processing summary fixture to use:

```typescript
blockers: [{
  code: "SYNOPSIS_DOSE_MISSING",
  message: "Intervention values must include an N mg dose and once daily frequency.",
  affectedArea: "arms_interventions",
  blockingReason: "Synopsis processing cannot succeed until the source content is corrected.",
}],
nextAction: {
  kind: "upload_synopsis",
  label: "Upload corrected synopsis",
  targetId: null,
  href: null,
},
```

Assert:

```typescript
assert.ok(screen.getByText("Affected area: arms interventions"));
assert.ok(screen.getByText(/cannot succeed until the source content is corrected/i));
assert.ok(screen.getByRole("heading", { name: "Upload corrected synopsis" }));
assert.equal(screen.getByLabelText("Synopsis DOCX").hasAttribute("disabled"), false);
assert.equal(screen.queryByRole("button", { name: /retry synopsis processing/i }), null);
```

Add a mapping test in `WorkspaceGuide.test.tsx` or a focused `api` test that sends snake-case blocker fields and expects camel-case values.

- [ ] **Step 2: Run the component test and verify RED**

Run:

```bash
cd clinical-protocol-poc/frontend
pnpm test -- tests/studies/WorkspaceGuide.test.tsx
```

Expected: affected-area and blocking-reason text are not rendered.

- [ ] **Step 3: Implement type mapping and accessible finding detail**

In `api.ts`, declare the wire shape separately and map it:

```typescript
type WorkspaceBlockerPayload = {
  code: string;
  message: string;
  affected_area: string | null;
  blocking_reason: string;
};

function mapBlocker(item: WorkspaceBlockerPayload): WorkspaceBlocker {
  return {
    code: item.code,
    message: item.message,
    affectedArea: item.affected_area,
    blockingReason: item.blocking_reason,
  };
}
```

Map both `payload.blockers` and `payload.processing.findings`. In `WorkspaceGuide.tsx`, render:

```tsx
<li key={`${blocker.code}-${blocker.affectedArea ?? "general"}`}>
  <p>{blocker.message} <span className="finding-code">({blocker.code})</span></p>
  {blocker.affectedArea ? (
    <p><strong>Affected area:</strong> {blocker.affectedArea.replaceAll("_", " ")}</p>
  ) : null}
  <p><strong>Why progress is blocked:</strong> {blocker.blockingReason}</p>
</li>
```

Do not add `upload_synopsis` to `commandAction`; the existing fallback correctly directs the user to the matching input card.

- [ ] **Step 4: Run frontend tests and static checks GREEN**

Run:

```bash
cd clinical-protocol-poc/frontend
pnpm test -- tests/studies/WorkspaceGuide.test.tsx
pnpm lint
pnpm typecheck
```

Expected: all commands pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add clinical-protocol-poc/frontend/src/lib/types.ts clinical-protocol-poc/frontend/src/lib/api.ts clinical-protocol-poc/frontend/src/features/studies/WorkspaceGuide.tsx clinical-protocol-poc/frontend/tests/studies/WorkspaceGuide.test.tsx
git commit -m "feat: explain safe workspace corrections"
```

---

### Task 4: Persist Unsupported Passage Findings and Recover Explicitly

**Files:**
- Create: `clinical-protocol-poc/backend/migrations/versions/0013_passage_validation_findings.py`
- Modify: `clinical-protocol-poc/backend/src/protocol_poc/drafting/models.py`
- Modify: `clinical-protocol-poc/backend/src/protocol_poc/drafting/review_service.py`
- Modify: `clinical-protocol-poc/backend/src/protocol_poc/drafting/routes.py`
- Modify: `clinical-protocol-poc/backend/src/protocol_poc/quality/service.py`
- Modify: `clinical-protocol-poc/backend/tests/unit/drafting/test_passage_review.py`
- Modify: `clinical-protocol-poc/backend/tests/integration/drafting/test_generate_passage.py`
- Modify: `clinical-protocol-poc/backend/tests/integration/export/test_artifact_orchestration.py`
- Modify: `clinical-protocol-poc/frontend/src/features/drafting/PassageEditor.tsx`
- Modify: `clinical-protocol-poc/frontend/tests/drafting/PassageEditor.test.tsx`
- Modify: `clinical-protocol-poc/frontend/tests/e2e/blocked-export.spec.ts`

**Interfaces:**
- Adds `PassageVersion.validation_findings: list[dict[str, str]]`, non-null with default `[]`.
- Changes `PassageReviewService.edit(...) -> Passage` to persist any nonblank proposed text as a new version, derive support links from current approved facts, and set status `blocked` when deterministic blocker findings exist.
- Keeps blank edits, stale versions, cross-tenant access, archived studies, and invalid support state fail-closed.
- `GET /api/studies/{study_id}/passages` returns exact persisted `{code, severity, message, source}` findings.
- Regeneration creates a clean new current version, preserves the blocked version in history, and returns the passage to `ready_for_review`.

- [ ] **Step 1: Write failing persistence, export-denial, and regeneration tests**

Replace the unsupported text case in `test_edit_fails_closed_and_derives_exact_support_from_the_template` with a dedicated journey:

```python
edited = client.post(
    f"/api/passages/{passage_id}/review",
    headers=headers,
    json={
        "action": "edit",
        "expected_version": 1,
        "text": generated.json()["text"].replace("10 mg", "99 mg"),
        "support_ids": ["dose-a"],
    },
)
listed = client.get("/api/studies/study-a/passages", headers=headers).json()["passages"][0]

assert edited.status_code == 200
assert (listed["status"], listed["version"]) == ("blocked", 2)
assert listed["findings"] == [{
    "code": "UNSUPPORTED_DOSE",
    "severity": "blocker",
    "message": "Dose 99 mg is not an approved fact",
    "source": "deterministic",
}]
```

Seed the remaining accepted sections and assert export returns `409 EXPORT_BLOCKED`. Then regenerate and assert:

```python
regenerated = client.post(
    f"/api/passages/{passage_id}/review",
    headers=headers,
    json={"action": "regenerate", "expected_version": 2},
)
assert regenerated.json()["status"] == "ready_for_review"
assert regenerated.json()["version"] == 3
assert client.get("/api/studies/study-a/passages", headers=headers).json()["passages"][0]["findings"] == []
```

Add a unit assertion that `accept()` rejects any current version with a blocker in `validation_findings`, even if passage status is incorrectly set to `ready_for_review`.

- [ ] **Step 2: Run targeted backend tests and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/drafting/test_passage_review.py tests/integration/drafting/test_generate_passage.py tests/integration/export/test_artifact_orchestration.py -v
```

Expected: the edit returns `409 PASSAGEBLOCKED`, no findings are persisted, and the model lacks `validation_findings`.

- [ ] **Step 3: Add the migration and model field**

In migration `0013_passage_validation_findings.py`, set `revision = "0013_passage_validation_findings"` and `down_revision = "0012_passage_current_unique"`, matching the actual revision identifier in `0012_passage_current_version_unique.py`. Add the column through Alembic's batch boundary so SQLite and PostgreSQL follow the same path:

```python
with op.batch_alter_table("passage_versions") as batch_op:
    batch_op.add_column(
        sa.Column(
            "validation_findings",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        )
    )
    batch_op.alter_column("validation_findings", server_default=None)
```

The downgrade drops only this column. In `PassageVersion`, add:

```python
validation_findings: Mapped[list[dict[str, str]]] = mapped_column(
    JSON, nullable=False, default=list
)
```

- [ ] **Step 4: Persist blocked edits and return exact findings**

Refactor `edit()` so it:

1. locks the active passage and rejects blank text;
2. composes the authoritative section to derive current claims and support IDs rather than trusting submitted `support_ids`;
3. validates the proposed text;
4. marks the prior version noncurrent and creates version `N+1` with serialized findings;
5. writes claims and support links using the authoritative current context;
6. sets `passage.status = "blocked"` when any finding severity is `blocker`, otherwise `ready_for_review`; and
7. appends `passage.edited` audit metadata containing finding codes.

Serialize findings with:

```python
finding_payload = [
    {
        "code": item.code,
        "severity": item.severity,
        "message": item.message,
        "source": item.source,
    }
    for item in findings
]
```

In `accept()`, require `not version.validation_findings`. In `_passage_payload()`, return `version.validation_findings` instead of `[]`. Ensure generation and regeneration initialize clean finding lists.

In `QualityService.calculate()`, add one `QualityBlocker("UNSUPPORTED_CONTENT", finding["message"], passage.id)` for each blocker finding on a current passage version. This makes quality and export remain fail-closed even if status is corrupted.

- [ ] **Step 5: Run backend tests, migration tests, and static checks GREEN**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/drafting/test_passage_review.py tests/integration/drafting/test_generate_passage.py tests/integration/export/test_artifact_orchestration.py tests/integration/ingest/test_migration.py -v
.venv/bin/ruff check src/protocol_poc/drafting src/protocol_poc/quality migrations/versions/0013_passage_validation_findings.py tests/unit/drafting tests/integration/drafting
.venv/bin/mypy src/protocol_poc/drafting src/protocol_poc/quality
```

Expected: all commands pass.

- [ ] **Step 6: Write a failing frontend recovery test**

In `PassageEditor.test.tsx`, use a versioned `reviewPassage` API that returns a blocked passage for edit and a clean `ready_for_review` passage for regenerate. Assert:

```typescript
await user.clear(screen.getByLabelText("Passage text"));
await user.type(screen.getByLabelText("Passage text"), "Participants receive 99 mg once daily.");
await user.click(screen.getByRole("button", { name: "Validate passage" }));

assert.ok(await screen.findByText("Dose 99 mg is not an approved fact"));
assert.equal(screen.getByRole("button", { name: "Accept passage" }).hasAttribute("disabled"), true);
assert.equal(screen.getByRole("button", { name: "Regenerate passage" }).hasAttribute("disabled"), false);
```

The test must verify that `Validate passage` sends the versioned `edit` command and that regeneration uses the returned version.

- [ ] **Step 7: Make validation save authoritative blocked state and verify frontend GREEN**

Keep a local `currentVersion` state initialized from `passage.version`. After every authoritative response, update text, findings, and current version. Make `Validate passage` call `command("edit")`; remove the dead unsaved `validatePassage` fallback from this server-backed path. Keep regeneration available while findings exist.

Run:

```bash
cd clinical-protocol-poc/frontend
pnpm test -- tests/drafting/PassageEditor.test.tsx
pnpm lint
pnpm typecheck
```

Expected: all commands pass.

- [ ] **Step 8: Add and run the browser recovery assertion**

Extend `blocked-export.spec.ts` with a self-service valid study that edits `study_design` from its supported dose to `99 mg`, selects **Validate passage**, sees `UNSUPPORTED_DOSE`, cannot create export, regenerates the passage, accepts it, and then sees enabled **Create export**.

Run:

```bash
cd clinical-protocol-poc
E2E_TESTS=tests/e2e/blocked-export.spec.ts make e2e
```

Expected: the browser test passes against the release stack.

- [ ] **Step 9: Commit Task 4**

```bash
git add clinical-protocol-poc/backend/migrations/versions/0013_passage_validation_findings.py clinical-protocol-poc/backend/src/protocol_poc/drafting clinical-protocol-poc/backend/src/protocol_poc/quality/service.py clinical-protocol-poc/backend/tests/unit/drafting clinical-protocol-poc/backend/tests/integration/drafting clinical-protocol-poc/backend/tests/integration/export/test_artifact_orchestration.py clinical-protocol-poc/frontend/src/features/drafting/PassageEditor.tsx clinical-protocol-poc/frontend/tests/drafting/PassageEditor.test.tsx clinical-protocol-poc/frontend/tests/e2e/blocked-export.spec.ts
git commit -m "feat: persist blocked passage corrections"
```

---

### Task 5: Tenant-Scoped Pilot HTTP Client

**Files:**
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/client.py`
- Create: `clinical-protocol-poc/backend/tests/unit/reliability/test_client.py`

**Interfaces:**
- Produces `PilotClient(base_url: str, tenant_id: str, actor_id: str, transport: httpx.BaseTransport | None = None, http_client: httpx.Client | None = None)` as a context manager. Production CLI use owns its client; integration tests may inject FastAPI's `TestClient` without using private transports.
- Produces typed methods `create_study`, `upload_input`, `get_workspace`, `process_synopsis`, `get_review_queue`, `review_fact`, `generate_passage`, `list_passages`, `review_passage`, `preview_replacement`, `confirm_replacement`, `create_export`, and `download_artifact`.
- Produces `PilotHttpError(status_code: int, code: str, payload: dict[str, object])` for expected fail-closed assertions.
- Every request sends `X-Tenant-ID` and `X-Actor-ID`; the client never uses test seed routes.

- [ ] **Step 1: Write failing request-shape and error tests with `httpx.MockTransport`**

Create a handler that records requests and returns fixed API payloads. Assert:

```python
with PilotClient(
    "http://pilot.test",
    "pilot-tenant",
    "pilot-runner",
    transport=httpx.MockTransport(handler),
) as client:
    study = client.create_study("Synthetic standard")

assert study["id"] == "study-1"
assert recorded[0].headers["X-Tenant-ID"] == "pilot-tenant"
assert recorded[0].headers["X-Actor-ID"] == "pilot-runner"
assert recorded[0].url.path == "/api/studies"
```

Return a `409` payload and assert:

```python
with pytest.raises(PilotHttpError) as captured:
    client.create_export("study-1", command)
assert (captured.value.status_code, captured.value.code) == (409, "EXPORT_BLOCKED")
assert captured.value.payload["detail"]["blockers"]
```

- [ ] **Step 2: Run the client tests and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/reliability/test_client.py -v
```

Expected: import fails because `reliability.client` does not exist.

- [ ] **Step 3: Implement the minimal synchronous client**

Use one private request boundary:

```python
def _request(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
    response = self._client.request(method, path, **kwargs)
    payload = response.json()
    if response.is_error:
        detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
        code = detail.get("code", "HTTP_ERROR") if isinstance(detail, dict) else "HTTP_ERROR"
        raise PilotHttpError(response.status_code, str(code), payload)
    if not isinstance(payload, dict):
        raise PilotHttpError(response.status_code, "INVALID_RESPONSE", {"body": payload})
    return payload
```

For multipart upload, open only the manifest-declared file and send:

```python
files = {"file": (path.name, path.read_bytes(), DOCX_CONTENT_TYPE)}
return self._request("POST", f"/api/studies/{study_id}/inputs", data={"role": role}, files=files)
```

Keep raw snake-case API payloads in this client; manifest comparison owns normalization.

- [ ] **Step 4: Run client tests and static checks GREEN**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/reliability/test_client.py -v
.venv/bin/ruff check src/protocol_poc/reliability/client.py tests/unit/reliability/test_client.py
.venv/bin/mypy src/protocol_poc/reliability/client.py
```

Expected: all commands pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add clinical-protocol-poc/backend/src/protocol_poc/reliability/client.py clinical-protocol-poc/backend/tests/unit/reliability/test_client.py
git commit -m "test: add self-service pilot HTTP client"
```

---

### Task 6: Six Study Journeys and Recovery Assertions

**Files:**
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/results.py`
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/runner.py`
- Create: `clinical-protocol-poc/backend/tests/unit/reliability/test_runner.py`
- Create: `clinical-protocol-poc/backend/tests/integration/reliability/test_six_study_pilot.py`

**Interfaces:**
- Produces immutable `CheckResult`, `ArtifactResult`, `StudyRunResult`, and `PilotRunResult` dataclasses.
- Produces `PilotRunner(client: PilotClient, fixture_root: Path).run(manifests: tuple[PilotManifest, ...]) -> PilotRunResult`.
- Produces `deterministic_projection(result: PilotRunResult) -> dict[str, object]`, excluding run-specific identifiers, timestamps, and hashes.
- A failed check records exact expected and actual values and causes the study to fail; it does not stop later studies from running.

- [ ] **Step 1: Write failing runner unit tests for mismatch accumulation and continuation**

Use a fake client and two minimal manifests. Make the first return a wrong blocker and the second succeed. Assert:

```python
result = PilotRunner(fake_client, fixture_root).run((first, second))

assert [item.study_key for item in result.studies] == ["first", "second"]
assert result.studies[0].passed is False
assert result.studies[0].checks[0].expected == "SYNOPSIS_DOSE_MISSING"
assert result.studies[0].checks[0].actual == "PROCESSING_FAILED"
assert result.studies[1].passed is True
assert result.passed is False
```

Add a test proving manifest file hash mismatch fails before `upload_input` is called.

- [ ] **Step 2: Run runner unit tests and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/reliability/test_runner.py -v
```

Expected: `results` and `runner` modules do not exist.

- [ ] **Step 3: Implement common workflow phases**

Implement five focused private methods with the signatures declared in the **Interfaces** block for this task:

- `_verify_fixture_hashes` resolves every filename under `fixture_root / manifest.study_key`, rejects path traversal with `resolved.is_relative_to(pack_root.resolve())`, calculates SHA-256, and returns one named check per file.
- `_create_and_upload` creates the study, uploads synopsis first and template second, and returns a `StudyState` carrying the stable manifest key plus the run-specific study, upload, current input, and study-version values needed for later commands.
- `_process_and_compare_facts` processes only the current synopsis version, fetches the authoritative fact-review queue, and compares the stable fact projection shown below.
- `_review_facts` approves each current candidate once, sends explicit confirmation only for critical facts, and verifies the final queue is empty.
- `_draft_review_and_export` generates sections in `synopsis`, `objectives_endpoints`, `study_design`, `eligibility` order, applies the manifest-specific recovery before acceptance when required, accepts each blocker-free current version, creates one export, downloads all artifacts, and returns checks plus artifact results.

Define `StudyState` as a private frozen dataclass in `runner.py` with `study_id: str`, `study_version: int`, `uploads: dict[str, dict[str, object]]`, and `workspace: dict[str, object]`. Each method returns checks rather than raising for expected/actual mismatches; unexpected transport or malformed-response failures are caught at the per-study boundary and recorded as an `INFRASTRUCTURE_FAILURE` check so later studies still run.

Fact comparison must preserve API queue order and compare only stable fields:

```python
actual = tuple(
    {
        "kind": item["kind"],
        "value": item["current_value"],
        "critical": item["critical"],
    }
    for item in queue["items"]
)
expected = tuple(item.model_dump() for item in manifest.expected_facts)
```

Approve every fact with `explicitly_confirmed=True` only when `critical` is true. Generate the four sections in the manifest’s declared order, compare passage text before acceptance, and accept only passages with no findings.

- [ ] **Step 4: Implement all three explicit recovery strategies**

For `replace_synopsis`:

1. process the missing-dose file;
2. assert `SYNOPSIS_DOSE_MISSING`, `upload_synopsis`, and absent export eligibility;
3. upload `corrected-synopsis.docx` and assert replacement confirmation is required;
4. preview and confirm replacement with current input and study versions;
5. assert current synopsis version is 2, the initial version ID differs and remains recorded in the run, and corrected candidate facts appear.

For `upload_corrected_template`:

1. assert initial upload status `conformance_failed` with exactly one `TEMPLATE_TOKEN_MISSING` for `eligibility`;
2. assert no current template and no export command;
3. upload `corrected-template.docx` and assert it becomes the current conforming version;
4. retain the invalid upload version ID in `StudyRunResult.input_history`.

For `regenerate_passage`:

1. create valid candidate facts and generate passages;
2. submit the manifest’s `99 mg` edit to `study_design`;
3. assert passage status `blocked` and exact finding `UNSUPPORTED_DOSE`;
4. assert workspace blocker `BLOCKED_PASSAGE` and export endpoint `409 EXPORT_BLOCKED`;
5. regenerate from the blocked version, assert findings clear and version history advances;
6. accept only the regenerated passage.

- [ ] **Step 5: Verify artifacts and the zero-unsupported-content invariant**

For each exported artifact:

```python
body = client.download_artifact(item["downloadUrl"])
assert sha256(body).hexdigest() == item["sha256"]
assert item["snapshotId"] == export_payload["snapshotId"]
```

Use `zipfile.ZipFile` to require `word/document.xml` and no `[[` token in `protocol.docx`. Parse `traceability.csv` with `csv.DictReader`, require the fixed eight columns and at least one row for every section, and require every `validation_status` to be `pass`. Decode `scorecard.html`, require all six dimension names and the synthetic POC disclaimer, and reject `readiness percentage` case-insensitively.

Compute `exported_unsupported_clinical_fact_count` by comparing exported traceability fact values with the manifest-approved fact values. The only passing value is `0`.

- [ ] **Step 6: Write and run an integration pilot against a FastAPI test server**

In `test_six_study_pilot.py`, start the real app with temporary SQLite and local storage, inject FastAPI's public `TestClient` through the `http_client` constructor argument, load all six manifests, and run:

```python
with TestClient(app) as test_client:
    client = PilotClient(
        "http://testserver",
        "pilot-tenant",
        "pilot-runner",
        http_client=test_client,
    )
    result = PilotRunner(client, FIXTURE_ROOT).run(load_pilot_manifests(FIXTURE_ROOT))

assert result.passed is True
assert len(result.studies) == 6
assert all(item.passed for item in result.studies)
assert result.exported_unsupported_clinical_fact_count == 0
assert sum(item.initial_export_denied for item in result.studies) == 3
assert sum(bool(item.artifacts) for item in result.studies) == 6
```

- [ ] **Step 7: Run runner tests and static checks GREEN**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/reliability/test_runner.py tests/integration/reliability/test_six_study_pilot.py -v
.venv/bin/ruff check src/protocol_poc/reliability tests/unit/reliability tests/integration/reliability
.venv/bin/mypy src/protocol_poc/reliability
```

Expected: all six studies pass and the unsupported exported fact count is zero.

- [ ] **Step 8: Commit Task 6**

```bash
git add clinical-protocol-poc/backend/src/protocol_poc/reliability/results.py clinical-protocol-poc/backend/src/protocol_poc/reliability/runner.py clinical-protocol-poc/backend/tests/unit/reliability/test_runner.py clinical-protocol-poc/backend/tests/integration/reliability/test_six_study_pilot.py
git commit -m "test: run six self-service reliability journeys"
```

---

### Task 7: JSON/Markdown Reports and Clean-Run Repeatability

**Files:**
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/report.py`
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/cli.py`
- Create: `clinical-protocol-poc/backend/src/protocol_poc/reliability/__main__.py`
- Create: `clinical-protocol-poc/backend/tests/unit/reliability/test_report.py`
- Create: `clinical-protocol-poc/backend/tests/unit/reliability/test_cli.py`
- Modify: `clinical-protocol-poc/Makefile`
- Modify: `clinical-protocol-poc/../.gitignore`

**Interfaces:**
- Produces `render_json(result: PilotRunResult) -> str` and `render_markdown(result: PilotRunResult) -> str`.
- Produces `compare_repeatability(first: PilotRunResult, second: PilotRunResult) -> tuple[CheckResult, ...]` using deterministic projections only.
- CLI run command: `python -m protocol_poc.reliability run --base-url URL --fixtures PATH --output PATH --run-label LABEL`.
- CLI comparison command: `python -m protocol_poc.reliability compare --first PATH --second PATH --output PATH`.
- `make reliability-pilot` starts a clean isolated test stack, runs the pilot twice with separate Compose projects and volumes, compares deterministic projections, writes reports under `work/reliability-pilot/`, and exits nonzero unless every acceptance criterion passes.

- [ ] **Step 1: Write failing report tests for exact safety language and mismatch detail**

Create a result containing one pass and one mismatch, then assert:

```python
markdown = render_markdown(result)
payload = json.loads(render_json(result))

assert "unsupported clinical facts exported: 0" in markdown
assert "Expected: SYNOPSIS_DOSE_MISSING" in markdown
assert "Actual: PROCESSING_FAILED" in markdown
assert payload["studies"][1]["checks"][0]["passed"] is False
for forbidden in ("clinical readiness", "regulatory readiness", "submission readiness", "readiness percentage"):
    assert forbidden not in markdown.casefold()
assert "%" not in markdown
```

Add repeatability fixtures with different study/snapshot IDs but identical stable facts and assert no mismatch. Change one passage string and assert one mismatch naming the study and `passages` field.

- [ ] **Step 2: Run report tests and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/reliability/test_report.py tests/unit/reliability/test_cli.py -v
```

Expected: report and CLI modules do not exist.

- [ ] **Step 3: Implement deterministic JSON and human-readable Markdown renderers**

The Markdown report must include:

```text
# Six-Study Synthetic Reliability Pilot

Synthetic POC evaluation only. This report does not establish clinical,
regulatory, submission, operational, production, or readiness status.

Result: PASS|FAIL
Studies passed: 6 of 6
unsupported clinical facts exported: 0
```

For each study, render input filenames/hashes, expected and actual blockers/actions, correction applied, current and historical versions, passage status, export denial evidence, snapshot ID, artifact names/hashes, and every failed check’s expected/actual values. Do not compute an aggregate percentage.

JSON uses sorted keys and two-space indentation. `render_json` must serialize the full run, while repeatability comparison uses `deterministic_projection` only.

- [ ] **Step 4: Implement the single-run CLI and strict exit status**

The CLI must:

1. load and hash-check all six manifests;
2. run the pilot through `PilotClient`;
3. write `<run-label>.json` and `<run-label>.md` atomically;
4. print only the report paths, six-study pass count, and unsupported export invariant; and
5. return exit code `0` only for a passing 6/6 run with zero unsupported exports.

Use `Path.replace()` from temporary files in the same output directory for atomic report publication.

- [ ] **Step 5: Add the clean-stack Make target and ignored run-output directory**

Add `work/reliability-pilot/` to the repository `.gitignore`. Add `reliability-pilot` to `.PHONY` and use this isolated recipe:

```make
RELIABILITY_OUTPUT ?= work/reliability-pilot

reliability-pilot:
	@mkdir -p $(RELIABILITY_OUTPUT)
	@set -eu; \
	cleanup() { \
		docker compose -p protocol-poc-reliability-a down --volumes >/dev/null 2>&1 || true; \
		docker compose -p protocol-poc-reliability-b down --volumes >/dev/null 2>&1 || true; \
	}; \
	trap cleanup EXIT; \
	cleanup; \
	APP_ENV=test ENVIRONMENT=test ALLOW_INSECURE_IDENTITY_HEADERS=true API_PORT=8301 WEB_PORT=3301 \
		docker compose -p protocol-poc-reliability-a up --build -d --wait; \
	(cd backend && .venv/bin/python -m protocol_poc.reliability run \
		--base-url http://127.0.0.1:8301 --fixtures ../fixtures/reliability-pilot \
		--output ../$(RELIABILITY_OUTPUT) --run-label run-a); \
	docker compose -p protocol-poc-reliability-a down --volumes; \
	APP_ENV=test ENVIRONMENT=test ALLOW_INSECURE_IDENTITY_HEADERS=true API_PORT=8302 WEB_PORT=3302 \
		docker compose -p protocol-poc-reliability-b up --build -d --wait; \
	(cd backend && .venv/bin/python -m protocol_poc.reliability run \
		--base-url http://127.0.0.1:8302 --fixtures ../fixtures/reliability-pilot \
		--output ../$(RELIABILITY_OUTPUT) --run-label run-b); \
	docker compose -p protocol-poc-reliability-b down --volumes; \
	(cd backend && .venv/bin/python -m protocol_poc.reliability compare \
		--first ../$(RELIABILITY_OUTPUT)/run-a.json \
		--second ../$(RELIABILITY_OUTPUT)/run-b.json \
		--output ../$(RELIABILITY_OUTPUT))
```

The `(cd backend && ...)` subshells return to the application root before each Docker command. The target must never reset or reuse the user’s normal `protocol-poc` Compose project.

- [ ] **Step 6: Run unit tests and one full two-stack pilot GREEN**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/unit/reliability/test_report.py tests/unit/reliability/test_cli.py -v
.venv/bin/ruff check src/protocol_poc/reliability tests/unit/reliability
.venv/bin/mypy src/protocol_poc/reliability
cd ..
make reliability-pilot
```

Expected: `run-a`, `run-b`, and repeatability JSON/Markdown reports are written; both runs show 6 of 6; repeatability passes; unsupported clinical facts exported is zero.

- [ ] **Step 7: Commit Task 7**

```bash
git add .gitignore clinical-protocol-poc/Makefile clinical-protocol-poc/backend/src/protocol_poc/reliability/report.py clinical-protocol-poc/backend/src/protocol_poc/reliability/cli.py clinical-protocol-poc/backend/src/protocol_poc/reliability/__main__.py clinical-protocol-poc/backend/tests/unit/reliability/test_report.py clinical-protocol-poc/backend/tests/unit/reliability/test_cli.py
git commit -m "test: report repeatable reliability pilot results"
```

---

### Task 8: Release Evidence and Full Verification

**Files:**
- Modify: `clinical-protocol-poc/README.md`
- Modify: `clinical-protocol-poc/docs/release-checklist.md`
- Modify: `clinical-protocol-poc/docs/safety-case.md`
- Create: `clinical-protocol-poc/docs/reliability-pilot.md`
- Modify: `clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py`

**Interfaces:**
- Documents `make reliability-pilot`, fixture scope, report locations, correction behaviors, and exact non-readiness limitations.
- Retains one reviewed Markdown summary only after its referenced run passes; generated JSON, snapshots, IDs, and downloaded artifacts remain ignored run output.
- Extends documented-control evaluation to require the six-study pilot, three pre-correction export denials, two-run agreement, and zero unsupported exported facts.

- [ ] **Step 1: Write a failing documented-control test**

Extend `test_documented_controls.py` to read `docs/reliability-pilot.md` and assert these stable controls are named:

```python
required = {
    "six synthetic self-service studies",
    "three direct-success studies",
    "three mistake-and-recovery studies",
    "SYNOPSIS_DOSE_MISSING",
    "TEMPLATE_TOKEN_MISSING",
    "UNSUPPORTED_DOSE",
    "two clean-stack runs",
    "unsupported clinical facts exported: 0",
}
assert all(item in document for item in required)
assert "readiness percentage" not in document.casefold()
```

- [ ] **Step 2: Run the evaluation test and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/evaluation/test_documented_controls.py -v
```

Expected: `docs/reliability-pilot.md` is absent.

- [ ] **Step 3: Document reproduction, evidence, and limitations**

Write `docs/reliability-pilot.md` with:

- the six study names and their exact expected first outcomes;
- the corrected synopsis, corrected template, and passage-regeneration paths;
- the command `make reliability-pilot`;
- output locations under `work/reliability-pilot/`;
- the 6/6 and two-run agreement criteria;
- `unsupported clinical facts exported: 0`; and
- the explicit statement that the pilot is synthetic POC reliability evidence, not validation or a clinical, regulatory, submission, operational, production, or readiness claim.

Update README development commands and safety-case control mapping. Update the release checklist only with results from the freshly passing run; do not copy old study, snapshot, or artifact IDs into gold manifests.

- [ ] **Step 4: Run the complete verification matrix**

Run:

```bash
cd clinical-protocol-poc
make test
make lint
make typecheck
make evaluation
make e2e
make reliability-pilot
```

Expected:

- backend and frontend tests pass;
- backend and frontend lint/type checks pass;
- adversarial evaluation passes with zero unsupported exported facts;
- the full browser suite passes;
- both clean reliability runs pass 6/6;
- three mistake studies prove export denial before correction;
- repeatability comparison passes; and
- the retained Markdown report contains no percentage or readiness claim.

- [ ] **Step 5: Inspect the final diff and retained report**

Run:

```bash
git diff --check
git status --short
rg -n "TB[D]|TO[D]O|FIXM[E]|PLACEHOLD[E]R" clinical-protocol-poc/backend/src/protocol_poc/reliability clinical-protocol-poc/docs/reliability-pilot.md
rg -ni "readiness percentage|clinical readiness|regulatory readiness|submission readiness" clinical-protocol-poc/docs/reliability-pilot.md clinical-protocol-poc/work/reliability-pilot/*.md
```

Expected: no whitespace errors, no placeholders, no unintended generated artifacts staged, and no prohibited readiness language. The limitation sentence may use the individual words `clinical`, `regulatory`, `submission`, and `readiness`, but not claim any readiness status.

- [ ] **Step 6: Commit Task 8**

```bash
git add clinical-protocol-poc/README.md clinical-protocol-poc/docs/release-checklist.md clinical-protocol-poc/docs/safety-case.md clinical-protocol-poc/docs/reliability-pilot.md clinical-protocol-poc/backend/tests/evaluation/test_documented_controls.py
git commit -m "docs: record six-study reliability evidence"
```

- [ ] **Step 7: Stop for merge review**

Present the eight task commits, complete verification output, retained report path, and any known limitations. Do not merge or push until the user explicitly approves those actions.
