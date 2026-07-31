# Resumable Export Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reopening any completed study automatically shows its latest immutable export snapshot and all three download links, including after archive and restore.

**Architecture:** Add a tenant-scoped repository read for the latest complete export and expose it through a read-only study export endpoint. Extend the frontend export API to load that state during drafting-workspace refresh, and render saved artifacts without offering duplicate creation.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pytest, TypeScript 5.8, React 19, Next.js 15, Node test runner, Testing Library, Playwright.

## Global Constraints

- The latest saved export appears whenever a completed study is reopened, not only after archive and restore.
- Archive and restore do not mutate snapshots, artifacts, or storage objects.
- The export remains exactly `protocol.docx`, `traceability.csv`, and `scorecard.html`.
- Unknown and cross-tenant studies return `404`; they are never represented as empty export state.
- A study with no export returns a successful empty export state.
- A partial artifact set fails closed and does not enable duplicate creation.
- Historical export listing, snapshot selection, deletion, replacement, format changes, remote storage, authentication changes, and multi-user behavior remain out of scope.

---

### Task 1: Latest Export Repository and API

**Files:**
- Modify: `clinical-protocol-poc/backend/src/protocol_poc/export/artifact_service.py`
- Modify: `clinical-protocol-poc/backend/src/protocol_poc/export/routes.py`
- Test: `clinical-protocol-poc/backend/tests/integration/export/test_export_api.py`

**Interfaces:**
- Consumes: `StudyService.get(ctx: TenantContext, study_id: str) -> Study`, `EXPECTED_FILENAMES`, `ExportSnapshot`, and `ExportArtifactRecord`.
- Produces: `LatestExport(snapshot_id: str, descriptors: tuple[ArtifactDescriptor, ...])` and `ExportArtifactRepository.latest_for_study(ctx: TenantContext, study_id: str) -> LatestExport | None`.
- Produces API: `GET /api/studies/{study_id}/exports/latest -> {snapshotId: string | null, blockers: string[], artifacts: ArtifactResponse[]}`.

- [ ] **Step 1: Write failing API tests for latest, empty, isolated, and incomplete states**

Add helpers in `test_export_api.py` that seed a tenant-scoped `Study`, two ordered `ExportSnapshot` rows, and exact artifact rows. Add one test that asserts only the newest snapshot is returned and its artifacts follow `EXPECTED_FILENAMES` order:

```python
response = client.get("/api/studies/study-a/exports/latest", headers=HEADERS)

assert response.status_code == 200
assert response.json() == {
    "snapshotId": "snapshot-new",
    "blockers": [],
    "artifacts": [
        {
            "id": "new-protocol",
            "name": "protocol.docx",
            "mediaType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "sha256": "1" * 64,
            "snapshotId": "snapshot-new",
            "downloadUrl": "/api/export-artifacts/new-protocol",
        },
        {
            "id": "new-traceability",
            "name": "traceability.csv",
            "mediaType": "text/csv",
            "sha256": "2" * 64,
            "snapshotId": "snapshot-new",
            "downloadUrl": "/api/export-artifacts/new-traceability",
        },
        {
            "id": "new-scorecard",
            "name": "scorecard.html",
            "mediaType": "text/html",
            "sha256": "3" * 64,
            "snapshotId": "snapshot-new",
            "downloadUrl": "/api/export-artifacts/new-scorecard",
        },
    ],
}
```

Add separate assertions for the remaining contracts:

```python
assert client.get("/api/studies/study-empty/exports/latest", headers=HEADERS).json() == {
    "snapshotId": None,
    "blockers": [],
    "artifacts": [],
}
assert client.get(
    "/api/studies/study-a/exports/latest",
    headers={"X-Tenant-ID": "tenant-b", "X-Actor-ID": "writer"},
).status_code == 404
assert client.get("/api/studies/missing/exports/latest", headers=HEADERS).status_code == 404
assert client.get("/api/studies/study-partial/exports/latest", headers=HEADERS).status_code == 409
```

For the partial study, persist a newest snapshot with only `protocol.docx` and assert:

```python
assert response.json() == {"detail": {"code": "EXPORT_INTEGRITY_FAILED"}}
```

- [ ] **Step 2: Run the targeted backend tests and verify RED**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/integration/export/test_export_api.py -v
```

Expected: the new tests fail with `405 Method Not Allowed` because the latest-export GET endpoint does not exist.

- [ ] **Step 3: Implement the minimal tenant-scoped latest-export read**

In `artifact_service.py`, add:

```python
@dataclass(frozen=True)
class LatestExport:
    snapshot_id: str
    descriptors: tuple[ArtifactDescriptor, ...]


def latest_for_study(
    self,
    ctx: TenantContext,
    study_id: str,
) -> LatestExport | None:
    context = require_tenant_context(ctx)
    snapshot = self._session.scalar(
        select(ExportSnapshot)
        .where(
            ExportSnapshot.tenant_id == context.tenant_id,
            ExportSnapshot.study_id == study_id,
        )
        .order_by(ExportSnapshot.created_at.desc(), ExportSnapshot.id.desc())
        .limit(1)
    )
    if snapshot is None:
        return None
    records = list(self._session.scalars(
        select(ExportArtifactRecord).where(
            ExportArtifactRecord.tenant_id == context.tenant_id,
            ExportArtifactRecord.snapshot_id == snapshot.id,
        )
    ))
    by_name = {record.filename: record for record in records}
    if set(by_name) != set(EXPECTED_FILENAMES) or len(records) != len(EXPECTED_FILENAMES):
        raise OSError("latest export artifact set is incomplete")
    return LatestExport(
        snapshot.id,
        tuple(self._descriptor(by_name[name]) for name in EXPECTED_FILENAMES),
    )
```

Keep `_descriptor` as the single conversion point used by persistence and retrieval.

In `routes.py`:

- Import `StudyNotFound` and `StudyService`.
- Change `ExportResponse.snapshot_id` to `str | None` so the same response contract can represent a valid no-export study.
- Add a `_response(latest: LatestExport | None) -> ExportResponse` helper to avoid duplicating descriptor mapping.
- Add the endpoint:

```python
@router.get(
    "/studies/{study_id}/exports/latest",
    response_model=ExportResponse,
    response_model_by_alias=True,
)
def latest_export(
    study_id: str,
    request: Request,
    session: Session = Depends(database_session),
) -> ExportResponse:
    ctx = _identity(request)
    try:
        StudyService(session).get(ctx, study_id)
        latest = ExportArtifactRepository(
            session,
            LocalFileStorage(Path(get_settings().local_storage_path)),
        ).latest_for_study(ctx, study_id)
    except StudyNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "STUDY_NOT_FOUND"},
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "EXPORT_INTEGRITY_FAILED"},
        ) from error
    return _response(latest)
```

The empty response is `ExportResponse(snapshot_id=None, blockers=[], artifacts=[])`. Do not check the study lifecycle; archived exports remain readable.

- [ ] **Step 4: Run targeted backend tests and verify GREEN**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/python -m pytest tests/integration/export/test_export_api.py -v
```

Expected: all tests in `test_export_api.py` pass.

- [ ] **Step 5: Run backend static checks for the touched boundary**

Run:

```bash
cd clinical-protocol-poc/backend
.venv/bin/ruff check src/protocol_poc/export tests/integration/export/test_export_api.py
.venv/bin/mypy src/protocol_poc/export
```

Expected: both commands exit successfully with no findings.

- [ ] **Step 6: Commit Task 1**

```bash
git add clinical-protocol-poc/backend/src/protocol_poc/export/artifact_service.py clinical-protocol-poc/backend/src/protocol_poc/export/routes.py clinical-protocol-poc/backend/tests/integration/export/test_export_api.py
git commit -m "feat: expose latest study export"
```

---

### Task 2: Frontend Resume Rendering

**Files:**
- Modify: `clinical-protocol-poc/frontend/src/lib/types.ts`
- Modify: `clinical-protocol-poc/frontend/src/lib/api.ts`
- Modify: `clinical-protocol-poc/frontend/src/app/studies/[studyId]/draft/page.tsx`
- Modify: `clinical-protocol-poc/frontend/src/features/export/ExportPanel.tsx`
- Test: `clinical-protocol-poc/frontend/tests/export/ExportPanel.test.tsx`

**Interfaces:**
- Consumes API: `GET /api/local/studies/{studyId}/exports/latest` with the `ExportState` payload from Task 1.
- Produces: `ExportApi.loadLatest(studyId: string) -> Promise<ExportState>`.
- Produces UI rule: a non-null `snapshotId` displays saved artifacts and suppresses `Create export`; a null `snapshotId` retains server-gated creation.

- [ ] **Step 1: Write failing frontend tests for loading and rendering a saved export**

In `ExportPanel.test.tsx`, add an API test:

```typescript
it("loads the latest export through the local proxy and rewrites downloads", async () => {
  const originalFetch = globalThis.fetch;
  let request: { url: string; init?: RequestInit } | null = null;
  globalThis.fetch = async (url, init) => {
    request = { url: String(url), init };
    return Response.json({
      blockers: [],
      snapshotId: "snapshot-saved",
      artifacts: [{
        id: "docx",
        name: "protocol.docx",
        mediaType: "application/docx",
        sha256: "a".repeat(64),
        snapshotId: "snapshot-saved",
        downloadUrl: "/api/export-artifacts/docx",
      }],
    });
  };
  try {
    const result = await protocolExportApi.loadLatest("study-1");
    assert.deepEqual(request, {
      url: "/api/local/studies/study-1/exports/latest",
      init: undefined,
    });
    assert.equal(result.artifacts[0]?.downloadUrl, "/api/local/export-artifacts/docx");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
```

Add a rendering test:

```typescript
it("shows a saved export without offering duplicate creation", () => {
  render(<ExportPanel
    studyId="study-1"
    exportCommand={exportCommand}
    state={{
      blockers: [],
      snapshotId: "snapshot-saved",
      artifacts: [{
        id: "docx",
        name: "protocol.docx",
        mediaType: "application/docx",
        sha256: "a".repeat(64),
        snapshotId: "snapshot-saved",
        downloadUrl: "/api/local/export-artifacts/docx",
      }],
    }}
  />);

  assert.ok(screen.getByRole("link", { name: "Download protocol.docx" }));
  assert.equal(screen.queryByRole("button", { name: "Create export" }), null);
});
```

Replace the obsolete test that attempts to create over an already populated snapshot with this suppression assertion. Keep existing blocker, successful creation, rerender-authority, and create-proxy tests. Add `loadLatest: async () => blockedState` (or the state appropriate to that test) to every inline `ExportApi` test double so each object implements the expanded interface.

- [ ] **Step 2: Run the targeted frontend test and verify RED**

Run:

```bash
cd clinical-protocol-poc/frontend
pnpm test -- tests/export/ExportPanel.test.tsx
```

Expected: the API test fails because `loadLatest` is missing, and the rendering test fails because `Create export` remains visible.

- [ ] **Step 3: Add the latest-export API method**

In `types.ts`, extend the interface:

```typescript
export type ExportApi = {
  loadLatest(studyId: string): Promise<ExportState>;
  createExport(studyId: string, command: ExportCommand): Promise<ExportState>;
};
```

In `api.ts`, extract one mapper shared by GET and POST:

```typescript
function localExportState(payload: ExportState): ExportState {
  return {
    ...payload,
    artifacts: payload.artifacts.map((artifact) => ({
      ...artifact,
      downloadUrl: `/api/local/export-artifacts/${encodeURIComponent(artifact.id)}`,
    })),
  };
}
```

Add `loadLatest`:

```typescript
async loadLatest(studyId) {
  const response = await fetch(
    `/api/local/studies/${encodeURIComponent(studyId)}/exports/latest`,
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Unable to load saved export"));
  }
  return localExportState((await response.json()) as ExportState);
},
```

Update `createExport` to return `localExportState(payload)` on success without changing its blocker behavior.

- [ ] **Step 4: Load saved export state with the drafting workspace**

Extend `DraftState` with `exportState: ExportState`. In `refresh`, load all four authoritative resources:

```typescript
const [passages, quality, workspace, exportState] = await Promise.all([
  protocolDraftingApi.getPassages(studyId),
  protocolDraftingApi.getQuality(studyId),
  protocolWorkspaceApi.getWorkspace(studyId),
  protocolExportApi.loadLatest(studyId),
]);
```

Set `exportState` in `setState`, then render:

```tsx
<ExportPanel
  studyId={studyId}
  exportCommand={state.exportCommand}
  state={{
    ...state.exportState,
    blockers: state.exportState.snapshotId
      ? state.exportState.blockers
      : state.exportBlockers,
  }}
/>
```

This preserves workspace-derived blockers before the first export while keeping a saved export authoritative after reopening.

- [ ] **Step 5: Suppress duplicate creation for saved snapshots**

In `ExportPanel.tsx`, derive `hasSavedExport` and render the button only for an empty snapshot:

```tsx
const hasSavedExport = exportState.snapshotId !== null;
const blocked = !hasSavedExport
  && (exportState.blockers.length > 0 || exportCommand === null);

{!hasSavedExport ? (
  <button
    type="button"
    disabled={blocked}
    onClick={() => void createExport()}
  >
    Create export
  </button>
) : null}
```

Keep the existing artifact section unchanged so all names, hashes, snapshot IDs, and downloads remain visible.

- [ ] **Step 6: Run targeted frontend tests and verify GREEN**

Run:

```bash
cd clinical-protocol-poc/frontend
pnpm test -- tests/export/ExportPanel.test.tsx
```

Expected: all `ExportPanel` tests pass.

- [ ] **Step 7: Run frontend typecheck and lint**

Run:

```bash
cd clinical-protocol-poc/frontend
pnpm typecheck
pnpm lint
```

Expected: both commands exit successfully with no findings.

- [ ] **Step 8: Commit Task 2**

```bash
git add clinical-protocol-poc/frontend/src/lib/types.ts clinical-protocol-poc/frontend/src/lib/api.ts 'clinical-protocol-poc/frontend/src/app/studies/[studyId]/draft/page.tsx' clinical-protocol-poc/frontend/src/features/export/ExportPanel.tsx clinical-protocol-poc/frontend/tests/export/ExportPanel.test.tsx
git commit -m "fix: resume saved export artifacts"
```

---

### Task 3: Archive/Restore Regression Journey and Full Verification

**Files:**
- Modify: `clinical-protocol-poc/frontend/tests/e2e/archive-restore.spec.ts`
- Reuse: `clinical-protocol-poc/frontend/tests/e2e/helpers.ts`

**Interfaces:**
- Consumes: the latest-export GET behavior from Task 1 and automatic drafting-page load from Task 2.
- Produces: an end-to-end regression proving the same saved snapshot and all three downloads survive archive and restore.

- [ ] **Step 1: Expand the archive/restore test to reproduce the reported bug**

Import `processSynopsis`, `reviewAllFacts`, and `generateAndAcceptPassages`. After input upload, complete the workflow and create the export:

```typescript
await processSynopsis(page);
await page.goto(`${studyHref}/review`);
await reviewAllFacts(page);
await generateAndAcceptPassages(page, studyHref);
await page.getByRole("button", { name: "Create export" }).click();
const snapshot = await page.getByTestId("snapshot-id").textContent();
expect(snapshot).toBeTruthy();
await expect(page.getByRole("link", { name: /^Download / })).toHaveCount(3);
```

Keep the existing archive/read-only/restore assertions. Replace the final `Process synopsis` assertion with:

```typescript
await page.goto(`${studyHref}/draft`);
await expect(page.getByTestId("snapshot-id")).toHaveText(snapshot!);
await expect(page.getByRole("link", { name: /^Download / })).toHaveCount(3);
await expect(page.getByRole("link", { name: "Download protocol.docx" })).toBeVisible();
await expect(page.getByRole("link", { name: "Download traceability.csv" })).toBeVisible();
await expect(page.getByRole("link", { name: "Download scorecard.html" })).toBeVisible();
await expect(page.getByRole("button", { name: "Create export" })).toHaveCount(0);
```

Set the test timeout to `180_000` because this now runs the complete server-backed workflow.

- [ ] **Step 2: Run the focused release-stack E2E test**

Run:

```bash
cd clinical-protocol-poc
E2E_TESTS=tests/e2e/archive-restore.spec.ts make e2e
```

Expected: the study restores to Active, the original snapshot ID reappears, all three links are visible, and `Create export` is absent.

- [ ] **Step 3: Run the full backend and frontend suites**

Run:

```bash
cd clinical-protocol-poc
make test
make lint
make typecheck
```

Expected: all backend and frontend tests pass; lint and type checks return no findings.

- [ ] **Step 4: Rebuild the local app and repeat the user-visible acceptance check**

Run:

```bash
cd clinical-protocol-poc
make app
```

Open the already-restored acceptance study at `/studies/01KYW7YZJ6510BFAC2PRQ0HR24/draft`. Verify snapshot `01KYWA3MVD0C863M2CVDFNWFZK`, the three saved download links, and no `Create export` button.

- [ ] **Step 5: Commit Task 3**

```bash
git add clinical-protocol-poc/frontend/tests/e2e/archive-restore.spec.ts
git commit -m "test: preserve exports across archive restore"
```

- [ ] **Step 6: Inspect the final diff and repository state**

Run:

```bash
git status --short --branch
git diff HEAD~3 --check
git log -4 --oneline
```

Expected: no uncommitted files, no whitespace errors, and one design commit plus three focused implementation commits above the prior `main` head.
