# Full-Path Export Design

**Date:** 2026-07-13  
**Status:** Approved for implementation planning  
**Scope:** Complete the clinical protocol POC's real export path without changing its synthetic-only, non-validated safety boundary.

## Problem

The accepted baseline proves snapshot gating and displays expected artifact names, but the release journey is incomplete. The backend artifact service emits JSON support files, the export endpoint returns only a snapshot identifier, the frontend displays hard-coded artifact metadata, and the browser test therefore does not prove that downloadable artifacts came from the governed backend snapshot. The fallback DOCX renderer also produces unstructured paragraphs when it is not given the uploaded protocol template.

## Decision

Implement one server-authoritative export path that creates and exposes exactly three immutable artifacts from one validated snapshot:

- `protocol.docx`
- `traceability.csv`
- `scorecard.html`

Each artifact records the same snapshot identifier and renderer version, has a verified SHA-256 digest, and contains the required POC limitation language where its format permits. The frontend consumes this real export response and never synthesizes successful artifact metadata.

## Architecture

### Export orchestration

`ExportService` remains authoritative for the transactional gate and immutable snapshot. A dedicated export-artifact orchestration service loads the snapshot's accepted passage versions, traceability data, scorecard dimensions, and referenced template version. It passes only snapshot-frozen values to the format renderers. Artifact creation occurs only after the gate allows export.

If template retrieval, rendering, hashing, or artifact persistence fails, the request fails closed. The API must not advertise a partially created artifact set. A denied or failed export remains auditable and does not expose download metadata.

### Artifact formats

The DOCX renderer receives the stored template bytes associated with the snapshot's template version. It performs deterministic target replacement, preserves the template's styles and page furniture, rejects missing or ambiguous targets, and includes a visible synthetic-POC disclaimer without implying clinical, regulatory, or submission readiness.

The traceability renderer emits UTF-8 CSV with the approved fixed columns: section, passage, claim, fact value, evidence location, guidance release, review state, and validation status. The scorecard renderer emits standalone semantic HTML containing separate quality dimensions, blockers, snapshot metadata, and limitations. It must not calculate or display a composite readiness score.

### Persistence and downloads

Artifact bytes and metadata are stored behind a tenant-scoped artifact repository. Metadata includes artifact ID, tenant ID, snapshot ID, filename, media type, renderer version, size, SHA-256 digest, and creation time. Download lookup requires both the authenticated tenant and artifact ID; cross-tenant or unknown artifact requests return not found.

The export response contains the snapshot ID and all three artifact descriptors, including a download URL. Download responses use the stored media type and attachment filename and return the exact hashed bytes.

### Frontend

The export client calls the authenticated backend export endpoint and renders the returned artifact descriptors. Successful rows show filename, SHA-256 digest, shared snapshot ID, and a download link. Server blockers remain authoritative and visible. Client-side disabled states improve usability but do not replace server enforcement.

Test-only seed endpoints may establish deterministic synthetic study state, but they must exercise the same export orchestration and artifact download code used by the local demo. They may not return hard-coded successful artifact metadata.

## Data flow

1. The writer requests export with the expected study and template versions.
2. The server locks and validates the study, calculates quality blockers, and denies export on any failure.
3. The server creates an immutable snapshot of approved facts, accepted passages, and the template reference.
4. The artifact orchestrator loads only snapshot-frozen data and the exact template bytes.
5. The three renderers create DOCX, CSV, and HTML bytes.
6. The server hashes and persists the complete artifact set, then returns descriptors.
7. The frontend displays descriptors and downloads bytes from tenant-scoped endpoints.

## Error handling and invariants

- Any gate blocker, validation outage, stale passage, version conflict, missing template, ambiguous template target, render failure, or persistence failure denies a successful export response.
- Exactly three artifacts are returned on success; partial sets are never advertised.
- All returned artifacts share one snapshot ID and renderer version.
- Downloaded bytes must match the descriptor's SHA-256 digest.
- Artifact lookup is tenant-scoped and does not reveal cross-tenant existence.
- The scorecard has separate dimensions and no composite readiness value.
- All artifact-facing content retains the synthetic-only and non-validated limitations.

## Testing strategy

Implementation follows red-green-refactor. Backend tests first specify the three formats, template preservation, metadata persistence, exact download bytes, hash verification, fail-closed behavior, and tenant isolation. Frontend tests specify the real export response and download links without demo metadata. Browser tests seed synthetic state, approve the critical fact, accept the passage, call the real export endpoint, download all three files, verify filenames, snapshot IDs, hashes, and representative contents, and retain the blocked-export and fact-invalidation journeys.

Release verification runs lint, type checking, backend and frontend tests, adversarial evaluation, and all browser journeys. The generated DOCX is rendered to page images and inspected on every page; CSV and HTML are checked for required fields, shared snapshot metadata, disclaimers, unresolved placeholders, and prohibited readiness language.

## Non-goals

- Production validation, regulatory compliance, submission readiness, or autonomous clinical decision-making.
- Live model-provider integration or live drafting research.
- Support for arbitrary sponsor templates beyond the approved POC template family.
- A generalized document-management platform or long-term artifact retention policy.
