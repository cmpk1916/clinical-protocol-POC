# Architecture

## Purpose and boundary

This proof of concept demonstrates a governed, synthetic-data-only path from bounded DOCX ingestion through fact review, passage drafting, deterministic validation, and snapshot-linked export artifacts. It is not a validated clinical system and does not claim clinical, regulatory, operational, production, or submission readiness.

## Main components

1. **Input and tenancy** — tenant-scoped persistence, append-only audit events, bounded DOCX parsing, and versioned source files.
2. **Canonical study model** — stable facts, provenance, relationships, conflicts, review status, and version tokens.
3. **AI gateway** — deterministic fixture responses constrained by declared schemas. Source text is data, never instruction.
4. **Guidance and drafting** — approved guidance releases and approved facts form the closed drafting context.
5. **Validation and review** — deterministic claim checks, cross-model checks, passage review, and dependency invalidation.
6. **Quality and export** — six separate quality dimensions, server-side hard blockers, immutable snapshots, deterministic rendering, traceability, and hashes.
7. **Writer interface** — guided fact review, model exploration, passage authoring, impact visibility, scorecard dimensions, and convenience export controls.

## Trust boundaries

- Uploaded DOCX content and extracted text are untrusted.
- AI output is untrusted until schema validation and deterministic checks pass.
- Browser controls are convenience controls; the API export gate is authoritative.
- Test seed/reset routes are registered only when `APP_ENV=test`; other environments return 404.
- Export artifacts are derived from one immutable snapshot and carry the same snapshot identifier.

## Data flow

```text
Synthetic DOCX
  -> bounded ingest and versioning
  -> candidate facts
  -> writer approval and conflict resolution
  -> approved canonical model
  -> closed-world passage context
  -> deterministic validation and passage review
  -> quality dimensions and server-side export gate
  -> immutable snapshot
  -> protocol DOCX + traceability + scorecard artifacts
```

## Deliberate limitations

- Synthetic fixtures only; confidential sponsor material and production clinical data are out of scope.
- No live drafting research or open-web retrieval.
- Fixture AI responses are not evidence of model performance in clinical use.
- The reference contract records a synthetic reviewer role; it is not evidence of an external medical-writer review.
- Security, privacy, accessibility, validation, deployment, and operational controls are POC-level.
- A passing evaluation does not establish safety, effectiveness, regulatory acceptability, or fitness for use.
