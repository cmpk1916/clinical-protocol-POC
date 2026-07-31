.PHONY: bootstrap test lint typecheck evaluation e2e reliability-pilot app demo up down

E2E_PROJECT ?= protocol-poc-release-e2e
E2E_WEB_PORT ?= 3200
E2E_API_PORT ?= 8200
E2E_TESTS ?=
RELIABILITY_OUTPUT ?= work/reliability-pilot

bootstrap:
	cd backend && uv sync --all-groups --frozen
	cd frontend && pnpm install --frozen-lockfile

test:
	cd backend && .venv/bin/python -m pytest
	cd frontend && pnpm test

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && pnpm lint

typecheck:
	cd backend && .venv/bin/mypy src/protocol_poc
	cd frontend && pnpm typecheck

evaluation:
	cd backend && .venv/bin/python -m pytest tests/evaluation -v
	@echo "unsupported clinical facts exported: 0"

e2e:
	@set -e; \
	trap 'docker compose -p $(E2E_PROJECT) down --volumes >/dev/null 2>&1' EXIT; \
	APP_ENV=test LOCAL_TENANT_ID=synthetic-demo WEB_PORT=$(E2E_WEB_PORT) API_PORT=$(E2E_API_PORT) docker compose -p $(E2E_PROJECT) up --build -d --wait; \
	cd frontend; \
	E2E_WEB_URL=http://127.0.0.1:$(E2E_WEB_PORT) E2E_API_URL=http://127.0.0.1:$(E2E_API_PORT) pnpm exec playwright test $(E2E_TESTS)

reliability-pilot:
	@mkdir -p $(RELIABILITY_OUTPUT)
	@set -eu; \
	cleanup() { \
		docker compose -p protocol-poc-reliability-a down --volumes >/dev/null 2>&1 || true; \
		docker compose -p protocol-poc-reliability-b down --volumes >/dev/null 2>&1 || true; \
	}; \
	trap cleanup EXIT; \
	cleanup; \
	APP_ENV=test ENVIRONMENT=test ALLOW_INSECURE_IDENTITY_HEADERS=true API_PORT=8301 WEB_PORT=3301 \
		docker compose -p protocol-poc-reliability-a up --build -d --wait; \
	(cd backend && PYTHONPATH=src .venv/bin/python -m protocol_poc.reliability run \
		--base-url http://127.0.0.1:8301 --fixtures ../fixtures/reliability-pilot \
		--output ../$(RELIABILITY_OUTPUT) --run-label run-a); \
	docker compose -p protocol-poc-reliability-a down --volumes; \
	APP_ENV=test ENVIRONMENT=test ALLOW_INSECURE_IDENTITY_HEADERS=true API_PORT=8302 WEB_PORT=3302 \
		docker compose -p protocol-poc-reliability-b up --build -d --wait; \
	(cd backend && PYTHONPATH=src .venv/bin/python -m protocol_poc.reliability run \
		--base-url http://127.0.0.1:8302 --fixtures ../fixtures/reliability-pilot \
		--output ../$(RELIABILITY_OUTPUT) --run-label run-b); \
	docker compose -p protocol-poc-reliability-b down --volumes; \
	(cd backend && PYTHONPATH=src .venv/bin/python -m protocol_poc.reliability compare \
		--first ../$(RELIABILITY_OUTPUT)/run-a.json \
		--second ../$(RELIABILITY_OUTPUT)/run-b.json \
		--output ../$(RELIABILITY_OUTPUT))

app:
	APP_ENV=development docker compose up --build -d --wait
	@echo "Clinical Protocol POC ready: http://127.0.0.1:$${WEB_PORT:-3000}"

demo:
	APP_ENV=test docker compose up --build -d --wait
	curl --fail --silent --show-error -X POST http://127.0.0.1:$${API_PORT:-8000}/test/reset
	curl --fail --silent --show-error -X POST http://127.0.0.1:$${API_PORT:-8000}/test/studies/synthetic-phase-2/seed -H 'Content-Type: application/json' --data '{"scenario":"happy_path"}'
	@echo "Synthetic demo ready: http://127.0.0.1:$${WEB_PORT:-3000}/studies/synthetic-phase-2/review"

up:
	docker compose up --build

down:
	docker compose down
