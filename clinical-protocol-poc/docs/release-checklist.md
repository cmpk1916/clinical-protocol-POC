# Release Checklist

## Scope and limitations

This record covers synthetic data only. The application is a proof of concept, not a validated system, and this checklist does not establish clinical, regulatory, operational, production, or submission readiness.

## Retained synthetic export

Shared snapshot ID: `01KXE9WSX32YFPM3CMKHV2Z7BX`

| Artifact | Independently verified SHA-256 |
| --- | --- |
| `protocol.docx` | `d4c6628e2755609f504b319a5cea3495a2cf4b5683c36b1ebf2d4882b6dd9540` |
| `traceability.csv` | `6417abf1c59c87ff48d925ec871bbb3ffa1713b5c4af67948b972e6d8926ca25` |
| `scorecard.html` | `d5b037a39e3e8d39abdda5a250f0820d8df759084e517bb8084fec9663472974` |

The hashes downloaded from the API matched fresh local SHA-256 calculations for all three files.

## Artifact inspection

- DOCX visual inspection: PASS. LibreOffice rendered one US Letter page and every rendered page was inspected at full resolution. The title, four section headings, accepted passages, running header, footer limitation, and prominent disclaimer were visible. No text was clipped or overlapping, and no unresolved `[[...]]` token remained.
- CSV inspection: PASS. The fixed columns were present, all four accepted section rows were included, and every row carried the synthetic source filename and paragraph 4 evidence location.
- HTML inspection: PASS. The shared snapshot and renderer metadata, all six quality dimensions, export status, and synthetic POC disclaimer were present. No composite score or readiness percentage was present.

## Automated evidence

- Backend: 357 passed and 4 concurrency tests skipped on SQLite, including the release-checklist and reliability-pilot controls.
- Frontend unit/component: 42 passed.
- Browser: 10 passed, covering full self-service export, blocked-content recovery, fact invalidation, input replacement, archive/restore, and saved-progress resumption.
- Static analysis: backend lint passed and strict typing passed across 89 source files; frontend lint and type checks passed.
- Evaluation: 18 passed, including all 13 adversarial export-denial scenarios.
- Evaluation invariant: `unsupported clinical facts exported: 0`.

## Six-study reliability evidence

The final synthetic reliability pilot completed three direct-success studies and three mistake-and-recovery studies through the real self-service HTTP workflow in each of two isolated clean stacks.

- Run A: 6 of 6 studies passed.
- Run B: 6 of 6 studies passed.
- Pre-correction export denials: 3 of 3 observed.
- Corrected synopsis, corrected template, and blocked-passage regeneration: PASS.
- Artifact integrity, traceability validation, scorecard limitations, and unresolved-template checks: PASS.
- Deterministic comparison after excluding run-specific IDs, timestamps, and hashes: PASS with no mismatches.
- `unsupported clinical facts exported: 0`.

The generated run reports remain ignored under `work/reliability-pilot/`. The reviewed stable summary is retained in `docs/reliability-pilot.md`; it contains no run-specific study, snapshot, artifact, or file-version IDs.

## Reproduction

1. Copy `.env.example` to `.env`.
2. Run `make demo` and open the printed review URL.
3. Approve the synthetic critical fact, accept the valid passage, create an export, and download all three artifacts.
4. Run `make evaluation` and `make e2e` for the safety and browser evidence.
5. Run `make reliability-pilot` for the two clean-stack six-study evaluation and deterministic comparison.
6. Run `make down` when finished.

Known limitations include synthetic fixtures, local header-based identity, a bounded four-section protocol, no live research, no production authorization model, and no regulated-system validation.
