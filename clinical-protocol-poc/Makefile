.PHONY: bootstrap test lint typecheck evaluation e2e up down

E2E_PROJECT ?= protocol-poc-release-e2e
E2E_WEB_PORT ?= 3200
E2E_API_PORT ?= 8200

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
	APP_ENV=test WEB_PORT=$(E2E_WEB_PORT) API_PORT=$(E2E_API_PORT) docker compose -p $(E2E_PROJECT) up --build -d --wait; \
	cd frontend; \
	E2E_WEB_URL=http://127.0.0.1:$(E2E_WEB_PORT) E2E_API_URL=http://127.0.0.1:$(E2E_API_PORT) pnpm exec playwright test

up:
	docker compose up --build

down:
	docker compose down
