from pathlib import Path


def test_compose_database_url_uses_installed_psycopg_driver() -> None:
    compose = (Path(__file__).parents[3] / "compose.yaml").read_text()
    assert "postgresql+psycopg://protocol_poc:protocol_poc@postgres:5432/protocol_poc" in compose


def test_frontend_runner_keeps_pnpm_build_policy() -> None:
    dockerfile = (Path(__file__).parents[3] / "frontend" / "Dockerfile").read_text()
    assert "COPY --from=builder /app/pnpm-workspace.yaml ./pnpm-workspace.yaml" in dockerfile


def test_web_healthcheck_uses_ipv4_for_ipv4_bound_server() -> None:
    compose = (Path(__file__).parents[3] / "compose.yaml").read_text()
    assert "http://127.0.0.1:3000" in compose


def test_api_container_applies_database_migrations_before_startup() -> None:
    dockerfile = (Path(__file__).parents[3] / "backend" / "Dockerfile").read_text()
    assert "COPY alembic.ini" in dockerfile
    assert "COPY migrations" in dockerfile
    assert "alembic upgrade head" in dockerfile


def test_makefile_has_one_command_synthetic_demo_setup() -> None:
    makefile = (Path(__file__).parents[3] / "Makefile").read_text()
    assert "demo:" in makefile
    assert "/test/reset" in makefile
    assert "/test/studies/synthetic-phase-2/seed" in makefile
    assert '"scenario":"happy_path"' in makefile
