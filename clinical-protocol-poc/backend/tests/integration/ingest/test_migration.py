from pathlib import Path
import re

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_migration_revision_identifiers_fit_alembic_version_column() -> None:
    revision_ids = []
    for path in Path("migrations/versions").glob("*.py"):
        match = re.search(r'^revision = "([^"]+)"$', path.read_text(), re.MULTILINE)
        assert match is not None, f"migration {path.name} is missing a revision identifier"
        revision_ids.append(match.group(1))
    assert all(len(revision) <= 32 for revision in revision_ids)


def test_files_migration_upgrade_constraints_and_downgrade(tmp_path: Path, monkeypatch: object) -> None:
    database = tmp_path / "migration.db"
    url = f"sqlite+pysqlite:///{database}"
    monkeypatch.setenv("DATABASE_URL", url)  # type: ignore[attr-defined]
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    inspector = inspect(create_engine(url))
    assert {"file_records", "file_versions", "source_evidence", "ingest_jobs"}.issubset(inspector.get_table_names())
    assert "export_artifacts" in inspector.get_table_names()
    assert "ck_export_artifact_filename" in {
        item["name"] for item in inspector.get_check_constraints("export_artifacts")
    }
    assert "uq_export_artifact_snapshot_filename" in {
        item["name"] for item in inspector.get_unique_constraints("export_artifacts")
    }
    assert {item["name"] for item in inspector.get_check_constraints("ingest_jobs")} == {"ck_ingest_job_role", "ck_ingest_job_status"}
    assert "uq_source_evidence_version_ordinal" in {item["name"] for item in inspector.get_unique_constraints("source_evidence")}
    assert "fk_evidence_version_tenant" in {item["name"] for item in inspector.get_foreign_keys("source_evidence")}
    assert "uq_passage_version_id_tenant" in {
        item["name"] for item in inspector.get_unique_constraints("passage_versions")
    }
    assert "uq_passage_study_section_tenant" in {
        item["name"] for item in inspector.get_unique_constraints("passages")
    }
    assert "processing_attempts" in inspector.get_table_names()
    attempt_indexes = {
        item["name"]: item for item in inspector.get_indexes("processing_attempts")
    }
    assert "uq_processing_attempt_active" in attempt_indexes
    assert attempt_indexes["uq_processing_attempt_active"]["unique"] == 1
    predicate = str(
        attempt_indexes["uq_processing_attempt_active"]["dialect_options"][
            "sqlite_where"
        ]
    )
    assert "pending" in predicate and "processing" in predicate
    assert "processing_attempt_id" in {
        item["name"] for item in inspector.get_columns("facts")
    }
    assert "confidence" in {
        item["name"] for item in inspector.get_columns("fact_versions")
    }
    assert "ck_fact_version_evidence_pair" in {
        item["name"] for item in inspector.get_check_constraints("fact_versions")
    }
    evidence_foreign_keys = {
        item["name"]: item for item in inspector.get_foreign_keys("fact_versions")
    }
    assert evidence_foreign_keys["fk_fact_version_evidence_tenant_version"][
        "constrained_columns"
    ] == ["source_evidence_id", "tenant_id", "source_evidence_version_id"]
    with create_engine(url).begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        triggers = {
            row[0]: row[1]
            for row in connection.execute(
                text(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type = 'trigger' AND tbl_name = 'processing_attempts'"
                )
            )
        }
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0012_passage_current_unique"
        )
    assert {
        "trg_processing_attempt_terminal_update",
        "trg_processing_attempt_delete",
    }.issubset(triggers)
    update_trigger = triggers["trg_processing_attempt_terminal_update"]
    assert "NEW.synopsis_version_id IS NOT OLD.synopsis_version_id" in update_trigger
    assert "NEW.extractor_version IS NOT OLD.extractor_version" in update_trigger
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO studies "
                "(id, tenant_id, name, version, lifecycle, created_at, updated_at) "
                "VALUES ('study-a', 'tenant-a', 'Study', 1, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO passages "
                "(id, tenant_id, study_id, section, status, current_version) VALUES "
                "('passage-a', 'tenant-a', 'study-a', 'study_design', 'draft', 1)"
            )
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO passages "
                    "(id, tenant_id, study_id, section, status, current_version) VALUES "
                    "('passage-b', 'tenant-a', 'study-a', 'study_design', 'draft', 1)"
                )
            )
    passage_version_indexes = {
        item["name"]: item for item in inspector.get_indexes("passage_versions")
    }
    assert passage_version_indexes["uq_passage_version_current"]["unique"] == 1
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO file_records (id, tenant_id, study_id, role, created_at) "
                "VALUES ('file-a', 'tenant-a', 'study-a', 'synopsis', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO file_versions "
                "(id, tenant_id, file_record_id, version, display_filename, checksum_sha256, "
                "size_bytes, content_type, storage_key, status, created_at) VALUES "
                "('version-a', 'tenant-a', 'file-a', 1, 'synopsis.docx', :checksum, "
                "1, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', "
                "'tenant/version-a.docx', 'succeeded', CURRENT_TIMESTAMP)"
            ),
            {"checksum": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO processing_attempts "
                "(id, tenant_id, study_id, synopsis_version_id, extractor_name, "
                "extractor_version, status, findings_json, started_at) VALUES "
                "('attempt-a', 'tenant-a', 'study-a', 'version-a', 'local-rules', "
                "'local-rules-v1', 'processing', '[]', CURRENT_TIMESTAMP)"
            )
        )
    with pytest.raises(IntegrityError, match="immutable"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE processing_attempts SET status = 'succeeded', "
                    "extractor_version = 'tampered' WHERE id = 'attempt-a'"
                )
            )
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE processing_attempts SET status = 'succeeded', "
                "completed_at = CURRENT_TIMESTAMP WHERE id = 'attempt-a'"
            )
        )
    with pytest.raises(IntegrityError, match="cannot be deleted"):
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM processing_attempts WHERE id = 'attempt-a'")
            )
    command.downgrade(config, "base")
    assert inspect(create_engine(url)).get_table_names() == ["alembic_version"]
