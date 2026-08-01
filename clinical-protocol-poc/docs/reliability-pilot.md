# Six-Study Synthetic Reliability Pilot

## Purpose and limits

This pilot exercises six synthetic self-service studies through the same document upload, processing, fact review, passage review, and export interfaces used by the local application. It contains three direct-success studies and three mistake-and-recovery studies.

This is synthetic POC reliability evidence only. It is not system validation and does not establish a clinical, regulatory, submission, operational, production, or readiness claim. Real sponsor, patient, confidential, clinical, regulatory, or production documents are outside the pilot boundary.

## Study contract

| Study | Expected first outcome | Required completion |
| --- | --- | --- |
| `standard` | Direct success | Review the declared facts and passages, then verify all three export artifacts. |
| `vocabulary-variation` | Direct success with supported heading vocabulary | Review the declared facts and passages, then verify all three export artifacts. |
| `value-variation` | Direct success with supported value variations | Review the declared facts and passages, then verify all three export artifacts. |
| `missing-dose` | Export denied with `SYNOPSIS_DOSE_MISSING` | Upload and explicitly confirm the corrected synopsis replacement, preserve version history, reprocess, review, and export. |
| `broken-template` | Invalid template remains noncurrent with `TEMPLATE_TOKEN_MISSING` | Upload the corrected template, preserve the rejected version in history, then complete review and export. |
| `unsupported-passage-edit` | Edited passage is blocked with `UNSUPPORTED_DOSE` and export is denied | Explicitly regenerate the blocked passage, verify findings clear and version history advances, accept it, and export. |

The corrected synopsis, corrected template, and passage-regeneration paths are explicit user-equivalent actions. The application does not silently invent facts, change source meaning, approve reviews, or rewrite unsupported clinical content.

## Reproduction

From the application root, run:

```text
make reliability-pilot
```

The command creates two isolated Compose projects with separate disposable databases, object storage, application storage, and ports. It runs all six studies once in each clean stack, removes both stacks and their volumes, and compares deterministic results. It does not reset or reuse the normal local `protocol-poc` project.

Generated evidence is written under `work/reliability-pilot/`:

- `run-a.json` and `run-a.md`
- `run-b.json` and `run-b.md`
- `repeatability.json` and `repeatability.md`

This generated directory is ignored by Git because the full reports contain run-specific IDs, snapshots, and hashes. This document is the retained stable summary.

## Acceptance criteria and retained result

A passing pilot requires all of the following:

- 6 of 6 studies pass;
- all three expected pre-correction export denials occur;
- every correction preserves its required version history and reaches the expected reviewed state;
- each successful study exports exactly `protocol.docx`, `traceability.csv`, and `scorecard.html` from one snapshot;
- artifact hashes, traceability rows, validation status, template resolution, and scorecard limitations pass verification;
- two clean-stack runs agree after run-specific identifiers, timestamps, and hashes are excluded; and
- unsupported clinical facts exported: 0.

The Task 8 verification run passed both clean stacks at 6 of 6 studies, proved all three pre-correction denials and recoveries, produced zero unsupported exported facts, and passed the deterministic repeatability comparison with no mismatches.

## Known boundary

The pilot covers deterministic local extraction, four protocol sections, one supported arm representation, bounded dose units and frequency vocabulary, one local user context, and synthetic fixtures. It adds no live model calls, web research, remote hosting, production authorization, or regulated-system validation.
