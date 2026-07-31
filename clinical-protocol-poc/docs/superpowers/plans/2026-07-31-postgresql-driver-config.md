# PostgreSQL Driver Configuration Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a clean `make app` startup use the installed Psycopg 3 driver consistently and prevent the sample configuration from regressing to the legacy driver.

**Architecture:** Keep the existing strict startup path and Psycopg 3 dependency unchanged. Align `.env.example` with the already-correct Compose, Alembic, and backend defaults, protect those checked-in settings with one focused contract test, and update the ignored local `.env` only to resume this machine's acceptance test.

**Tech Stack:** Docker Compose, PostgreSQL 16, SQLAlchemy, Alembic, Psycopg 3, pytest, FastAPI, Next.js

## Global Constraints

- Use `postgresql+psycopg://protocol_poc:protocol_poc@postgres:5432/protocol_poc` for local PostgreSQL configuration.
- Do not install `psycopg2`, rewrite database URLs at runtime, or add a fallback driver.
- Preserve strict startup failure for malformed URLs, unavailable databases, missing drivers, and failed migrations.
- Do not change APIs, database schemas, clinical workflows, UI behavior, dependency versions, or production configuration.
- Keep `.env` ignored and local; commit only `.env.example`, the regression test, and this approved planning documentation.

---

## File Structure

- Modify: `.env.example` — checked-in local configuration template copied by new users.
- Modify locally only: `.env` — ignored settings used for this machine's acceptance test.
- Modify: `backend/tests/unit/test_compose_contract.py` — contract test ensuring every checked-in local database URL selects Psycopg 3.

### Task 1: Align and verify the local PostgreSQL driver contract

**Files:**
- Modify: `.env.example:5`
- Modify locally only: `.env:5`
- Test: `backend/tests/unit/test_compose_contract.py`

**Interfaces:**
- Consumes: SQLAlchemy database URLs read from `.env.example`, `compose.yaml`, `backend/alembic.ini`, and `backend/src/protocol_poc/config.py`.
- Produces: a consistent checked-in Psycopg 3 local-development contract and a healthy Docker Compose startup.

- [ ] **Step 1: Replace the narrow Compose-only assertion with a failing cross-file contract test**

Update `test_compose_database_url_uses_installed_psycopg_driver` in `backend/tests/unit/test_compose_contract.py` to read every checked-in local database configuration:

```python
def test_local_database_urls_use_installed_psycopg_driver() -> None:
    root = Path(__file__).parents[3]
    expected_url = (
        "postgresql+psycopg://"
        "protocol_poc:protocol_poc@postgres:5432/protocol_poc"
    )
    configured_sources = {
        ".env.example": (root / ".env.example").read_text(),
        "compose.yaml": (root / "compose.yaml").read_text(),
        "backend/alembic.ini": (root / "backend" / "alembic.ini").read_text(),
        "backend/src/protocol_poc/config.py": (
            root / "backend" / "src" / "protocol_poc" / "config.py"
        ).read_text(),
    }

    for source_name, source_text in configured_sources.items():
        assert expected_url in source_text, source_name
        assert "postgresql://" not in source_text, source_name
```

- [ ] **Step 2: Run the contract test and confirm the existing sample configuration fails**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_compose_contract.py::test_local_database_urls_use_installed_psycopg_driver -v
```

Expected: FAIL naming `.env.example`, because it contains `postgresql://...` instead of `postgresql+psycopg://...`.

- [ ] **Step 3: Apply the minimal permanent and local configuration correction**

In both `.env.example` and the ignored `.env`, replace only the `DATABASE_URL` line with:

```dotenv
DATABASE_URL=postgresql+psycopg://protocol_poc:protocol_poc@postgres:5432/protocol_poc
```

Do not change Compose, Alembic, backend defaults, or dependencies; they already select Psycopg 3.

- [ ] **Step 4: Run the focused contract test and confirm it passes**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_compose_contract.py::test_local_database_urls_use_installed_psycopg_driver -v
```

Expected: `1 passed`.

- [ ] **Step 5: Run the full Compose contract test file**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_compose_contract.py -v
```

Expected: all tests in `test_compose_contract.py` pass with zero failures.

- [ ] **Step 6: Rebuild and start the local application**

From the project root, run:

```bash
make app
```

Expected: Compose reports PostgreSQL, MinIO, API, and web services healthy and prints `Clinical Protocol POC ready: http://127.0.0.1:3000`.

- [ ] **Step 7: Verify both application entry points and service state**

Run:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:3000
docker compose ps
```

Expected: the API returns a healthy response, the web request returns HTML, and all four Compose services are running with PostgreSQL, MinIO, API, and web marked healthy.

- [ ] **Step 8: Confirm the tracked change set is narrow**

Run:

```bash
git status --short
git diff --check
git diff -- .env.example backend/tests/unit/test_compose_contract.py
```

Expected: only `.env.example`, `backend/tests/unit/test_compose_contract.py`, and the already-committed design/plan documentation belong to this repair; `.env` remains ignored; `git diff --check` reports no errors.

- [ ] **Step 9: Commit the tested repair**

Run:

```bash
git add .env.example backend/tests/unit/test_compose_contract.py
git commit -m "fix: align local PostgreSQL driver configuration"
```

Expected: one commit containing the tracked configuration correction and its regression test, with no local `.env` included.
