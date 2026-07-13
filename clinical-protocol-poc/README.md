# Clinical Protocol POC

This is a local proof of concept for drafting selected clinical-trial protocol sections using synthetic data only.

## Safety statement

No protocol produced by this POC is claimed clinically, regulatorily, submission, operationally, or production ready. It must not be used with confidential sponsor documents or production clinical data. The POC does not make autonomous scientific, medical, or regulatory decisions.

This is **not a validated system**. It performs **no live drafting research** and must not be represented as supporting a clinical, regulatory, or submission-readiness claim.

## Test it yourself

For the application demo, the only prerequisites are Docker with Compose, `make`, and `curl`.

1. Copy `.env.example` to `.env`. The included values are local-only defaults and are not secrets suitable for another environment.
2. Run `make demo`. This builds the application, applies database migrations, waits for every service to become healthy, resets disposable local state, and seeds the synthetic happy-path study.
3. Open `http://localhost:3000/studies/synthetic-phase-2/review`.
4. Approve the synthetic critical dose fact and confirm it explicitly.
5. Open `/studies/synthetic-phase-2/draft`, review and accept the passage, then select **Create export**.
6. Download `protocol.docx`, `traceability.csv`, and `scorecard.html`. Confirm that all three rows show the same snapshot ID and that each row has its own SHA-256 digest.
7. Run `make down` when finished. Add `--volumes` to the Compose command if you also want to remove disposable database and object-storage data.

This workflow tests a synthetic proof of concept. It is not system validation and does not establish clinical, regulatory, operational, production, or submission readiness.

## Development checks

Development also requires `uv`, Node.js 22, and pnpm 11.7.0. Run `make bootstrap` to install the locked dependencies, then run `make lint`, `make typecheck`, `make test`, `make evaluation`, and `make e2e`.

## Demo entrypoint

`make demo` prints the direct review URL after the stack becomes healthy. The API health endpoint is `http://localhost:8000/health`.

See `docs/demo-script.md` for the successful and blocked demo paths, `docs/release-checklist.md` for retained release evidence, `docs/architecture.md` for system boundaries, and `docs/safety-case.md` for the invariant-to-control map.
