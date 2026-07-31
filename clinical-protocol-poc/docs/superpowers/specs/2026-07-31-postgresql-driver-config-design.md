# PostgreSQL Driver Configuration Repair

## Context

The clean local startup path copies `.env.example` to `.env` and runs `make app`. The sample environment currently uses a `postgresql://` SQLAlchemy URL, which selects the legacy `psycopg2` driver. The backend intentionally installs and configures Psycopg 3 through the `postgresql+psycopg://` dialect. As a result, a clean startup builds successfully but the API exits while Alembic imports the unavailable `psycopg2` package.

## Decision

Use the existing Psycopg 3 configuration consistently. Change the sample and local development database URL to:

```text
postgresql+psycopg://protocol_poc:protocol_poc@postgres:5432/protocol_poc
```

Do not install `psycopg2`, rewrite URLs at runtime, or add a fallback driver. Invalid external configuration must continue to fail explicitly.

## Scope

- Update the tracked `.env.example` database URL.
- Update the ignored local `.env` database URL so the acceptance test can continue.
- Extend the existing Compose configuration contract test to confirm that `.env.example`, `compose.yaml`, `backend/alembic.ini`, and the backend default all select `postgresql+psycopg`.
- Rebuild and start the local stack, then verify the API health endpoint and web home screen.

No API behavior, database schema, clinical workflow, user interface, dependency version, or production configuration changes are included.

## Runtime Flow

1. A user copies `.env.example` to `.env`.
2. Compose passes the explicit Psycopg 3 URL to the API container.
3. Alembic uses Psycopg 3 to apply migrations.
4. The API starts and reports healthy.
5. The web application starts after the API health check succeeds.

## Error Handling

Startup remains strict. A missing driver, malformed URL, unavailable database, or failed migration stops the API and prevents the web service from being reported as ready. The repair removes only the known driver-name inconsistency; it does not conceal future configuration errors.

## Testing and Acceptance Criteria

- A regression test fails if any checked-in local-development database URL selects the legacy `psycopg2` dialect or diverges from `postgresql+psycopg`.
- The targeted configuration contract test passes.
- `make app` completes with all Compose services healthy.
- `http://localhost:8000/health` returns a healthy response.
- `http://localhost:3000` returns the application home screen.
- The Git working tree contains only the intended tracked repair files before commit.
