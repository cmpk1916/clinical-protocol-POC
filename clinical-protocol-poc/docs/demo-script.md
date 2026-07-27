# Demo Script

## Before the demo

1. Confirm the repository contains synthetic data only.
2. Copy `.env.example` to `.env`, then run `make app` for a clean local stack.
3. Open `http://localhost:3000`, create a synthetic study, and upload `fixtures/self-service/synopsis.docx` and `fixtures/self-service/template.docx`.
4. Process the synopsis, review the candidate facts, generate and accept the four passages, then create the export.
5. State clearly: this is a proof of concept, not a validated clinical or regulatory system.

## Self-service archive and restore

1. From the home screen, archive the synthetic study and show that its workspace is read-only while saved inputs and evidence remain visible.
2. Select **Archived**, restore the study, return to its workspace, and show that the next safe action is enabled again.

## Seeded deterministic demo

For the retained seeded presentation, run `make demo` and open `http://localhost:3000/studies/synthetic-phase-2/review`. The path below assumes that seeded study.

## Successful governed path

1. Point out the always-visible export blocker.
2. Open the dose fact and compare the current value, candidate value, exact evidence location, confidence metadata, and downstream impact.
3. Select **Approve fact** and show that the critical-fact checkbox is required.
4. Open the Model Explorer and show provenance, version, relationships, conflicts, affected passages, and the text alternative for relationships.
5. Open `/studies/synthetic-phase-2/draft`.
6. Review the passage evidence, guidance, findings, and impact.
7. Show the six scorecard dimensions and the disclaimer; note that no overall readiness percentage exists.
8. Accept the valid passage, then select **Create export**.
9. Download `protocol.docx`, `traceability.csv`, and `scorecard.html`. Show their distinct SHA-256 values and shared snapshot ID.
10. Open the CSV to show the source filename and paragraph location, and open the scorecard to show all six dimensions without an overall readiness percentage.

## Blocked adversarial path: unsupported eligibility

1. Reset and seed the scenario, then refresh the draft page:

   ```bash
   curl -X POST http://127.0.0.1:8000/test/reset
   curl -X POST http://127.0.0.1:8000/test/studies/synthetic-phase-2/seed -H 'Content-Type: application/json' --data '{"scenario":"unsupported_eligibility"}'
   ```

2. Show the unsupported eligibility finding in the passage and export panels.
3. Show that **Create export** is disabled.
4. Explain that the server gate, not the button, is authoritative.

## Blocked adversarial path: changed fact

1. Reset and seed the changed-fact scenario, then refresh the draft page:

   ```bash
   curl -X POST http://127.0.0.1:8000/test/reset
   curl -X POST http://127.0.0.1:8000/test/studies/synthetic-phase-2/seed -H 'Content-Type: application/json' --data '{"scenario":"fact_change_invalidation"}'
   ```

2. Show that the accepted passage becomes stale after the approved dose changes.
3. Show that passage acceptance and export are denied until revalidation.

## Close

Reiterate the limitations: synthetic data only, no live research, no clinical or regulatory claim, no submission-readiness claim, and not a validated system.

Run `make down` to stop the local stack.
