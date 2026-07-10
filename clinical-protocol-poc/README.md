# Clinical Protocol POC

This is a local proof of concept for drafting selected clinical-trial protocol sections using synthetic data only.

## Safety statement

No protocol produced by this POC is claimed clinically, regulatorily, submission, operationally, or production ready. It must not be used with confidential sponsor documents or production clinical data. The POC does not make autonomous scientific, medical, or regulatory decisions.

This is **not a validated system**. It performs **no live drafting research** and must not be represented as supporting a clinical, regulatory, or submission-readiness claim.

## Local setup

Prerequisites are Docker with Compose, `uv`, Node.js 22, and pnpm 11.7.0.

1. Copy `.env.example` to `.env`. The included values are local-only defaults and are not secrets suitable for another environment.
2. Run `make bootstrap` to install the exact backend and frontend dependencies recorded in `uv.lock` and `pnpm-lock.yaml`.
3. Run `make lint`, `make typecheck`, `make test`, `make evaluation`, and `make e2e` for release checks.
4. Run `make up` to start Postgres 16, MinIO, the API, and the web application. Run `make down` to stop them.

## Demo entrypoint

Open `http://localhost:3000` after the stack becomes healthy. The API health endpoint is `http://localhost:8000/health`.

See `docs/demo-script.md` for the successful and blocked demo paths, `docs/architecture.md` for system boundaries, and `docs/safety-case.md` for the invariant-to-control map.
