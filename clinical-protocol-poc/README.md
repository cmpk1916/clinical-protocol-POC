# Clinical Protocol POC

This is a local proof of concept for drafting selected clinical-trial protocol sections using synthetic data only.

## Safety statement

No protocol produced by this POC is claimed clinically, regulatorily, submission, operationally, or production ready. It must not be used with confidential sponsor documents or production clinical data. The POC does not make autonomous scientific, medical, or regulatory decisions.

This is **not a validated system**. It performs **no live drafting research** and must not be represented as supporting a clinical, regulatory, or submission-readiness claim.

## Run a self-service synthetic study

For a clean local workflow, the only prerequisites are Docker with Compose and `make`.

1. Copy `.env.example` to `.env`. The included values are local-only defaults and are not secrets suitable for another environment.
2. Run `make app`. This builds the application, applies migrations, and waits for a clean local stack; it does not seed a study.
3. Open `http://localhost:3000`, create a synthetic study, and open its workspace.
4. Upload `fixtures/self-service/synopsis.docx` and `fixtures/self-service/template.docx`, then select **Process synopsis**.
5. Review the synthetic candidate facts, generate and accept the four draft passages, then select **Create export**.
6. Download `protocol.docx`, `traceability.csv`, and `scorecard.html`. Confirm their shared snapshot ID and individual SHA-256 digests.
7. Archive a study from the home screen to make it read-only; use the **Archived** tab and **Restore** to return it to active work.
8. Run `make down` when finished. Add `--volumes` to the Compose command if you also want to remove disposable database and object-storage data.

The local stack and its documents are for synthetic evaluation data only. Do not upload patient, sponsor, confidential, clinical, regulatory, or production data; the POC has no external document-sharing workflow and makes no readiness claim.

## Seeded deterministic demo

Run `make demo` when you need the existing pre-seeded synthetic happy-path demonstration. It resets disposable local state and opens `http://localhost:3000/studies/synthetic-phase-2/review`; it is separate from the clean self-service workflow above.

Both workflows test a synthetic proof of concept. They are not system validation and do not establish clinical, regulatory, operational, production, or submission readiness.

## Development checks

Development also requires `uv`, Node.js 22, and pnpm 11.7.0. Run `make bootstrap` to install the locked dependencies, then run `make lint`, `make typecheck`, `make test`, `make evaluation`, and `make e2e`.

Run `make reliability-pilot` for the isolated six-study synthetic reliability evaluation. It creates two disposable clean stacks, runs three direct-success and three mistake-and-recovery studies through the real self-service interfaces, compares stable results, writes ignored local reports under `work/reliability-pilot/`, and removes both stacks and their volumes. A passing result requires 6 of 6 studies in both runs, all expected correction-path export denials, deterministic agreement, and `unsupported clinical facts exported: 0`.

## Demo entrypoint

`make demo` prints the direct review URL after the stack becomes healthy. The API health endpoint is `http://localhost:8000/health`.

See `docs/demo-script.md` for the successful and blocked demo paths, `docs/reliability-pilot.md` for the retained six-study reliability summary, `docs/release-checklist.md` for retained release evidence, `docs/architecture.md` for system boundaries, and `docs/safety-case.md` for the invariant-to-control map.
