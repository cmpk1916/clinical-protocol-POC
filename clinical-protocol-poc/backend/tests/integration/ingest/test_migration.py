from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_files_migration_upgrade_constraints_and_downgrade(tmp_path: Path, monkeypatch: object) -> None:
    database = tmp_path / "migration.db"
    url = f"sqlite+pysqlite:///{database}"
    monkeypatch.setenv("DATABASE_URL", url)  # type: ignore[attr-defined]
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    inspector = inspect(create_engine(url))
    assert {"file_records", "file_versions", "source_evidence", "ingest_jobs"}.issubset(inspector.get_table_names())
    assert {item["name"] for item in inspector.get_check_constraints("ingest_jobs")} == {"ck_ingest_job_role", "ck_ingest_job_status"}
    assert "uq_source_evidence_version_ordinal" in {item["name"] for item in inspector.get_unique_constraints("source_evidence")}
    assert "fk_evidence_version_tenant" in {item["name"] for item in inspector.get_foreign_keys("source_evidence")}
    command.downgrade(config, "base")
    assert inspect(create_engine(url)).get_table_names() == ["alembic_version"]
