# Self-Service Study Workflow Design

**Date:** 2026-07-17
**Status:** Design approved; pending written-spec review
**Scope:** Turn the synthetic clinical protocol POC into a resumable, single-user local application where a user can create a study, upload supported DOCX inputs, review deterministic facts and draft passages, export the existing three-artifact package, and archive or restore studies.

## Problem

The accepted POC proves the governed review, drafting, validation, snapshot, and export path for seeded synthetic data. It does not yet provide a normal application entry point for a user to create and manage studies. The home screen is a basic landing page, review and drafting screens can fall back to demo state, and the application has no complete browser workflow for creating a study, uploading source documents, resuming work, replacing an input safely, or archiving a study.

The next milestone must expose the real backend workflow without weakening the POC's existing safety boundary. In particular, successful progress must always reflect persisted server state; source documents must remain local; extraction must be deterministic; replacements must preserve history and invalidate downstream work when required; and export must continue to fail closed.

## Decision

Build a guided study workspace backed by the authoritative local API. A user creates a named synthetic study, uploads one supported synopsis DOCX and one supported protocol-template DOCX, reviews deterministically extracted facts with exact evidence, reviews four bounded draft sections, and exports exactly:

- `protocol.docx`
- `traceability.csv`
- `scorecard.html`

The dashboard derives the study's current stage, progress, blockers, and next safe action from persisted records. It does not store a separate mutable workflow-stage label. Closing and reopening the application therefore resumes the same state.

This release is single-user and local. It has no account or sign-in interface, makes no live AI calls, and sends no document content to an external service. Tenant scoping remains enforced internally so this milestone does not erode the existing isolation boundary.

## Product experience

### Home screen

The home screen is the study dashboard. It contains:

- a clear **Create study** action;
- an **Active** list showing each study's name, saved progress, blockers, last-updated time, and next action;
- an **Archived** view with a restore action; and
- an empty state that explains the synthetic-only POC and leads directly to study creation.

Archived studies are hidden from the Active list by default. The first release does not permanently delete studies.

### Guided workspace

Opening a study shows a persistent progress guide and one primary next action. Completed steps remain available for inspection. Blocked steps explain the exact prerequisite instead of appearing to succeed optimistically.

The workflow is:

1. Create the synthetic study.
2. Upload and validate the supported synopsis and protocol template.
3. Process the synopsis locally into candidate facts.
4. Review each candidate fact alongside its exact source evidence.
5. Generate, validate, and accept the four bounded draft sections.
6. Create the immutable export snapshot and download the three artifacts.

The four draft sections remain the existing bounded scope:

- `synopsis`
- `objectives_endpoints`
- `study_design`
- `eligibility`

The workspace routes into the existing fact review, passage review, quality, and export experiences. Demo or fallback data must never be used to represent success in the self-service path.

### Input history and replacement

Each input role has one current version and an immutable version history. Uploading the first valid file activates version 1. Uploading a later file opens an impact preview and requires explicit confirmation before it becomes current.

A synopsis replacement:

- creates a new immutable synopsis version;
- runs supported-structure validation and deterministic extraction before activation;
- supersedes the prior synopsis-derived fact set;
- marks passages that depend on the superseded facts stale;
- clears acceptance for affected passages; and
- routes the user back through fact review before drafting and export can continue.

A template replacement:

- creates a new immutable template version;
- preserves the current facts and passage reviews;
- checks the new template's required insertion points and disclaimer target; and
- blocks export until the new version passes template conformance.

Replacement activation and its required supersession or invalidation changes occur atomically. A failed replacement never displaces the current working version.

### Archive and restore

Archiving changes only the study's lifecycle state and records the action. It does not delete input versions, facts, passages, snapshots, or artifacts. An archived study cannot be edited or exported. Restoring it returns the unchanged study to the Active list at its previously derived workflow position.

## Supported document contract

This milestone deliberately supports a controlled POC document family, not arbitrary Word documents.

### Common DOCX requirements

Both inputs must:

- use the `.docx` format and the existing DOCX media type;
- pass the current secure package checks for size, compression, macros, external relationships, XML entities, unsafe paths, and unsupported text-bearing structures;
- contain readable text in ordinary body paragraphs or tables supported by the current parser; and
- be synthetic and suitable only for software evaluation.

Validation errors identify the missing, duplicate, damaged, unsafe, or unsupported requirement without echoing sensitive document content into logs or generic error responses.

### Synopsis requirements

The supported synopsis contains uniquely identifiable sections covering:

- study identity;
- objectives;
- endpoints and their timepoints;
- arms and interventions;
- intervention dose and frequency where applicable;
- study population; and
- eligibility criteria.

The local extractor recognizes the approved heading and field-label vocabulary case-insensitively, normalizes whitespace, and applies versioned deterministic rules. Required information that is absent or ambiguous blocks the extraction attempt as a whole. It does not create a partial candidate fact set.

The extracted fact set covers the existing bounded data model: study identity, objectives, endpoints, timepoints, arms, interventions, dose or frequency values, population, and structured eligibility criteria. Every candidate fact stores the synopsis version, extractor version, and exact evidence location used to create it.

### Template requirements

The supported template contains each of these insertion tokens exactly once:

- `[[SECTION:synopsis]]`
- `[[SECTION:objectives_endpoints]]`
- `[[SECTION:study_design]]`
- `[[SECTION:eligibility]]`
- `[[POC_DISCLAIMER]]`

A missing or duplicate token fails conformance. The template renderer preserves surrounding styles and page furniture and replaces only these allowlisted targets. No arbitrary content controls, inferred headings, or approximate insertion locations are supported in this release.

## Architecture

### System boundary

The guided browser workspace calls same-origin frontend server routes. Those routes attach the configured local identity on the server side and proxy to the authoritative FastAPI application. The browser does not manufacture identity headers or success responses.

FastAPI remains the authority for study lifecycle, input validation, processing, review state, replacement effects, quality blockers, snapshot creation, and artifact downloads. PostgreSQL stores workflow records and metadata. The existing local object store keeps immutable input and artifact bytes. Document content does not cross the local application boundary.

### Study service

`StudyService` owns create, list, detail, archive, and restore operations. Study creation requires a nonblank name and produces an active study in the local tenant. Lifecycle-changing commands use the expected study version so stale browser tabs cannot silently overwrite newer state.

The Study record gains lifecycle and update metadata while retaining its existing optimistic version:

- lifecycle state: `active` or `archived`;
- `created_at`;
- `updated_at`; and
- `archived_at`, nullable.

All study queries remain tenant-scoped.

### Workspace summary service

`WorkspaceSummaryService` calculates a read model from the current inputs, processing attempts, fact review states, passage states, quality blockers, and exports. Its output contains:

- the derived workflow step;
- completion status for each step;
- counts needed for progress summaries;
- current blockers;
- the single recommended next action; and
- current synopsis and template version descriptors.

The summary is derived on read rather than stored as another source of truth. The derivation order is: missing or invalid inputs, processing needed or failed, facts awaiting review, passages unavailable or awaiting review, export blocked, and export available or completed.

### Document workflow service

`DocumentWorkflowService` coordinates input upload, contract validation, processing, replacement preview, confirmed activation, and retry. It composes the existing secure ingest and storage services rather than bypassing them.

File history remains immutable. A file record represents the study and role; each upload creates or reuses a checksum-identical version. A current-version reference identifies the activated version for each role. Processing attempts record:

- study and tenant;
- synopsis version;
- extractor name and version;
- status: `pending`, `processing`, `succeeded`, or `failed`;
- stable error code and structured validation findings; and
- start and completion times.

The user may retry a failed processing attempt without re-uploading the unchanged synopsis. One active processing operation per study and synopsis version is permitted.

### Deterministic extraction

The deterministic local extractor is a versioned pure rules component. It consumes only persisted evidence from a validated synopsis version and returns a complete candidate-fact proposal or structured validation findings. It performs no network call and does not use the AI gateway or fixture provider.

On success, the document workflow service atomically persists the new candidate facts and their evidence links, marks the processing attempt successful, and activates the synopsis version when the operation is a confirmed replacement. On failure, no new fact set becomes current.

### Existing governed services

The existing fact review, impact analysis, bounded drafting, passage review, quality, snapshot, artifact orchestration, and download services remain authoritative. They are extended only where required to consume the activated input versions and deterministic facts.

Drafting remains deterministic and local for this milestone. Any current fixture-provider behavior used for bounded passage generation must be selected from saved study state and must not imply a live model call. A passage may be accepted only after its required facts are approved and its validation findings are clear.

Export retains the previously approved full-path invariants: it fails closed; freezes approved facts, accepted current passages, and the conformed current template; produces exactly three immutable artifacts; and exposes the exact stored bytes through tenant-scoped download endpoints.

### Frontend data ownership

The frontend displays server-provided study summaries, evidence, review state, blockers, versions, and artifacts. Client-side state may hold form input and loading state but is not the source of workflow truth. After every command, the workspace refreshes its server-derived summary.

Test-only seed helpers may remain for automated evaluation and the existing demo, but self-service application routes may not invoke them or fall back to their data.

## API shape

The same-origin frontend layer exposes the equivalent of these local backend capabilities:

- create and list studies, with active or archived filtering;
- load a study and its derived workspace summary;
- archive or restore a study with an expected version;
- upload an initial synopsis or template;
- validate and process a current synopsis;
- preview and confirm a synopsis or template replacement;
- retry processing for an unchanged input version;
- use the existing fact review, drafting, passage review, quality, export, and download operations.

Command responses return the new authoritative version or state needed by the UI. Domain conflicts use a conflict response and include enough current metadata for the UI to refresh. Cross-tenant, unknown, and inaccessible resources return not found without revealing whether another tenant owns them.

## State and invariants

- A study has at most one current synopsis version and one current template version.
- Input versions, processing attempts, audit events, snapshots, and artifacts are immutable history.
- Only a complete successful extraction can establish a current synopsis-derived fact set.
- A candidate fact always points to exact evidence in the synopsis version that produced it.
- Export uses only approved current facts, accepted non-stale current passages, and the conformed current template.
- Replacing a synopsis cannot leave dependent passages accepted against superseded facts.
- Replacing a template cannot reuse an earlier template silently at export.
- Archived studies cannot accept workflow mutations or new exports.
- Workflow stage is derived from authoritative records and cannot drift from them.
- UI success is never based solely on client state or fallback fixtures.
- The application continues to label outputs as synthetic, non-validated POC artifacts that are not clinical, regulatory, operational, or submission ready.

## Error handling

Invalid, damaged, unsafe, or unsupported documents are rejected before they become current. Supported-structure findings identify missing synopsis sections or fields and missing or duplicate template tokens. The prior valid current version remains usable after any failed upload, validation, extraction, or replacement.

Extraction is all-or-nothing. A failed attempt records stable findings and offers retry; it does not expose partial facts for review. Unexpected service or storage failures remain auditable and fail closed.

The replacement preview names the current and proposed versions and explains the downstream effect. Confirmation uses the expected study and input versions. If another operation changes either version first, the command returns a conflict and the UI asks the user to refresh before trying again.

Export remains unavailable when any required input is missing or invalid, processing is incomplete, facts await review, a passage is blocked, rejected, or stale, quality validation is unavailable or blocked, or the current template has not passed conformance.

## Testing strategy

Implementation follows red-green-refactor in end-to-end vertical slices.

Backend unit tests specify study lifecycle transitions, workspace-stage derivation, supported heading and field recognition, deterministic normalization and extraction, structured findings, template token conformance, and replacement impact calculations.

Backend integration tests specify tenant-scoped study APIs, immutable file history, current-version activation, processing retries, evidence links, atomic synopsis supersession and passage invalidation, template replacement behavior, optimistic conflicts, archive restrictions, fail-closed export, and preservation of existing full-path export invariants.

Frontend tests specify dashboard empty, active, and archived states; study creation; guided progress; upload validation feedback; evidence-backed review; replacement previews; retry behavior; archive and restore; resume from persisted state; and the absence of successful fallback data.

Browser tests cover these complete journeys:

1. Empty dashboard to study creation, two valid uploads, local extraction, fact review, four passage reviews, export, and download of all three files.
2. Close or navigate away, reopen the study, and resume at the derived saved step.
3. Replace the synopsis, verify earlier facts are superseded and dependent passages become stale, then re-review before export.
4. Replace the template, verify facts remain unchanged and export is blocked until the new template passes conformance.
5. Archive a study, verify it is read-only and hidden from Active, restore it, and resume unchanged.
6. Upload an invalid or unsupported document and verify clear findings, no partial fact set, and no displacement of the valid current version.

Release verification runs backend and frontend formatting, linting, type checking, unit and integration suites, adversarial evaluation, and all browser journeys. The final DOCX is rendered and visually inspected on every page. All three downloaded artifacts are checked for filenames, shared snapshot metadata, SHA-256 integrity, required limitation language, unresolved placeholders, and prohibited readiness claims.

## Delivery approach

Build the milestone as end-to-end vertical slices so each increment leaves a testable user outcome:

1. Study dashboard, creation, derived summary, and archive or restore.
2. Initial synopsis and template upload with supported-contract validation.
3. Deterministic extraction and evidence-backed fact review.
4. Guided passage workflow connected to the four existing bounded sections.
5. Existing governed export connected to the workspace and real downloads.
6. Versioned synopsis and template replacement with atomic downstream effects.
7. Full resume, failure, adversarial, and visual release verification.

Detailed file-level tasks and commit boundaries belong in the implementation plan created after this specification is reviewed.

## Non-goals

- Live AI or model-provider integration.
- Sending documents or document-derived content to an external service.
- Multi-user accounts, sign-in, roles, invitations, or concurrent collaborative editing.
- Arbitrary sponsor synopsis or template formats.
- PDF ingestion, scanned-document OCR, `.doc`, or macro-enabled Word files.
- Permanent deletion or retention-policy automation.
- Production hosting, production authentication, regulatory validation, submission readiness, or clinical use.
- Autonomous clinical decisions or claims that generated output is correct without human review.
