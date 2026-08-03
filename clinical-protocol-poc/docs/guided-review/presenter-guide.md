# Presenter Guide

## Session contract

Allow 35 to 45 minutes. Share only the application window and retain control of every action. The reviewer may ask questions and request that any screen or artifact be revisited.

## Opening: 5 minutes

State: “This is a local synthetic proof of concept. It demonstrates evidence-controlled protocol drafting and mistake recovery. It is not validated and is not ready for clinical, regulatory, submission, operational, or production use.”

Explain that the walkthrough will show one successful study and one study that must be corrected before work can continue.

## Successful workflow: 10 to 15 minutes

Use `fixtures/reliability-pilot/standard/`.

1. Create and open a study.
2. Upload `synopsis.docx` and `template.docx`.
3. Process the synopsis.
4. Review each extracted fact and its source evidence.
5. Generate and review the four passages.
6. Create the export.
7. Download and briefly open `protocol.docx`, `traceability.csv`, and `scorecard.html`.
8. Point out the shared snapshot and the distinct purpose of each artifact.

## Mistake and recovery: 10 minutes

Use `fixtures/reliability-pilot/missing-dose/`.

1. Create a second study.
2. Upload `synopsis.docx` and `template.docx`.
3. Process the synopsis and show the missing-dose blocker.
4. Explain that the application does not invent the dose.
5. Upload `corrected-synopsis.docx` as an explicit replacement.
6. Show preserved version history.
7. Reprocess and continue after the blocker clears.

## Role-specific discussion: 10 to 15 minutes

Use `questions.md`. Ask the shared questions first, followed by the questions for the reviewer’s role. Record confusion before explaining it.

## Unexpected behavior

Do not conceal unexpected behavior. State what happened, record the action and visible result, and avoid improvising with unapproved files. If needed, continue by opening previously generated synthetic artifacts while retaining the failure in the feedback record.

## Closing

Thank the reviewer, explain that feedback will shape a broader synthetic Generalization and Evaluation milestone, and make no promise that a requested feature will be implemented.
