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


def test_normal_app_defaults_disable_test_routes_while_demo_and_e2e_enable_them() -> None:
    root = Path(__file__).parents[3]
    compose = (root / "compose.yaml").read_text()
    example = (root / ".env.example").read_text()
    makefile = (root / "Makefile").read_text()
    e2e_recipe = makefile.partition("\ne2e:")[2].partition("\napp:")[0]
    app_recipe = makefile.partition("\napp:")[2].partition("\ndemo:")[0]
    demo_recipe = makefile.partition("\ndemo:")[2].partition("\nup:")[0]

    assert "APP_ENV: ${APP_ENV:-development}" in compose
    assert "\nAPP_ENV=development\n" in f"\n{example}\n"
    assert "APP_ENV=development" in app_recipe
    assert "APP_ENV=test" in e2e_recipe
    assert "APP_ENV=test" in demo_recipe


def test_api_storage_uses_a_named_persistent_volume_at_the_configured_path() -> None:
    compose = (Path(__file__).parents[3] / "compose.yaml").read_text()

    assert "LOCAL_STORAGE_PATH: /var/lib/protocol-poc/storage" in compose
    assert "protocol-storage:/var/lib/protocol-poc/storage" in compose
    assert "\n  protocol-storage:\n" in compose


def test_e2e_stack_uses_the_seeded_journeys_tenant() -> None:
    makefile = (Path(__file__).parents[3] / "Makefile").read_text()
    e2e_recipe = makefile.partition("\ne2e:")[2].partition("\napp:")[0]

    assert "LOCAL_TENANT_ID=synthetic-demo" in e2e_recipe


def test_e2e_target_can_run_a_selected_playwright_spec() -> None:
    makefile = (Path(__file__).parents[3] / "Makefile").read_text()
    e2e_recipe = makefile.partition("\ne2e:")[2].partition("\napp:")[0]

    assert "E2E_TESTS ?=" in makefile
    assert "pnpm exec playwright test $(E2E_TESTS)" in e2e_recipe
