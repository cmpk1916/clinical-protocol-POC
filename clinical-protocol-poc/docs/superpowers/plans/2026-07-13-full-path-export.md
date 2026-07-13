# Full-Path Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the simulated clinical-protocol export with a server-authoritative path that creates, stores, returns, downloads, and verifies one template-based DOCX, one traceability CSV, and one scorecard HTML artifact from a single immutable snapshot.

**Architecture:** Keep `ExportService` authoritative for the transactional safety gate and snapshot. Add tenant-scoped immutable artifact records and object-storage reads, focused deterministic renderers, and an orchestration service that persists an all-or-nothing three-file set. Expose descriptors and downloads through authenticated FastAPI routes, proxy them through Next.js, and make Playwright validate the real bytes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, local/S3-compatible object storage, deterministic OOXML, CSV, semantic HTML, Next.js 15, React 19, TypeScript, pytest, Vitest/Node test runner, Playwright, Docker Compose.

## Global Constraints

- Synthetic data only; this remains a non-validated POC with no clinical, regulatory, submission, operational, or readiness claim.
- Successful export consists of exactly `protocol.docx`, `traceability.csv`, and `scorecard.html` from one snapshot and renderer version.
- Every descriptor SHA-256 must match the exact downloaded bytes.
- Artifact lookup is tenant-scoped and returns not found for unknown or cross-tenant identifiers.
- Missing templates, hash mismatches, ambiguous template targets, render failures, and storage failures fail closed and never advertise a partial artifact set.
- Scorecard output contains separate dimensions and no composite score or readiness percentage.
- Test-only seed routes may prepare synthetic state but may not synthesize successful artifact descriptors.
- New behavior follows test-driven development: write the test, observe the expected failure, implement the minimum, rerun the focused test, then run the relevant suite.

---

## File Structure

- `backend/src/protocol_poc/files/service.py` — object storage protocol and local/S3 byte reads.
- `backend/src/protocol_poc/export/models.py` — immutable snapshot-linked artifact metadata.
- `backend/migrations/versions/0008_export_artifacts.py` — artifact table migration.
- `backend/src/protocol_poc/rendering/scorecard.py` — deterministic standalone scorecard HTML.
- `backend/src/protocol_poc/rendering/artifact_service.py` — exact three-format byte generation and hashing.
- `backend/src/protocol_poc/export/artifact_service.py` — tenant-scoped artifact persistence, retrieval, cleanup, and descriptors.
- `backend/src/protocol_poc/export/orchestration.py` — gate, snapshot, frozen-data assembly, template retrieval, rendering, and persistence.
- `backend/src/protocol_poc/export/routes.py` — export and download HTTP endpoints.
- `backend/src/protocol_poc/testing/seed_service.py` — deterministic database and template-storage state for browser tests.
- `backend/src/protocol_poc/testing/routes.py` — test-only reset/seed endpoints calling the seed service.
- `frontend/src/app/api/studies/[studyId]/exports/route.ts` — server-side export proxy with local identity context.
- `frontend/src/app/api/artifacts/[artifactId]/route.ts` — authenticated download proxy.
- `frontend/src/lib/api.ts` and `frontend/src/lib/types.ts` — real export client and descriptor types.
- `frontend/src/features/export/ExportPanel.tsx` — live export state, errors, hashes, and download links.
- `frontend/tests/e2e/happy-path.spec.ts` — real export/download verification.

---

### Task 1: Add immutable artifact persistence and byte reads

**Files:**
- Modify: `backend/src/protocol_poc/files/service.py`
- Modify: `backend/src/protocol_poc/export/models.py`
- Create: `backend/migrations/versions/0008_export_artifacts.py`
- Create: `backend/tests/unit/export/test_artifact_models.py`
- Modify: `backend/tests/unit/files/test_storage.py`
- Modify: `backend/tests/integration/ingest/test_migration.py`

**Interfaces:**
- Produces: `FileStorage.get(key: str) -> bytes | None`.
- Produces: `ExportArtifactRecord` with `id`, `tenant_id`, `snapshot_id`, `filename`, `media_type`, `renderer_version`, `size_bytes`, `sha256_hex`, `storage_key`, and `created_at`.

- [ ] **Step 1: Write failing storage-read tests**

Add tests proving a local object round-trips exact bytes, missing keys return `None`, traversal remains rejected, and an S3 adapter delegates to `get_object`:

```python
def test_local_storage_reads_exact_bytes_and_missing_is_none(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    storage.put("tenant/artifact.bin", b"exact bytes")
    assert storage.get("tenant/artifact.bin") == b"exact bytes"
    assert storage.get("tenant/missing.bin") is None
    with pytest.raises(ValueError):
        storage.get("../escape")
```

- [ ] **Step 2: Run the storage test and observe the missing-method failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/files/test_storage.py -v`  
Expected: FAIL because `LocalFileStorage` and `S3FileStorage` do not implement `get`.

- [ ] **Step 3: Add the minimum storage read interface**

Extend the protocols and adapters:

```python
class FileStorage(Protocol):
    def put(self, key: str, data: bytes) -> bool: ...
    def get(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...
    def object_checksum(self, key: str) -> str | None: ...

def get(self, key: str) -> bytes | None:
    target = self._path(key)
    return target.read_bytes() if target.exists() else None
```

For S3, add `get_object` to `S3Client`, classify not-found consistently, and return `Body.read()` bytes.

- [ ] **Step 4: Write failing immutable artifact-model tests**

```python
def test_export_artifact_record_is_snapshot_linked_and_immutable(session: Session) -> None:
    snapshot = ExportSnapshot(tenant_id="tenant", study_id="study", study_version=1)
    session.add(snapshot)
    session.flush()
    artifact = ExportArtifactRecord(
        tenant_id="tenant", snapshot_id=snapshot.id, filename="protocol.docx",
        media_type=DOCX_MEDIA_TYPE, renderer_version="renderer-v1", size_bytes=4,
        sha256_hex=sha256(b"docx").hexdigest(), storage_key="tenant/export/docx",
    )
    session.add(artifact)
    session.commit()
    artifact.filename = "changed.docx"
    with pytest.raises(ImmutableSnapshotError):
        session.commit()
```

- [ ] **Step 5: Run the model and migration tests and observe failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/export/test_artifact_models.py tests/integration/ingest/test_migration.py -v`  
Expected: FAIL because `ExportArtifactRecord` and migration `0008_export_artifacts` do not exist.

- [ ] **Step 6: Add the model and migration**

Define an `export_artifacts` table with a foreign key to `export_snapshots`, unique `(tenant_id, snapshot_id, filename)`, unique `storage_key`, non-negative size, a lowercase 64-character digest check, and the three allowed filenames. Add `ExportArtifactRecord` to `SNAPSHOT_TYPES`. Create migration `0008_export_artifacts` with `down_revision = "0007_exports"`.

- [ ] **Step 7: Run focused tests and commit**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/files/test_storage.py tests/unit/export/test_artifact_models.py tests/integration/ingest/test_migration.py -v`  
Expected: PASS.

```bash
git add backend/src/protocol_poc/files/service.py backend/src/protocol_poc/export/models.py backend/migrations/versions/0008_export_artifacts.py backend/tests/unit/files/test_storage.py backend/tests/unit/export/test_artifact_models.py backend/tests/integration/ingest/test_migration.py
git commit -m "feat: persist immutable export artifacts"
```

---

### Task 2: Render the exact DOCX, CSV, and HTML formats

**Files:**
- Modify: `backend/src/protocol_poc/rendering/artifact_service.py`
- Modify: `backend/src/protocol_poc/rendering/docx_renderer.py`
- Modify: `backend/src/protocol_poc/rendering/traceability.py`
- Create: `backend/src/protocol_poc/rendering/scorecard.py`
- Modify: `backend/tests/integration/rendering/test_artifacts.py`
- Create: `backend/tests/unit/rendering/test_scorecard_html.py`

**Interfaces:**
- Consumes: `RenderSnapshot`, uploaded template bytes, and `QualityScorecard`.
- Produces: `Artifact(kind, filename, media_type, snapshot_id, renderer_version, content, sha256_hex)` for exactly three artifacts.
- Produces: `scorecard_html(snapshot_id: str, renderer_version: str, scorecard: QualityScorecard) -> bytes`.

- [ ] **Step 1: Replace the existing artifact expectations with failing format-contract tests**

```python
def test_artifact_set_is_docx_csv_html_with_one_snapshot(template_bytes: bytes) -> None:
    artifacts = ArtifactService("renderer-v1").create(snapshot(), scorecard(), template_bytes)
    assert [(a.filename, a.media_type) for a in artifacts] == [
        ("protocol.docx", DOCX_MEDIA_TYPE),
        ("traceability.csv", "text/csv; charset=utf-8"),
        ("scorecard.html", "text/html; charset=utf-8"),
    ]
    assert {a.snapshot_id for a in artifacts} == {"snapshot-a"}
    assert all(a.verify_integrity() for a in artifacts)
```

Add assertions that the CSV has the fixed header, the HTML contains six named dimensions and the disclaimer, and neither HTML nor its schema contains `overall`, `composite`, `readiness percentage`, or `%`.

- [ ] **Step 2: Run rendering tests and observe JSON-format failures**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/rendering/test_artifacts.py tests/unit/rendering/test_scorecard_html.py -v`  
Expected: FAIL because the service returns JSON artifacts and has no HTML renderer.

- [ ] **Step 3: Implement deterministic CSV and scorecard HTML**

Use `traceability_csv()` for UTF-8 CSV. In `scorecard.py`, escape every dynamic value with `html.escape`, sort dimensions by the six canonical names, include snapshot and renderer metadata, render blocker codes and messages as a list, and include this exact disclaimer:

```text
Synthetic POC output only; not validated and no clinical, regulatory, submission, operational, or readiness claim is made.
```

- [ ] **Step 4: Make template bytes mandatory and preserve the package**

Change `ArtifactService.create` to accept `template: bytes`. Call `DocxRenderer.render(snapshot, template)` and remove the production fallback from this path. Add a deterministic disclaimer insertion target `[[POC_DISCLAIMER]]`; reject templates without exactly one disclaimer target and exactly one target for each exported passage section.

- [ ] **Step 5: Verify format tests and deterministic hashes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/rendering tests/unit/rendering -v`  
Expected: PASS, including byte-for-byte identical outputs and hashes for identical inputs.

- [ ] **Step 6: Commit**

```bash
git add backend/src/protocol_poc/rendering backend/tests/integration/rendering backend/tests/unit/rendering
git commit -m "feat: render governed export formats"
```

---

### Task 3: Orchestrate all-or-nothing artifact creation from frozen state

**Files:**
- Create: `backend/src/protocol_poc/export/artifact_service.py`
- Create: `backend/src/protocol_poc/export/orchestration.py`
- Modify: `backend/src/protocol_poc/export/service.py`
- Modify: `backend/src/protocol_poc/export/gate.py`
- Create: `backend/tests/integration/export/test_artifact_orchestration.py`
- Modify: `backend/tests/integration/export/test_snapshot.py`

**Interfaces:**
- Produces: `ArtifactDescriptor(id: str, name: str, media_type: str, sha256: str, snapshot_id: str, download_url: str)`.
- Produces: `ExportResult(snapshot_id: str, artifacts: tuple[ArtifactDescriptor, ...])`.
- Produces: `ExportOrchestrator.create(ctx, study_id, command) -> ExportResult`.
- Produces: `ExportArtifactRepository.get(ctx, artifact_id) -> tuple[ExportArtifactRecord, bytes]`.

- [ ] **Step 1: Write a failing happy-path orchestration test**

Seed one tenant, study, approved facts, accepted passages with current versions and support links, a stored template `FileVersion`, and a blocker-free scorecard. Assert that `create` returns exactly the three descriptors, persists three immutable rows, stores exact bytes, and uses one snapshot ID and renderer version.

- [ ] **Step 2: Write failing fail-closed tests**

Parameterize missing template version, tenant mismatch, template hash mismatch, ambiguous section target, renderer exception, and second-object storage failure. Assert that no successful descriptors are returned, no partial `ExportArtifactRecord` rows remain, newly written objects are deleted, and the audit event contains only sanitized failure codes.

- [ ] **Step 3: Run orchestration tests and observe missing-service failures**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/export/test_artifact_orchestration.py -v`  
Expected: FAIL because orchestration and artifact repository types do not exist.

- [ ] **Step 4: Tighten template validation in the export gate**

Load `FileVersion` by `template_version_id`, tenant, study-linked `FileRecord`, and role `template`. Compare `checksum_sha256` with the command hash. Add hard blockers `TEMPLATE_VERSION_INVALID` and `TEMPLATE_HASH_MISMATCH` before snapshot creation. Do not trust caller-provided template metadata.

- [ ] **Step 5: Implement the artifact repository**

Use storage keys of the form `tenants/{sha256(tenant_id)}/exports/{snapshot_id}/{artifact_id}/{filename}`. Write all bytes first, verify storage checksums, add all metadata rows, and flush. On any error, roll back and delete every object written by the attempt. Retrieval queries by both artifact ID and tenant ID, reads exact bytes, and verifies size and SHA-256 before returning.

- [ ] **Step 6: Implement export orchestration**

Within one transaction, calculate the `QualityScorecard`, call `ExportService.create_snapshot`, load the snapshot passage rows, build traceability rows from the accepted passage claims/support records captured during the same transaction, retrieve the exact template bytes, create the three formats, persist them, set `snapshot.renderer_version` before the snapshot becomes immutable, and append `export.artifacts_created` with artifact IDs, filenames, hashes, and no clinical text.

- [ ] **Step 7: Run export integration and safety tests**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/export tests/unit/export tests/evaluation/test_adversarial_exports.py -v`  
Expected: PASS; unsupported-content scenarios still export zero unsupported clinical facts.

- [ ] **Step 8: Commit**

```bash
git add backend/src/protocol_poc/export backend/tests/integration/export backend/tests/unit/export
git commit -m "feat: orchestrate snapshot artifact exports"
```

---

### Task 4: Return descriptors and authenticated downloads through the API

**Files:**
- Modify: `backend/src/protocol_poc/export/routes.py`
- Modify: `backend/src/protocol_poc/app.py`
- Create: `backend/tests/integration/export/test_export_api.py`
- Modify: `backend/tests/unit/test_identity.py`

**Interfaces:**
- `POST /api/studies/{study_id}/exports` returns `{snapshotId, blockers, artifacts[]}`.
- `GET /api/export-artifacts/{artifact_id}` returns attachment bytes for the authenticated tenant.

- [ ] **Step 1: Write failing API contract tests**

Assert a valid signed request returns status 201 and exactly three descriptors with camel-case JSON fields. Assert each download returns the descriptor media type, `Content-Disposition: attachment; filename="..."`, exact bytes, and matching digest. Assert unknown and cross-tenant IDs both return 404. Assert denied export returns 409 with every blocker and no snapshot/artifacts.

- [ ] **Step 2: Run the API tests and observe the old response shape**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/export/test_export_api.py -v`  
Expected: FAIL because export returns only `snapshot_id` and no download route exists.

- [ ] **Step 3: Implement typed response models and routes**

Add Pydantic `ArtifactResponse` and `ExportResponse` models using camel-case aliases. Inject `LocalFileStorage(Path(settings.local_storage_path))` into the orchestrator. Map `ExportDenied` to 409, template/render/storage failures to a sanitized 409 `EXPORT_FAILED`, invalid identity to 401, and absent/cross-tenant artifacts to 404. Use `StreamingResponse(BytesIO(content), media_type=record.media_type)` for downloads.

- [ ] **Step 4: Verify API and identity tests**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/export/test_export_api.py tests/unit/test_identity.py -v`  
Expected: PASS, including proof that insecure identity headers remain forbidden when `environment=production`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/protocol_poc/export/routes.py backend/src/protocol_poc/app.py backend/tests/integration/export/test_export_api.py backend/tests/unit/test_identity.py
git commit -m "feat: expose governed export downloads"
```

---

### Task 5: Replace frontend export fixtures with the real API

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/app/api/studies/[studyId]/exports/route.ts`
- Create: `frontend/src/app/api/artifacts/[artifactId]/route.ts`
- Modify: `frontend/src/features/export/ExportPanel.tsx`
- Modify: `frontend/src/app/studies/[studyId]/draft/page.tsx`
- Modify: `frontend/tests/export/ExportPanel.test.tsx`
- Create: `frontend/tests/export/exportApi.test.ts`
- Modify: `compose.yaml`
- Modify: `.env.example`

**Interfaces:**
- Extends `ExportArtifact` with `id`, `mediaType`, and `downloadUrl`.
- Produces `protocolExportApi.createExport(studyId) -> Promise<ExportState>`.

- [ ] **Step 1: Write failing frontend API tests**

Mock `fetch` only at the HTTP boundary. Assert `protocolExportApi` posts to `/api/studies/{studyId}/exports`, parses real descriptors, surfaces all 409 blockers, and never returns `snapshot-demo-001` or `demo-*-sha256`.

- [ ] **Step 2: Write failing panel tests**

Assert the panel shows a pending state, disables duplicate submission, displays a server error without discarding blockers, and renders three `<a download>` links whose text, snapshot IDs, and hashes come from the API response.

- [ ] **Step 3: Run frontend tests and observe fixture failures**

Run: `cd frontend && pnpm test -- tests/export`  
Expected: FAIL because `demoExportApi` returns hard-coded metadata and artifact types lack download fields.

- [ ] **Step 4: Implement Next.js server proxies**

The export proxy posts to `${API_URL}/api/studies/${studyId}/exports` with `X-Tenant-ID: synthetic-demo`, `X-Actor-ID: local-writer`, and development/test identity headers. It maps backend download URLs to same-origin `/api/artifacts/{id}`. The artifact proxy fetches backend bytes with the same server-side identity context and forwards `Content-Type`, `Content-Disposition`, and the body. Neither route exposes secrets to the browser.

- [ ] **Step 5: Implement the real frontend client and panel**

Delete `successfulExport` and `demoExportApi`. Export `protocolExportApi`. Keep the initial `demoExportState` empty only as a render state. Use the real API by default in `ExportPanel`, show `Creating export…`, render server blockers, and provide download links after success.

- [ ] **Step 6: Configure safe local identity mode**

Set Compose defaults `ENVIRONMENT=development` and `ALLOW_INSECURE_IDENTITY_HEADERS=true`; retain application enforcement that this mode fails in production. Document these as local-only settings in `.env.example`.

- [ ] **Step 7: Run frontend tests, lint, and type checking**

Run: `cd frontend && pnpm test && pnpm lint && pnpm typecheck`  
Expected: PASS with no hard-coded successful export metadata.

- [ ] **Step 8: Commit**

```bash
git add frontend compose.yaml .env.example
git commit -m "feat: connect UI to governed exports"
```

---

### Task 6: Seed real synthetic export state and verify downloads end to end

**Files:**
- Create: `backend/src/protocol_poc/testing/seed_service.py`
- Modify: `backend/src/protocol_poc/testing/routes.py`
- Modify: `backend/tests/unit/testing/test_routes.py`
- Modify: `frontend/tests/e2e/helpers.ts`
- Modify: `frontend/tests/e2e/happy-path.spec.ts`
- Modify: `frontend/tests/e2e/blocked-export.spec.ts`
- Modify: `frontend/tests/e2e/fact-change-invalidation.spec.ts`
- Modify: `frontend/playwright.config.ts`

**Interfaces:**
- `POST /test/studies/{study_id}/seed` resets and inserts deterministic database/storage state for one named scenario.
- Browser tests use the ordinary export and artifact routes after seeding.

- [ ] **Step 1: Write failing test-seed contract tests**

Assert `happy_path` creates a study, four accepted supported passages, approved facts, current fact/passage versions, and a stored template containing exactly one target for each section and the disclaimer. Assert blocked and invalidation scenarios create the corresponding real blocker state. Assert reset removes test records and local objects. Assert every route remains 404 when `APP_ENV` is not `test`.

- [ ] **Step 2: Run seed tests and observe in-memory-fixture failures**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/testing/test_routes.py -v`  
Expected: FAIL because current test routes only update an in-memory scenario dictionary.

- [ ] **Step 3: Implement deterministic seed service**

Use the application session factory and `LocalFileStorage`; insert only synthetic values from the checked-in fixtures. Store the checked-in template as a real `FileRecord`/`FileVersion`. For `happy_path`, create export-eligible state. For `unsupported_eligibility`, add an unsupported-content quality blocker. For `fact_change_invalidation`, create a stale accepted passage. Return only scenario identifiers and state required by pages, never successful artifact descriptors.

- [ ] **Step 4: Rewrite happy-path browser assertions around downloaded bytes**

After clicking `Create export`, use Playwright requests to download each same-origin link. Assert response status 200, filenames, media types, non-empty bodies, SHA-256 equality with the UI descriptor, one shared snapshot ID, DOCX ZIP signature, CSV fixed header and evidence row, HTML disclaimer and six dimensions, and absence of composite/readiness percentages.

- [ ] **Step 5: Preserve server-side blocked journeys**

Assert unsupported eligibility returns the backend blocker and no artifact rows. Assert changed dose leaves the passage stale, export returns 409, and no artifact download link appears.

- [ ] **Step 6: Run browser tests**

Run: `PATH=/Users/chriskelly/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH make e2e`  
Expected: 3 passed; test stack is removed afterward.

- [ ] **Step 7: Commit**

```bash
git add backend/src/protocol_poc/testing backend/tests/unit/testing frontend/tests/e2e frontend/playwright.config.ts
git commit -m "test: verify real protocol artifact journey"
```

---

### Task 7: Complete release evidence and self-testing instructions

**Files:**
- Modify: `README.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/safety-case.md`
- Create: `docs/release-checklist.md`
- Modify: `backend/tests/evaluation/test_documented_controls.py`

**Interfaces:**
- Produces reproducible local self-test instructions and recorded hashes/inspection results for the synthetic release snapshot.

- [ ] **Step 1: Write a failing documentation-control test**

Require `docs/release-checklist.md` to name all three artifacts, record one shared snapshot ID, contain three lowercase SHA-256 digests, record DOCX visual inspection, and repeat the synthetic-only/non-validated limitation.

- [ ] **Step 2: Run the documentation test and observe failure**

Run: `cd backend && .venv/bin/python -m pytest tests/evaluation/test_documented_controls.py -v`  
Expected: FAIL because the release checklist does not exist.

- [ ] **Step 3: Run the complete release suite**

Run in order:

```bash
PATH=/Users/chriskelly/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH make lint
PATH=/Users/chriskelly/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH make typecheck
PATH=/Users/chriskelly/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH make test
make evaluation
PATH=/Users/chriskelly/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH make e2e
```

Expected: every command exits 0; evaluation reports `unsupported clinical facts exported: 0`; browser suite reports 3 passed.

- [ ] **Step 4: Inspect the generated artifacts**

Retain one happy-path export in temporary QA space. Verify each file digest independently. Render `protocol.docx` with the Documents skill renderer, inspect every page image at 100%, and confirm template headings, page furniture, disclaimer, accepted passage placement, no overlap/clipping, and no unresolved `[[...]]` tokens. Parse the CSV for the fixed columns and evidence locations. Inspect the HTML for six dimensions, shared snapshot metadata, disclaimer, and prohibited composite/readiness language.

- [ ] **Step 5: Document reproducible user testing**

Update the README and demo script with: copy `.env.example` to `.env`, `make bootstrap`, `make up`, open the review URL, approve the synthetic critical fact, accept passages, create export, download all three files, run the blocked scenarios, and `make down`. State that this tests a synthetic POC and is not validation.

- [ ] **Step 6: Record release checklist and rerun its test**

Record the actual snapshot ID, three actual SHA-256 digests, commands, test counts, visual inspection result, and known limitations. Run: `cd backend && .venv/bin/python -m pytest tests/evaluation/test_documented_controls.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add README.md docs backend/tests/evaluation/test_documented_controls.py
git commit -m "docs: record protocol export release evidence"
```

---

## Completion Gate

Before declaring the branch complete:

- Re-read `docs/superpowers/specs/2026-07-13-full-path-export-design.md` and map every requirement to a passing test or inspection record.
- Run `git diff --check` and confirm the worktree is clean after commits.
- Use `superpowers:verification-before-completion` and `superpowers:finishing-a-development-branch`.
- Present merge, pull-request, keep-branch, or cleanup choices without modifying `main` automatically.
