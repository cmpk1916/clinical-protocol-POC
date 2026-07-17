# Self-Service Study Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable local workflow that creates synthetic studies, accepts supported synopsis and template DOCX files, extracts evidence-backed facts deterministically, guides review and drafting, exports the governed three-file package, and supports safe replacement plus archive or restore.

**Architecture:** FastAPI and PostgreSQL remain authoritative for lifecycle, inputs, processing, review, quality, replacement, and export. Next.js exposes a same-origin local proxy that attaches the configured identity server-side and renders server-derived workspace summaries; document bytes remain in local storage and extraction/drafting make no network calls.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Alembic 1.15, PostgreSQL 16, Pydantic 2, Next.js 15, React 19, TypeScript 5.8, pytest 8, Node test runner/Testing Library, Playwright 1.61, Docker Compose.

## Global Constraints

- Support only synthetic `.docx` inputs that pass the existing secure package parser.
- Make no live AI calls and transmit no document or document-derived content externally.
- Use one local writer without account or sign-in UI while retaining server-side tenant scoping.
- Derive workflow stage, blockers, and next action from saved records; never persist a second workflow-stage truth.
- Keep file versions, processing history, snapshots, and artifacts immutable.
- Extraction is all-or-nothing and every fact points to exact source evidence.
- Support exactly four draft sections: `synopsis`, `objectives_endpoints`, `study_design`, and `eligibility`.
- Export exactly `protocol.docx`, `traceability.csv`, and `scorecard.html`, failing closed on every blocker.
- Allow archive and restore only; do not add permanent deletion.
- Preserve synthetic-only, non-validated, non-clinical, non-regulatory, and non-submission-ready language.

## File structure

### Backend files to create

- `backend/src/protocol_poc/studies/service.py` — study lifecycle commands and active-study guard.
- `backend/src/protocol_poc/studies/routes.py` — create/list/detail/archive/restore and workspace APIs.
- `backend/src/protocol_poc/studies/workspace.py` — derived workflow summary read model.
- `backend/src/protocol_poc/studies/document_contract.py` — supported synopsis and template validation.
- `backend/src/protocol_poc/studies/local_extractor.py` — versioned deterministic fact rules.
- `backend/src/protocol_poc/studies/document_workflow.py` — activation, processing, retry, preview, and replacement transaction boundary.
- `backend/src/protocol_poc/drafting/local_composer.py` — deterministic four-section text composition.
- `backend/migrations/versions/0009_self_service_workflow.py` — lifecycle, active-input, processing, and fact-source schema.
- `backend/tests/unit/studies/test_study_service.py`, `test_document_contract.py`, `test_local_extractor.py`, `test_workspace.py` — focused domain tests.
- `backend/tests/integration/studies/test_study_api.py`, `test_document_workflow.py`, `test_replacement.py`, `test_workspace_api.py` — persisted workflow tests.

### Frontend files to create

- `frontend/src/lib/backend.ts` — server-only authenticated backend requests.
- `frontend/src/app/api/local/[...path]/route.ts` — allowlisted same-origin JSON, multipart, and artifact proxy.
- `frontend/src/features/studies/StudyDashboard.tsx` — active/archived lists and create form.
- `frontend/src/features/studies/WorkspaceGuide.tsx` — derived progress, blockers, and next action.
- `frontend/src/features/studies/InputCard.tsx` — upload, findings, retry, history, and replacement confirmation.
- `frontend/src/app/studies/[studyId]/page.tsx` — guided workspace entry page.
- `frontend/src/app/globals.css` — shared accessible guided-workspace styling.
- `frontend/tests/studies/StudyDashboard.test.tsx`, `WorkspaceGuide.test.tsx`, `InputCard.test.tsx` — UI behavior tests.
- `frontend/tests/e2e/self-service-workflow.spec.ts`, `replacement-workflow.spec.ts`, `archive-restore.spec.ts` — user journeys.

### Existing files to modify

- Backend: `app.py`, `studies/models.py`, `studies/repository.py`, `files/models.py`, `ingest/service.py`, `review/routes.py`, `review/fact_service.py`, `review/impact_service.py`, `drafting/routes.py`, `drafting/service.py`, `drafting/review_service.py`, `export/gate.py`, `export/orchestration.py`, and `export/routes.py`.
- Frontend: `app/layout.tsx`, `app/page.tsx`, current study review/draft/model pages, `lib/api.ts`, `lib/types.ts`, review/drafting/export components, and the two existing export proxy routes (remove after the generic proxy is verified).
- Operations/docs: `compose.yaml`, `Makefile`, `README.md`, `docs/demo-script.md`, and supported fixture files.

---

### Task 1: Study lifecycle and persistence foundation

**Files:**
- Create: `backend/migrations/versions/0009_self_service_workflow.py`
- Create: `backend/src/protocol_poc/studies/service.py`
- Create: `backend/src/protocol_poc/studies/routes.py`
- Modify: `backend/src/protocol_poc/studies/models.py`
- Modify: `backend/src/protocol_poc/studies/repository.py`
- Modify: `backend/src/protocol_poc/app.py`
- Test: `backend/tests/unit/studies/test_study_service.py`
- Test: `backend/tests/integration/studies/test_study_api.py`

**Interfaces:**
- Produces: `StudyService.create(ctx, name) -> Study`, `list(ctx, lifecycle) -> list[Study]`, `archive(ctx, study_id, expected_version) -> Study`, `restore(...) -> Study`, and `require_active(ctx, study_id) -> Study`.
- Produces API: `POST /api/studies`, `GET /api/studies?lifecycle=active|archived`, `GET /api/studies/{id}`, `POST /api/studies/{id}/archive`, and `POST /api/studies/{id}/restore`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_archive_and_restore_use_optimistic_versions(session, ctx):
    service = StudyService(session)
    study = service.create(ctx, "Synthetic Alpha")
    archived = service.archive(ctx, study.id, expected_version=1)
    assert (archived.lifecycle, archived.version, archived.archived_at is not None) == ("archived", 2, True)
    with pytest.raises(StudyVersionConflict):
        service.restore(ctx, study.id, expected_version=1)
    restored = service.restore(ctx, study.id, expected_version=2)
    assert (restored.lifecycle, restored.version, restored.archived_at) == ("active", 3, None)
```

Add API tests asserting blank names return 422, tenant B receives 404 for tenant A's study, archived filtering is correct, and archived mutations return `STUDY_ARCHIVED`.

- [ ] **Step 2: Run the tests and confirm the intended failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/studies/test_study_service.py tests/integration/studies/test_study_api.py -v`

Expected: collection fails because `StudyService` and study routes do not exist.

- [ ] **Step 3: Add lifecycle fields, migration, service, and routes**

Add `lifecycle`, `updated_at`, and `archived_at` to `Study`; define `StudyVersionConflict`, `StudyArchived`, and `StudyNotFound`; increment `version` and `updated_at` on archive/restore; append `study.created`, `study.archived`, and `study.restored` audit events. Use Pydantic commands with `extra="forbid"`:

```python
class CreateStudyCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)

class VersionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
```

Register `studies.routes.router` in `create_app()`. The migration must add `lifecycle VARCHAR(16) NOT NULL DEFAULT 'active'`, `updated_at`, `archived_at`, and a lifecycle check constraint.

- [ ] **Step 4: Run lifecycle and migration verification**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/studies/test_study_service.py tests/integration/studies/test_study_api.py tests/integration/ingest/test_migration.py -v`

Expected: all selected tests pass.

- [ ] **Step 5: Commit the lifecycle slice**

```bash
git add backend/migrations/versions/0009_self_service_workflow.py backend/src/protocol_poc/studies backend/src/protocol_poc/app.py backend/tests/unit/studies/test_study_service.py backend/tests/integration/studies/test_study_api.py
git commit -m "feat: add local study lifecycle"
```

### Task 2: Same-origin local identity and study dashboard

**Files:**
- Create: `frontend/src/lib/backend.ts`
- Create: `frontend/src/app/api/local/[...path]/route.ts`
- Create: `frontend/src/features/studies/StudyDashboard.tsx`
- Create: `frontend/tests/studies/StudyDashboard.test.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/globals.css`
- Modify: `frontend/src/lib/types.ts`
- Modify: `compose.yaml`

**Interfaces:**
- Consumes Task 1 study APIs.
- Produces `backendFetch(path, init) -> Promise<Response>` and `StudySummary` with `id`, `name`, `version`, `lifecycle`, `updatedAt`, and `archivedAt`.

- [ ] **Step 1: Write failing dashboard and proxy tests**

```tsx
test("creates a study and moves archived studies between views", async () => {
  render(<StudyDashboard initialActive={[]} initialArchived={[archived]} />);
  await userEvent.type(screen.getByLabelText("Study name"), "Synthetic Alpha");
  await userEvent.click(screen.getByRole("button", { name: "Create study" }));
  expect(await screen.findByRole("link", { name: "Open Synthetic Alpha" })).toBeVisible();
  await userEvent.click(screen.getByRole("tab", { name: "Archived" }));
  expect(screen.getByText("Archived Study")).toBeVisible();
});
```

Add route-handler tests proving the proxy rejects non-allowlisted paths and attaches `X-Tenant-ID`/`X-Actor-ID` from server environment variables, never browser input.

- [ ] **Step 2: Run the focused frontend test and confirm failure**

Run: `cd frontend && pnpm test -- tests/studies/StudyDashboard.test.tsx`

Expected: FAIL because the dashboard and local proxy modules do not exist.

- [ ] **Step 3: Implement the server-only proxy and dashboard**

`backendFetch` must set `LOCAL_TENANT_ID` (default `local-poc`) and `LOCAL_ACTOR_ID` (default `local-writer`), preserve multipart boundaries, use `cache: "no-store"`, and never accept identity headers from the incoming browser request. The catch-all proxy allowlist is exactly `studies/`, `facts/`, `passages/`, and `export-artifacts/`; it streams non-JSON responses unchanged.

The server-rendered home page loads active and archived lists. `StudyDashboard` posts JSON to `/api/local/studies`, provides **Archive** and **Restore** commands with each study's expected version, refreshes authoritative lists after commands, links each active study to `/studies/{id}`, and explains the synthetic-only boundary in its empty state. Add the two local identity values to the web service environment in `compose.yaml`.

- [ ] **Step 4: Verify the dashboard slice**

Run: `cd frontend && pnpm test -- tests/studies/StudyDashboard.test.tsx && pnpm typecheck && pnpm lint`

Expected: dashboard tests, TypeScript, and ESLint pass.

- [ ] **Step 5: Commit the dashboard slice**

```bash
git add frontend/src frontend/tests/studies/StudyDashboard.test.tsx compose.yaml
git commit -m "feat: add guided study dashboard"
```

### Task 3: Supported document contract and activated input versions

**Files:**
- Create: `backend/src/protocol_poc/studies/document_contract.py`
- Create: `backend/src/protocol_poc/studies/document_workflow.py`
- Create: `backend/tests/unit/studies/test_document_contract.py`
- Create: `backend/tests/integration/studies/test_document_workflow.py`
- Modify: `backend/src/protocol_poc/files/models.py`
- Modify: `backend/src/protocol_poc/ingest/service.py`
- Modify: `backend/src/protocol_poc/studies/routes.py`
- Modify: `backend/migrations/versions/0009_self_service_workflow.py`

**Interfaces:**
- Produces `StudyInput` with one row per tenant/study/role and `current_file_version_id`, `conformance_status`, and `revision`.
- Produces `DocumentContract.validate_synopsis(evidence) -> tuple[ContractFinding, ...]` and `validate_template(evidence) -> tuple[ContractFinding, ...]`.
- Produces `DocumentWorkflowService.upload(ctx, study_id, UploadInput) -> UploadOutcome`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_template_requires_each_allowlisted_token_once():
    valid = evidence("[[SECTION:synopsis]]", "[[SECTION:objectives_endpoints]]", "[[SECTION:study_design]]", "[[SECTION:eligibility]]", "[[POC_DISCLAIMER]]")
    assert DocumentContract().validate_template(valid) == ()
    duplicate = (*valid, evidence_item("[[SECTION:synopsis]]"))
    assert [f.code for f in DocumentContract().validate_template(duplicate)] == ["TEMPLATE_TOKEN_DUPLICATE"]

def test_synopsis_reports_all_missing_sections():
    findings = DocumentContract().validate_synopsis(evidence("Study identity", "Short title: SYN-1"))
    assert {f.field for f in findings} == {"objectives", "endpoints", "arms_interventions", "population", "eligibility"}
```

Integration tests must prove: first valid upload activates version 1; invalid upload records history/finding but does not activate; checksum-identical upload reuses the immutable version; second valid upload returns `replacement_confirmation_required` and leaves version 1 current.

- [ ] **Step 2: Run contract/workflow tests and confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/studies/test_document_contract.py tests/integration/studies/test_document_workflow.py -v`

Expected: FAIL because the contract and activation models do not exist.

- [ ] **Step 3: Implement exact validation and initial activation**

Define immutable findings:

```python
@dataclass(frozen=True, slots=True)
class ContractFinding:
    code: str
    field: str
    message: str
```

Recognize synopsis section headings case-insensitively after whitespace normalization. Require study identity, objectives, endpoints, arms/interventions, population, and eligibility; require `Short title:`, at least one objective, endpoint, arm/intervention, population line, and eligibility line. Count each template token across persisted evidence and return missing/duplicate findings.

`DocumentWorkflowService.upload` must call `StudyService.require_active`, reuse `IngestService`, validate persisted evidence, create `StudyInput` only for a conforming first version, and return replacement impact without activation for later versions. Never delete a failed or superseded `FileVersion`.

- [ ] **Step 4: Verify secure ingest and contract behavior**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/ingest tests/integration/ingest tests/unit/studies/test_document_contract.py tests/integration/studies/test_document_workflow.py -v`

Expected: all selected tests pass, including existing unsafe-DOCX protections.

- [ ] **Step 5: Commit supported inputs**

```bash
git add backend/migrations/versions/0009_self_service_workflow.py backend/src/protocol_poc/files backend/src/protocol_poc/ingest backend/src/protocol_poc/studies backend/tests/unit/studies backend/tests/integration/studies/test_document_workflow.py
git commit -m "feat: validate and activate supported inputs"
```

### Task 4: Deterministic extraction, processing history, and evidence-rich review

**Files:**
- Create: `backend/src/protocol_poc/studies/local_extractor.py`
- Create: `backend/tests/unit/studies/test_local_extractor.py`
- Modify: `backend/src/protocol_poc/studies/document_workflow.py`
- Modify: `backend/src/protocol_poc/studies/models.py`
- Modify: `backend/src/protocol_poc/review/routes.py`
- Modify: `backend/src/protocol_poc/review/fact_service.py`
- Modify: `backend/migrations/versions/0009_self_service_workflow.py`
- Test: `backend/tests/integration/studies/test_document_workflow.py`
- Test: `backend/tests/integration/review/test_fact_review_api.py`

**Interfaces:**
- Produces `LOCAL_EXTRACTOR_VERSION = "local-rules-v1"`.
- Produces `LocalExtractor.extract(evidence) -> ExtractionProposal`; proposal contains complete `LocalCandidate` values or findings, never both.
- Produces `DocumentWorkflowService.process(ctx, study_id, file_version_id) -> ProcessingOutcome` and `retry(ctx, study_id, attempt_id) -> ProcessingOutcome`.

- [ ] **Step 1: Write failing deterministic extraction tests**

```python
def test_extracts_required_facts_with_exact_evidence_ids():
    proposal = LocalExtractor().extract(supported_synopsis_evidence())
    assert proposal.findings == ()
    assert {item.kind for item in proposal.candidates} >= {"study_identity", "objective", "endpoint", "timepoint", "arm", "intervention", "dose", "population", "eligibility"}
    dose = next(item for item in proposal.candidates if item.kind == "dose")
    assert dose.value_json == {"kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"}
    assert dose.source_evidence_id == "arms-line-1"
```

Add tests for ambiguous headings, missing dose on an intervention line, extraction retry, no partial facts on failure, candidate-only statuses, exact `source_evidence_id`, extractor version, and no call to `AIGateway`.

- [ ] **Step 2: Run extractor and review tests and confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/studies/test_local_extractor.py tests/integration/studies/test_document_workflow.py tests/integration/review/test_fact_review_api.py -v`

Expected: FAIL because local extraction and processing records do not exist.

- [ ] **Step 3: Implement all-or-nothing processing**

Add `ProcessingAttempt` with synopsis version, extractor version, status, findings JSON, timestamps, and unique active-attempt protection; add nullable `processing_attempt_id` to `Fact`. Parse only the approved labels and patterns, including `N mg`, `once daily`, and `Week N`; ambiguity yields stable findings.

Persist a successful proposal and its candidate facts in one transaction. On failure, persist only the failed attempt and findings. Extend fact-review responses with current value, confidence, exact `SourceEvidence.location_json`, evidence text, critical flag, version, and downstream impact. Do not log evidence text.

- [ ] **Step 4: Verify extraction and existing review safety**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/studies/test_local_extractor.py tests/integration/studies/test_document_workflow.py tests/integration/review tests/contract/ai_gateway -v`

Expected: local tests pass and legacy AI-gateway contract tests remain isolated from the self-service route.

- [ ] **Step 5: Commit deterministic processing**

```bash
git add backend/migrations/versions/0009_self_service_workflow.py backend/src/protocol_poc/studies backend/src/protocol_poc/review backend/tests/unit/studies/test_local_extractor.py backend/tests/integration/studies/test_document_workflow.py backend/tests/integration/review
git commit -m "feat: extract local evidence-backed facts"
```

### Task 5: Derived workspace and input/review user interface

**Files:**
- Create: `backend/src/protocol_poc/studies/workspace.py`
- Create: `backend/tests/unit/studies/test_workspace.py`
- Create: `backend/tests/integration/studies/test_workspace_api.py`
- Create: `frontend/src/features/studies/WorkspaceGuide.tsx`
- Create: `frontend/src/features/studies/InputCard.tsx`
- Create: `frontend/src/app/studies/[studyId]/page.tsx`
- Create: `frontend/tests/studies/WorkspaceGuide.test.tsx`
- Create: `frontend/tests/studies/InputCard.test.tsx`
- Modify: `backend/src/protocol_poc/studies/routes.py`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/studies/[studyId]/review/page.tsx`
- Modify: `frontend/src/features/review/ReviewQueue.tsx`

**Interfaces:**
- Produces `WorkspaceSummaryService.get(ctx, study_id) -> WorkspaceSummary`.
- Produces API `GET /api/studies/{id}/workspace`, process/retry commands, and real review queue/actions through the local proxy.

- [ ] **Step 1: Write failing stage-derivation and UI tests**

```python
@pytest.mark.parametrize((state, step, action), [
    ("no_inputs", "inputs", "upload_synopsis"),
    ("needs_processing", "processing", "process_synopsis"),
    ("candidate_facts", "fact_review", "review_facts"),
    ("accepted_facts", "passage_review", "generate_passages"),
    ("accepted_passages", "export", "create_export"),
])
def test_workspace_derives_next_safe_action(state, step, action, scenario):
    summary = scenario(state).summary()
    assert (summary.step, summary.next_action.kind) == (step, action)
```

Frontend tests must assert missing-input prompts, validation finding lists, processing retry, evidence text/location next to each candidate, critical confirmation, and refresh from the returned authoritative summary. Backend tests must assert an archived study's workspace is read-only and rejects fact-review commands with `STUDY_ARCHIVED`.

- [ ] **Step 2: Run workspace tests and confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/studies/test_workspace.py tests/integration/studies/test_workspace_api.py -v`

Run: `cd frontend && pnpm test -- tests/studies/WorkspaceGuide.test.tsx tests/studies/InputCard.test.tsx tests/review/ReviewQueue.test.tsx`

Expected: FAIL because summary and guided workspace components do not exist.

- [ ] **Step 3: Implement derived summary and guided input/review screens**

Derive in this fixed order: archived; missing/invalid input; processing required/failed/in progress; candidate/conflicted facts; missing/blocked/stale/unaccepted passages; quality/export blockers; export available/completed. Return per-step completion, counts, blocker codes/messages, current input descriptors, and one next action.

The workspace page renders `WorkspaceGuide`, two `InputCard` components, and a primary link/button for the server-provided next action. Upload uses multipart `/api/local/studies/{id}/inputs`; process and retry use explicit commands. Call `StudyService.require_active` before every fact-review mutation. Replace all `demoReviewApi` usage on the self-service review route with real responses; retain no catch/fallback success state.

- [ ] **Step 4: Verify the guided workspace slice**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/studies/test_workspace.py tests/integration/studies/test_workspace_api.py tests/integration/review -v`

Run: `cd frontend && pnpm test && pnpm typecheck && pnpm lint`

Expected: backend workspace/review and all frontend component tests pass.

- [ ] **Step 5: Commit workspace and fact review**

```bash
git add backend/src/protocol_poc/studies backend/tests/unit/studies/test_workspace.py backend/tests/integration/studies/test_workspace_api.py frontend/src frontend/tests
git commit -m "feat: guide local input and fact review"
```

### Task 6: Deterministic four-section drafting and passage review

**Files:**
- Create: `backend/src/protocol_poc/drafting/local_composer.py`
- Create: `backend/tests/unit/drafting/test_local_composer.py`
- Modify: `backend/src/protocol_poc/drafting/service.py`
- Modify: `backend/src/protocol_poc/drafting/routes.py`
- Modify: `backend/src/protocol_poc/drafting/review_service.py`
- Modify: `frontend/src/app/studies/[studyId]/draft/page.tsx`
- Modify: `frontend/src/features/drafting/PassageEditor.tsx`
- Modify: `frontend/src/features/drafting/ProtocolNavigator.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `backend/tests/integration/drafting/test_generate_passage.py`
- Test: `frontend/tests/drafting/PassageEditor.test.tsx`

**Interfaces:**
- Produces `LocalComposer.compose(section, approved_facts) -> ComposedPassage` with text, claims, and fact support IDs.
- Produces API `GET /api/studies/{id}/passages`, `POST /api/studies/{id}/passages`, and `POST /api/passages/{id}/review`.

- [ ] **Step 1: Write failing local-composer and passage API tests**

```python
def test_local_composer_uses_only_approved_fact_values():
    output = LocalComposer().compose("study_design", approved_fact_inputs())
    assert output.text == "Arm A receives Synthetic Intervention A, 10 mg once daily, for 24 weeks."
    assert set(output.fact_ids) == {"arm-a", "intervention-a", "dose-a", "duration-a"}
    assert "20 mg" not in output.text
```

Add tests for all four sections, required-fact blockers, exact support links, list/read tenant scoping, accept/edit/reject conflicts, and archived-study denial.

- [ ] **Step 2: Run drafting tests and confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/drafting/test_local_composer.py tests/integration/drafting/test_generate_passage.py -v`

Expected: FAIL because `LocalComposer` and read/review routes do not exist.

- [ ] **Step 3: Implement deterministic drafting and real passage UI**

Use fixed sentence templates per section and only current approved fact versions. Persist claims and fact support links exactly as today; block when required facts are absent. Remove the self-service route's `FixtureProvider` construction. Add Pydantic review commands with expected passage version and actions `accept`, `edit`, `reject`, and `regenerate`.

Load all four passages and quality state from real APIs. The frontend shows evidence/support, deterministic findings, stale state, edit controls, and accept actions. Remove `demoPassages` and `demoScorecard` from the self-service draft page; network failure renders an error state, never a successful passage.

- [ ] **Step 4: Verify drafting and passage review**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/drafting tests/integration/drafting tests/integration/validation -v`

Run: `cd frontend && pnpm test -- tests/drafting/PassageEditor.test.tsx && pnpm typecheck && pnpm lint`

Expected: all selected drafting, validation, and UI tests pass.

- [ ] **Step 5: Commit deterministic drafting**

```bash
git add backend/src/protocol_poc/drafting backend/tests/unit/drafting backend/tests/integration/drafting frontend/src/app/studies frontend/src/features/drafting frontend/src/lib frontend/tests/drafting
git commit -m "feat: add local governed passage workflow"
```

### Task 7: Workspace-authoritative export and exact downloads

**Files:**
- Modify: `backend/src/protocol_poc/studies/workspace.py`
- Modify: `backend/src/protocol_poc/export/gate.py`
- Modify: `backend/src/protocol_poc/export/orchestration.py`
- Modify: `backend/src/protocol_poc/export/routes.py`
- Modify: `frontend/src/features/export/ExportPanel.tsx`
- Modify: `frontend/src/app/studies/[studyId]/draft/page.tsx`
- Modify: `frontend/src/lib/api.ts`
- Remove: `frontend/src/app/api/studies/[studyId]/exports/route.ts`
- Remove: `frontend/src/app/api/artifacts/[artifactId]/route.ts`
- Test: `backend/tests/integration/export/test_export_api.py`
- Test: `frontend/tests/export/ExportPanel.test.tsx`

**Interfaces:**
- Consumes current study version and conformed current template from `WorkspaceSummary`.
- Produces `exportCommand` only when the server has a current conformed template; downloads flow through `/api/local/export-artifacts/{id}`.

- [ ] **Step 1: Write failing export-authority tests**

Extend backend tests to reject archived studies, missing/noncurrent templates, unprocessed synopses, candidate facts, stale passages, and unconformed replacements. Extend frontend tests to assert the POST body exactly matches the server summary, returned artifacts share a snapshot, and failed requests show blockers without artifact rows.

- [ ] **Step 2: Run export tests and confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/export -v`

Run: `cd frontend && pnpm test -- tests/export/ExportPanel.test.tsx`

Expected: new authority tests fail because export still depends on test-seed state in the frontend.

- [ ] **Step 3: Connect current persisted state to export**

Have the workspace summary return `{expectedStudyVersion, templateVersionId, templateHash}` from the current `StudyInput`. Recheck all three values plus active lifecycle inside export orchestration under the existing transaction. Add blockers `STUDY_ARCHIVED`, `INPUT_PROCESSING_INCOMPLETE`, and `TEMPLATE_NOT_CONFORMED` to the hard gate.

Post through the generic local proxy, rewrite returned artifact URLs to `/api/local/export-artifacts/{id}`, and remove the two seed-specific route handlers. Preserve the exact three-artifact, shared-snapshot, hash, tenant-isolation, and fail-closed invariants.

- [ ] **Step 4: Verify full-path export regression coverage**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/export tests/integration/export tests/integration/rendering -v`

Run: `cd frontend && pnpm test -- tests/export/ExportPanel.test.tsx && pnpm typecheck && pnpm lint`

Expected: all selected tests pass and no frontend production path references `/test/studies`.

- [ ] **Step 5: Commit real self-service export**

```bash
git add backend/src/protocol_poc/studies/workspace.py backend/src/protocol_poc/export backend/tests frontend/src frontend/tests/export
git commit -m "feat: export current self-service study"
```

### Task 8: Versioned synopsis/template replacement

**Files:**
- Modify: `backend/src/protocol_poc/studies/document_workflow.py`
- Modify: `backend/src/protocol_poc/studies/routes.py`
- Modify: `backend/src/protocol_poc/review/impact_service.py`
- Create: `backend/tests/integration/studies/test_replacement.py`
- Modify: `frontend/src/features/studies/InputCard.tsx`
- Modify: `frontend/tests/studies/InputCard.test.tsx`

**Interfaces:**
- Produces `preview_replacement(ctx, study_id, role, proposed_version_id) -> ReplacementImpact`.
- Produces `confirm_replacement(ctx, study_id, role, proposed_version_id, expected_current_version_id, expected_study_version) -> ReplacementOutcome`.
- Produces APIs `POST /api/studies/{id}/inputs/{role}/replacement-preview` and `/replacement-confirmation`.

- [ ] **Step 1: Write failing atomic replacement tests**

```python
def test_synopsis_replacement_supersedes_facts_and_stales_supported_passages(workflow, seeded_study):
    outcome = workflow.confirm_replacement(ctx, seeded_study.id, "synopsis", "synopsis-v2", "synopsis-v1", 1)
    assert outcome.current_version_id == "synopsis-v2"
    assert all(f.status == "superseded" for f in seeded_study.original_facts)
    assert seeded_study.supported_passage.status == "stale"
    assert seeded_study.unrelated_passage.status == "accepted"
```

Add tests proving extraction failure leaves v1 current, template replacement preserves facts/passages but blocks export until conformance, stale expected versions return 409, and the activation/invalidation transaction rolls back completely on injected failure.

- [ ] **Step 2: Run replacement tests and confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/studies/test_replacement.py -v`

Expected: FAIL because confirmed replacement methods/routes do not exist.

- [ ] **Step 3: Implement preview, confirmation, and UI impact warning**

For synopsis: validate and extract the proposed version first; within one database transaction activate it, persist its new candidate fact set, mark every prior attempt's facts `superseded`, and call an `ImpactService.invalidate_for_facts` batch method that stales only accepted passages linked to those facts. For template: validate all five unique tokens, activate it, preserve facts/passages, and expose the new conformance/version to the export gate.

The UI must show filenames/versions and exact effects before enabling **Confirm replacement**. On 409 it refreshes the workspace and displays “The study changed in another window. Review the latest version before trying again.”

- [ ] **Step 4: Verify replacements and invalidation regressions**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/studies/test_replacement.py tests/integration/review/test_invalidation.py tests/integration/export -v`

Run: `cd frontend && pnpm test -- tests/studies/InputCard.test.tsx && pnpm typecheck`

Expected: all selected tests pass.

- [ ] **Step 5: Commit replacement safety**

```bash
git add backend/src/protocol_poc/studies backend/src/protocol_poc/review backend/tests/integration/studies/test_replacement.py frontend/src/features/studies/InputCard.tsx frontend/tests/studies/InputCard.test.tsx
git commit -m "feat: add safe versioned input replacement"
```

### Task 9: Complete browser journeys, fixtures, and release verification

**Files:**
- Create: `frontend/tests/e2e/self-service-workflow.spec.ts`
- Create: `frontend/tests/e2e/replacement-workflow.spec.ts`
- Create: `frontend/tests/e2e/archive-restore.spec.ts`
- Modify: `frontend/tests/e2e/helpers.ts`
- Create: `backend/tests/support/build_supported_fixtures.py`
- Create: `fixtures/self-service/synopsis.docx`
- Create: `fixtures/self-service/template.docx`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `docs/demo-script.md`

**Interfaces:**
- Produces `make app` for a clean local start without seeded test data.
- Preserves `make demo` for the existing deterministic seeded demonstration.

- [ ] **Step 1: Add the six required browser journeys**

Implement Playwright tests for: empty-to-export; reopen/resume; synopsis replacement and re-review; template replacement and revalidation; archive/restore; and invalid document with no partial/current-state displacement. Use `page.setInputFiles()` with the committed supported fixtures and assert UI-visible state after every command.

For the happy path, download all three returned URLs and assert filenames, SHA-256 values, common snapshot ID, DOCX ZIP signature, CSV traceability headers/evidence location, HTML limitation copy, and absence of unresolved `[[` tokens.

- [ ] **Step 2: Run the new E2E suite and confirm failures before final wiring**

Run: `cd frontend && pnpm exec playwright test tests/e2e/self-service-workflow.spec.ts tests/e2e/replacement-workflow.spec.ts tests/e2e/archive-restore.spec.ts`

Expected before final fixture/operational wiring: at least the clean-start or fixture upload journey fails for the missing `make app`/fixture integration.

- [ ] **Step 3: Add supported fixtures and local run instructions**

The fixture builder must generate deterministic DOCX packages containing the approved synopsis headings/labels and exactly the four section tokens plus disclaimer token. Add:

```make
.PHONY: app
app:
	APP_ENV=test docker compose up --build -d --wait
	@echo "Clinical Protocol POC ready: http://127.0.0.1:$${WEB_PORT:-3000}"
```

Document `make app`, opening the home screen, creating a synthetic study, uploading both files, processing/reviewing/drafting/exporting, stopping with `make down`, the local-only data boundary, and archive/restore. Keep the existing seeded demo instructions separate.

- [ ] **Step 4: Run full verification**

Run: `make lint`

Expected: Ruff and ESLint pass.

Run: `make typecheck`

Expected: mypy and TypeScript pass.

Run: `make test`

Expected: all backend and frontend tests pass.

Run: `make evaluation`

Expected: adversarial evaluation passes and reports `unsupported clinical facts exported: 0`.

Run: `make e2e`

Expected: existing seeded journeys and all six self-service journeys pass.

Render the downloaded `protocol.docx` to page images with the repository's established document-rendering workflow and inspect every page for preserved headings/styles, visible limitation language, no clipping, and no unresolved tokens. Open `traceability.csv` and `scorecard.html` and verify their shared snapshot metadata, required columns/dimensions, hashes, and lack of readiness claims.

- [ ] **Step 5: Commit verified self-service release documentation**

```bash
git add fixtures/self-service backend/tests/support frontend/tests/e2e Makefile README.md docs/demo-script.md
git commit -m "test: verify self-service study workflow"
```

### Task 10: Final branch review and integration handoff

**Files:**
- Modify only files required by review findings.

**Interfaces:**
- Consumes all prior tasks.
- Produces a verified feature branch ready for the finishing-development-branch workflow.

- [ ] **Step 1: Review scope and prohibited dependencies**

Run: `git diff --stat main...HEAD`

Run: `rg -n "demoReviewApi|demoModelApi|demoPassages|/test/studies|AIGateway|FixtureProvider" frontend/src backend/src/protocol_poc/studies backend/src/protocol_poc/drafting/routes.py`

Expected: no self-service frontend route uses demo/test data; deterministic study extraction and production drafting routes do not instantiate `AIGateway` or `FixtureProvider`.

- [ ] **Step 2: Request code review**

Use `superpowers:requesting-code-review` against the complete spec and this plan. Resolve only verified findings, using `superpowers:receiving-code-review` before applying feedback.

- [ ] **Step 3: Rerun full verification after review changes**

Run: `make lint && make typecheck && make test && make evaluation && make e2e`

Expected: every command exits 0 with no failed tests.

- [ ] **Step 4: Inspect final repository state**

Run: `git status --short --branch && git log --oneline main..HEAD`

Expected: clean feature branch with the documentation commit and the task commits above.

- [ ] **Step 5: Choose merge/PR/cleanup path**

Use `superpowers:finishing-a-development-branch` and present its integration options to the user. Do not merge, push, or delete the branch without the user's selected option.
