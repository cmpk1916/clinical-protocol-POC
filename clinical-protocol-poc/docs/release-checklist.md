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

- Backend: 145 passed, including the release-checklist control.
- Frontend unit/component: 7 passed.
- Browser: 3 passed, covering happy-path downloads, unsupported eligibility blocking, and changed-fact invalidation.
- Static analysis: backend lint and typing passed across 72 source files; frontend lint and type checks passed.
- Evaluation invariant: `unsupported clinical facts exported: 0`.

## Reproduction

1. Copy `.env.example` to `.env`.
2. Run `make demo` and open the printed review URL.
3. Approve the synthetic critical fact, accept the valid passage, create an export, and download all three artifacts.
4. Run `make evaluation` and `make e2e` for the safety and browser evidence.
5. Run `make down` when finished.

Known limitations include synthetic fixtures, local header-based identity, a bounded four-section protocol, no live research, no production authorization model, and no regulated-system validation.
