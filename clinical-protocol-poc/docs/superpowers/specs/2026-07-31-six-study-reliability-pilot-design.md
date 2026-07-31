# Six-Study Synthetic Reliability Pilot

## Context

The local Clinical Protocol POC now completes its governed self-service workflow from supported synthetic DOCX inputs through deterministic extraction, fact review, passage review, immutable export, archive, restore, and saved-export resumption. The current self-service acceptance evidence relies on one synopsis/template pair. Seeded adversarial scenarios cover important safety invariants, but they bypass the document upload and extraction path used by a person operating the application.

The next milestone must test reliability across multiple real self-service document packs. It must also prove that mistakes are caught, explained, and recoverable without silently inventing or modifying clinical content. The work remains local, single-user, deterministic, and synthetic-only.

## Goal and Success Definition

Build a six-study synthetic pilot in which three valid studies reach export directly and three mistake studies are first blocked for an exact expected reason, present a safe correction path, preserve version and review history, and then reach export after explicit user correction.

Reliability is the primary outcome. Ease-of-use improvements are included only where needed to explain and correct the tested mistakes. Supporting additional protocol sections, arbitrary DOCX structures, live model calls, real clinical data, or production deployment is not part of this milestone.

## Approach

Use six real self-service DOCX study packs. Every pack enters through the same upload, validation, processing, review, drafting, validation, and export APIs used by the application. Do not substitute seeded database state for any pilot result.

Each pack includes a machine-readable gold manifest containing its expected facts, blocker codes, next action, correction, final passages, and export outcome. Mistake packs also include the corrected input file when their recovery requires source replacement.

Seeded adversarial scenarios remain valuable regression tests, but they are supporting evidence rather than pilot subjects.

## Study Matrix

### Direct-success studies

1. **Standard study**
   - Uses the supported synopsis and template structure with a distinct set of synthetic values.
   - Exercises the ordinary ten-fact path, four accepted passages, six quality dimensions, and three-artifact export.

2. **Vocabulary variation**
   - Uses supported alternate headings such as `Arms/Interventions`, `Study Population`, or `Eligibility Criteria`.
   - Varies capitalization and whitespace while preserving the declared document contract.
   - Proves that normalization is reliable without accepting unsupported headings.

3. **Value variation**
   - Uses a decimal milligram dose, a different supported `Week N` timepoint, and a distinct population and eligibility statement.
   - Exercises singular, plural, or omitted optional duration within the existing contract.
   - Does not add a second arm, new units, new frequencies, or new protocol sections.

### Mistake-and-recovery studies

4. **Missing dose**
   - The initial synopsis omits the supported milligram dose or once-daily frequency.
   - Processing must fail with `SYNOPSIS_DOSE_MISSING` and export must remain unavailable.
   - The recommended next action must be `Upload corrected synopsis`, not an ineffective retry.
   - A corrected synopsis replacement must preserve input history, invalidate only dependent downstream state, and resume processing from the correct step.

5. **Broken template**
   - The initial template omits exactly one required section or disclaimer token.
   - Upload validation must identify `TEMPLATE_TOKEN_MISSING`, name the affected token, and keep the invalid version from becoming current.
   - The user uploads a corrected conforming template. Existing valid synopsis state must remain intact.

6. **Unsupported passage edit**
   - The input documents are valid and deterministic drafting succeeds.
   - The pilot deliberately edits one passage to add a synthetic claim unsupported by its approved facts.
   - Validation must show the exact finding, export must remain blocked, and the user must be offered passage revision or regeneration.
   - Correcting or regenerating the passage must clear the finding before acceptance and export.

## Fixture and Manifest Structure

Store each study under a stable directory such as:

```text
fixtures/reliability-pilot/<study-key>/
  manifest.json
  synopsis.docx
  template.docx
  corrected-synopsis.docx   # only when required
  corrected-template.docx   # only when required
```

Generate DOCX fixtures with a checked-in deterministic builder rather than manually editing ZIP packages. The builder may reuse existing supported self-service fixture helpers and must reproduce byte-identical documents from declared source content.

Each manifest records:

- schema version and stable study key;
- synthetic study name and expected initial outcome;
- input filenames and expected SHA-256 hashes;
- ordered expected candidate facts, including critical status and normalized values;
- expected processing, validation, or workspace blocker codes;
- expected recommended next action;
- correction type and corrected input filename when applicable;
- expected post-correction current input versions and preserved historical versions;
- expected passage text or deterministic passage fact bindings;
- expected final export decision; and
- the exact three required artifact names and structural checks.

Manifests contain no generated database identifiers, timestamps, snapshot identifiers, or artifact hashes that legitimately change between independent runs.

## Correction Guidance

The application must distinguish correctable source content from transient technical failure.

- Document-content finding: recommend upload of a corrected synopsis.
- Template-contract finding: keep the invalid version noncurrent and recommend a corrected template upload.
- Fact-review issue: direct the user to explicit fact review or conflict resolution.
- Passage-validation issue: direct the user to revise or regenerate the affected passage.
- Temporary processing failure: offer retry.

For deterministic synopsis findings such as `SYNOPSIS_DOSE_MISSING`, retrying the unchanged file is not a valid primary action. The workspace derives an `Upload corrected synopsis` action and keeps the synopsis input card available for versioned replacement.

Every blocker shown to the user includes:

- what is wrong;
- the stable finding code;
- the affected field, input, fact, or passage;
- why progress or export is blocked; and
- the recommended next safe action.

Corrections remain explicit user actions. The application must not automatically invent facts, alter source meaning, accept reviews, or rewrite unsupported clinical content.

## Pilot Runner and Data Flow

The automated pilot runner operates against an isolated local release stack and uses the real self-service HTTP interfaces.

For each study:

1. Create a new study.
2. Upload the manifest-declared synopsis and template.
3. Verify input hashes, conformance, and expected current-version state.
4. Process the synopsis and compare the authoritative state with the manifest.
5. For mistake studies, stop at the expected blocker, verify export denial and correction guidance, then apply the manifest-declared correction.
6. Review facts using manifest expectations and required critical confirmations.
7. Generate, validate, and accept all four passages.
8. For the unsupported-passage study, introduce the declared unsupported edit, verify denial, then correct it explicitly.
9. Create one export and download all three artifacts.
10. Verify shared snapshot linkage, individual SHA-256 integrity, file structure, traceability rows, scorecard dimensions, and absence of unresolved template tokens.

Each study uses isolated persisted state. A failure in one study is recorded and does not cause later study results to be reported as passing. The full pilot is also rerun on a fresh stack to verify repeatability.

## Reliability Report

The runner produces both machine-readable JSON and a human-readable Markdown report. Generated run reports live under ignored test-output storage; a reviewed retained summary may be committed deliberately as release evidence.

For each study, report:

- input filenames and hashes;
- extracted facts compared with gold values;
- expected and actual blocker codes;
- correction guidance and action applied;
- preserved version history;
- final passage and validation status;
- export denial before correction where required;
- final snapshot identifier and artifact hashes; and
- pass or fail with exact mismatches.

The summary reports six independent outcomes and the invariant `unsupported clinical facts exported: 0`. It does not compute or display a clinical, regulatory, submission, production, or readiness percentage.

## Error Handling and Fail-Closed Behavior

- A fixture whose hash differs from its manifest fails before upload.
- An unexpected fact, blocker, next action, passage, or export result fails that study; the runner does not update gold values automatically.
- A mistake study that reaches export before correction fails immediately.
- A corrected study that loses required historical versions fails.
- A partial artifact set, mismatched snapshot link, hash mismatch, unresolved template token, or malformed report fails the study.
- Infrastructure failure is reported separately from a clinical-workflow mismatch and cannot be counted as a pass.
- Pilot helper routes remain limited to `APP_ENV=test`; the runner does not rely on seeded production state.

## Testing Strategy

- Unit tests specify manifest schema validation, deterministic fixture generation, correction-action classification, result comparison, and report rendering.
- Backend integration tests prove deterministic source findings recommend replacement while transient processing failures recommend retry.
- Frontend tests prove the workspace displays the finding, affected area, explanation, and recommended correction action.
- End-to-end tests exercise each pack through the real self-service flow, including all three corrections.
- Existing adversarial evaluation, backend, frontend, static-analysis, and end-to-end suites remain green.
- The complete six-study pilot runs twice on clean stacks and produces identical facts, blockers, next actions, and passage content. Run-specific identifiers and timestamps may differ.

## Acceptance Criteria

The milestone is complete only when:

- all six study packs pass their gold manifests;
- all three valid studies export without unexpected blockers;
- all three mistake studies are denied export for the exact expected reason before correction;
- missing-dose recovery uses corrected synopsis replacement rather than unchanged-file retry;
- broken-template recovery leaves the invalid version noncurrent and accepts the corrected template;
- unsupported-passage recovery requires explicit revision or regeneration and revalidation;
- correction preserves required input and review history;
- all corrected studies produce `protocol.docx`, `traceability.csv`, and `scorecard.html` from one snapshot;
- no unsupported content is exported;
- two clean-stack pilot runs agree on deterministic facts, blockers, actions, and passages;
- the human-readable report identifies every mismatch without presenting a composite readiness score; and
- the full existing verification suite passes.

## Out of Scope

- Real sponsor, patient, confidential, clinical, regulatory, or production documents.
- Live model or web retrieval.
- Automatic clinical-content correction or autonomous review decisions.
- Additional protocol sections, multiple-arm extraction, new dose units, new frequency vocabularies, or arbitrary document layouts.
- Historical export browsing beyond the latest saved export.
- Multi-user accounts, production authentication, remote hosting, regulatory validation, or submission readiness.
