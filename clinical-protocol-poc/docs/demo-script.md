# Demo Script

## Before the demo

1. Confirm the repository contains synthetic data only.
2. Start the local stack with `make up`.
3. Open `http://localhost:3000/studies/synthetic-phase-2/review`.
4. State clearly: this is a proof of concept, not a validated clinical or regulatory system.

## Successful governed path

1. Point out the always-visible export blocker.
2. Open the dose fact and compare the current value, candidate value, exact evidence location, confidence metadata, and downstream impact.
3. Select **Approve fact** and show that the critical-fact checkbox is required.
4. Open the Model Explorer and show provenance, version, relationships, conflicts, affected passages, and the text alternative for relationships.
5. Open `/studies/synthetic-phase-2/draft`.
6. Review the passage evidence, guidance, findings, and impact.
7. Show the six scorecard dimensions and the disclaimer; note that no overall readiness percentage exists.
8. Select **Create export**.
9. Show `protocol.docx`, `traceability.csv`, and `scorecard.html`, their SHA-256 values, and their shared snapshot ID.

## Blocked adversarial path: unsupported eligibility

1. Run the automated browser journey or seed `unsupported_eligibility` in test mode.
2. Show the unsupported eligibility finding in the passage and export panels.
3. Show that **Create export** is disabled.
4. Explain that the server gate, not the button, is authoritative.

## Blocked adversarial path: changed fact

1. Seed `fact_change_invalidation` in test mode.
2. Show that the accepted passage becomes stale after the approved dose changes.
3. Show that passage acceptance and export are denied until revalidation.

## Close

Reiterate the limitations: synthetic data only, no live research, no clinical or regulatory claim, no submission-readiness claim, and not a validated system.
