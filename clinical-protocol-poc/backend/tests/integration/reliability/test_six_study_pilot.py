from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.db import Base
from protocol_poc.reliability.client import PilotClient
from protocol_poc.reliability.manifest import ExpectedBlocker, load_pilot_manifests
from protocol_poc.reliability.runner import PilotRunner


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[4] / "fixtures" / "reliability-pilot"
)


def test_all_six_self_service_journeys_recover_and_export_safely(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'pilot.db'}"
    )
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)

    with TestClient(app) as test_client:
        client = PilotClient(
            "http://testserver",
            "pilot-tenant",
            "pilot-runner",
            http_client=test_client,
        )
        result = PilotRunner(client, FIXTURE_ROOT).run(
            load_pilot_manifests(FIXTURE_ROOT)
        )

    get_settings.cache_clear()
    assert result.passed is True, [
        (study.study_key, [check for check in study.checks if not check.passed])
        for study in result.studies
        if not study.passed
    ]
    assert len(result.studies) == 6
    assert all(item.passed for item in result.studies)
    assert result.exported_unsupported_clinical_fact_count == 0
    assert sum(item.initial_export_denied for item in result.studies) == 3
    assert sum(bool(item.artifacts) for item in result.studies) == 6
    for study in result.studies:
        final_statuses = {
            check.name: check.actual
            for check in study.checks
            if check.name.endswith(".final_status")
        }
        assert final_statuses == {
            "passage.synopsis.final_status": "accepted",
            "passage.objectives_endpoints.final_status": "accepted",
            "passage.study_design.final_status": "accepted",
            "passage.eligibility.final_status": "accepted",
        }
    manifests = load_pilot_manifests(FIXTURE_ROOT)
    for manifest, study in zip(manifests, result.studies, strict=True):
        fact_check = next(check for check in study.checks if check.name == "facts")
        assert fact_check.expected == tuple(
            item.model_dump() for item in manifest.expected_facts
        )
    unsupported = next(
        study for study in result.studies
        if study.study_key == "unsupported-passage-edit"
    )
    denial = next(
        check for check in unsupported.checks if check.name == "initial_export"
    )
    assert denial.expected == (409, "EXPORT_BLOCKED")
    assert denial.actual == (409, "EXPORT_BLOCKED")


def test_fact_mismatch_fails_closed_before_review_or_export(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'pilot.db'}"
    )
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    standard = load_pilot_manifests(FIXTURE_ROOT)[0]
    wrong_fact = standard.expected_facts[0].model_copy(
        update={"value": {"kind": "string", "value": "WRONG-GOLD"}}
    )
    mismatched = standard.model_copy(
        update={"expected_facts": (wrong_fact, *standard.expected_facts[1:])}
    )

    with TestClient(app) as test_client:
        client = PilotClient(
            "http://testserver", "pilot-tenant", "pilot-runner", http_client=test_client
        )
        study = PilotRunner(client, FIXTURE_ROOT).run((mismatched,)).studies[0]
        remaining = client.get_review_queue(str(study.study_id))

    get_settings.cache_clear()
    assert study.passed is False
    assert study.artifacts == ()
    assert len(remaining["items"]) == len(standard.expected_facts)


def test_blocker_mismatch_fails_closed_and_later_study_still_runs(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'pilot.db'}"
    )
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    manifests = load_pilot_manifests(FIXTURE_ROOT)
    missing = manifests[3]
    wrong_blocker = ExpectedBlocker(
        code="SYNOPSIS_DOSE_MISSING",
        affected_area="wrong_area",
        next_action="upload_synopsis",
    )
    mismatched = missing.model_copy(update={"expected_blockers": (wrong_blocker,)})

    with TestClient(app) as test_client:
        client = PilotClient(
            "http://testserver", "pilot-tenant", "pilot-runner", http_client=test_client
        )
        result = PilotRunner(client, FIXTURE_ROOT).run((mismatched, manifests[0]))

    get_settings.cache_clear()
    assert result.studies[0].passed is False
    assert result.studies[0].artifacts == ()
    assert result.studies[1].passed is True


def test_passage_mismatch_fails_closed_before_acceptance_or_export(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'pilot.db'}"
    )
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    standard = load_pilot_manifests(FIXTURE_ROOT)[0]
    expected_passages = dict(standard.expected_passages)
    expected_passages["study_design"] = "Wrong gold passage."
    mismatched = standard.model_copy(update={"expected_passages": expected_passages})

    with TestClient(app) as test_client:
        client = PilotClient(
            "http://testserver", "pilot-tenant", "pilot-runner", http_client=test_client
        )
        study = PilotRunner(client, FIXTURE_ROOT).run((mismatched,)).studies[0]
        passages = client.list_passages(str(study.study_id))["passages"]

    get_settings.cache_clear()
    assert study.passed is False
    assert study.artifacts == ()
    assert {item["status"] for item in passages} == {"ready_for_review"}


def test_corrupted_downloaded_artifact_cannot_pass_the_pilot(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'pilot.db'}"
    )
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    standard = load_pilot_manifests(FIXTURE_ROOT)[0]

    with TestClient(app) as test_client:
        real_client = PilotClient(
            "http://testserver", "pilot-tenant", "pilot-runner", http_client=test_client
        )

        class CorruptingDownloads:
            def __getattr__(self, name: str) -> object:
                return getattr(real_client, name)

            def download_artifact(self, download_url: str) -> bytes:
                body = real_client.download_artifact(download_url)
                if b"Synthetic POC output only" in body:
                    return body.replace(b"Synthetic POC output only", b"Corrupted output only")
                return body

        study = PilotRunner(
            cast(PilotClient, CorruptingDownloads()), FIXTURE_ROOT
        ).run((standard,)).studies[0]

    get_settings.cache_clear()
    assert study.passed is False
    assert next(
        check for check in study.checks if check.name == "scorecard.disclaimer"
    ).passed is False
    assert next(
        check for check in study.checks if check.name == "artifact.scorecard.html.sha256"
    ).passed is False


def test_unsupported_passage_blocker_contract_mismatch_stops_recovery(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'pilot.db'}"
    )
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))  # type: ignore[attr-defined]
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")  # type: ignore[attr-defined]
    monkeypatch.setenv("ENVIRONMENT", "test")  # type: ignore[attr-defined]
    monkeypatch.setenv("APP_ENV", "test")  # type: ignore[attr-defined]
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    unsupported = load_pilot_manifests(FIXTURE_ROOT)[5]
    wrong_blocker = unsupported.expected_blockers[0].model_copy(
        update={"affected_area": "wrong_section"}
    )
    mismatched = unsupported.model_copy(
        update={"expected_blockers": (wrong_blocker,)}
    )

    with TestClient(app) as test_client:
        client = PilotClient(
            "http://testserver", "pilot-tenant", "pilot-runner", http_client=test_client
        )
        study = PilotRunner(client, FIXTURE_ROOT).run((mismatched,)).studies[0]
        passages = client.list_passages(str(study.study_id))["passages"]

    get_settings.cache_clear()
    blocked = next(item for item in passages if item["section"] == "study_design")
    assert study.passed is False
    assert study.artifacts == ()
    assert blocked["status"] == "blocked"
    blocker_check = next(
        check for check in study.checks if check.name == "passage.blocked_findings"
    )
    assert blocker_check.expected == (("UNSUPPORTED_DOSE", "wrong_section"),)
    assert blocker_check.actual == (("UNSUPPORTED_DOSE", "study_design"),)
