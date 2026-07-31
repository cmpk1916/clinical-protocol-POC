# Resumable Export Artifacts

## Context

The workspace summary correctly reports `View export artifacts` after a study has produced an export, including after the study is archived and restored. The drafting page, however, always initializes its export panel with an empty snapshot and artifact list. The API supports creating an export and downloading a known artifact, but it does not provide a way to retrieve the latest saved export for a study. Consequently, reopening a completed study incorrectly shows `Create export` even though its immutable snapshot and three artifacts remain stored.

## Decision

Add a tenant-scoped, read-only endpoint that returns the latest saved export for a study. The drafting page will request that state whenever it loads and pass the authoritative result to the export panel.

If a saved export exists, the panel displays its snapshot identifier and the download links for `protocol.docx`, `traceability.csv`, and `scorecard.html`. It does not offer `Create export`. If no export exists, the endpoint returns an empty export state and the existing creation flow remains available.

This behavior applies whenever a completed study is reopened, not only after archive and restore.

## Alternatives Considered

- Embed artifacts in the general workspace summary. Rejected because artifact descriptors and download links belong to the export boundary, while the workspace summary should remain a compact workflow guide.
- Store the latest export only in browser state. Rejected because it would be lost on refresh, restart, or another browser session and would not provide resumability.

## Components and Data Flow

1. The export repository queries the newest snapshot for the requested tenant and study, then loads its artifact descriptors in a deterministic filename order.
2. A `GET /api/studies/{study_id}/exports/latest` endpoint verifies local identity and tenant-scoped study access, then returns the latest snapshot and artifacts or an empty export state.
3. The existing local frontend proxy forwards the request without changing the trust boundary.
4. The drafting page loads passages, quality, workspace state, and latest export state together.
5. The export panel renders saved artifacts when a snapshot exists. `Create export` is shown only when no saved export exists and the server has supplied a valid export command.

Archive and restore continue to change only study lifecycle fields. They do not mutate snapshots, artifacts, or storage objects.

## Error Handling

- An unknown or cross-tenant study returns `404`; it is not treated as a study with no exports.
- A study with no prior snapshot returns a successful empty export state.
- An incomplete snapshot or missing artifact set is reported as an integrity error instead of displaying partial downloads or enabling duplicate creation.
- A frontend load failure makes the drafting workspace unavailable with its existing explicit error state; it does not silently replace saved export data with an empty state.
- Existing artifact download integrity checks remain authoritative.

## Testing and Acceptance Criteria

- Backend tests prove that the latest export endpoint returns exactly one snapshot and all three artifact descriptors in deterministic order.
- Backend tests prove that a study with no export returns an empty state and that cross-tenant access returns `404`.
- Frontend tests prove that reopening a completed study loads and displays all three saved downloads without offering `Create export`.
- Frontend tests prove that a study with no export retains the existing enabled or blocked creation behavior derived from its workspace state.
- The archive/restore end-to-end test completes an export before archiving, restores the study, reopens it, and confirms that the same snapshot and three artifact links remain visible.
- Existing backend, frontend, and end-to-end tests continue to pass.

## Out of Scope

- Listing historical exports or selecting older snapshots.
- Deleting, replacing, or modifying immutable export snapshots.
- Changing the three artifact formats or their rendering logic.
- Adding remote storage, authentication changes, or multi-user behavior.
