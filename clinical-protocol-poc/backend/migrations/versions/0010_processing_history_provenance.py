"""Protect processing history and bind facts to exact evidence versions."""

import sqlalchemy as sa
from alembic import op


revision = "0010_processing_provenance"
down_revision = "0009_self_service_workflow"
branch_labels = None
depends_on = None


def _create_processing_history_triggers() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_processing_attempt_terminal_update
            BEFORE UPDATE ON processing_attempts
            WHEN OLD.status IN ('succeeded','failed')
              OR NOT (
                (OLD.status = 'pending' AND NEW.status IN ('processing','failed'))
                OR (OLD.status = 'processing' AND NEW.status IN ('succeeded','failed'))
              )
              OR NEW.id IS NOT OLD.id
              OR NEW.tenant_id IS NOT OLD.tenant_id
              OR NEW.study_id IS NOT OLD.study_id
              OR NEW.synopsis_version_id IS NOT OLD.synopsis_version_id
              OR NEW.extractor_name IS NOT OLD.extractor_name
              OR NEW.extractor_version IS NOT OLD.extractor_version
              OR NEW.started_at IS NOT OLD.started_at
            BEGIN
              SELECT RAISE(ABORT, 'processing attempt history is immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_processing_attempt_delete
            BEFORE DELETE ON processing_attempts
            BEGIN
              SELECT RAISE(ABORT, 'processing attempts cannot be deleted');
            END
            """
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION protect_processing_attempt_history()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'processing attempts cannot be deleted';
              END IF;
              IF OLD.status IN ('succeeded','failed')
                 OR NOT (
                   (OLD.status = 'pending' AND NEW.status IN ('processing','failed'))
                   OR (OLD.status = 'processing' AND NEW.status IN ('succeeded','failed'))
                 )
                 OR NEW.id IS DISTINCT FROM OLD.id
                 OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                 OR NEW.study_id IS DISTINCT FROM OLD.study_id
                 OR NEW.synopsis_version_id IS DISTINCT FROM OLD.synopsis_version_id
                 OR NEW.extractor_name IS DISTINCT FROM OLD.extractor_name
                 OR NEW.extractor_version IS DISTINCT FROM OLD.extractor_version
                 OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN
                RAISE EXCEPTION 'processing attempt history is immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_processing_attempt_history
            BEFORE UPDATE OR DELETE ON processing_attempts
            FOR EACH ROW EXECUTE FUNCTION protect_processing_attempt_history()
            """
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    evidence_unique_names = {
        item["name"] for item in inspector.get_unique_constraints("source_evidence")
    }
    if "uq_source_evidence_id_tenant_version" not in evidence_unique_names:
        with op.batch_alter_table("source_evidence") as batch_op:
            batch_op.create_unique_constraint(
                "uq_source_evidence_id_tenant_version",
                ["id", "tenant_id", "file_version_id"],
            )
    fact_version_columns = {
        item["name"] for item in inspector.get_columns("fact_versions")
    }
    if "source_evidence_version_id" not in fact_version_columns:
        op.add_column(
            "fact_versions",
            sa.Column("source_evidence_version_id", sa.String(length=26)),
        )
    op.execute(
        """
        UPDATE fact_versions
        SET source_evidence_version_id = (
          SELECT source_evidence.file_version_id
          FROM source_evidence
          WHERE source_evidence.id = fact_versions.source_evidence_id
            AND source_evidence.tenant_id = fact_versions.tenant_id
        )
        WHERE source_evidence_id IS NOT NULL
        """
    )
    inspector = sa.inspect(bind)
    fact_check_names = {
        item["name"] for item in inspector.get_check_constraints("fact_versions")
    }
    fact_foreign_key_names = {
        item["name"] for item in inspector.get_foreign_keys("fact_versions")
    }
    if (
        "ck_fact_version_evidence_pair" not in fact_check_names
        or "fk_fact_version_evidence_tenant_version" not in fact_foreign_key_names
    ):
        with op.batch_alter_table("fact_versions") as batch_op:
            if "ck_fact_version_evidence_pair" not in fact_check_names:
                batch_op.create_check_constraint(
                    "ck_fact_version_evidence_pair",
                    "(source_evidence_id IS NULL AND source_evidence_version_id IS NULL) "
                    "OR (source_evidence_id IS NOT NULL AND source_evidence_version_id IS NOT NULL)",
                )
            if "fk_fact_version_evidence_tenant_version" not in fact_foreign_key_names:
                batch_op.create_foreign_key(
                    "fk_fact_version_evidence_tenant_version",
                    "source_evidence",
                    ["source_evidence_id", "tenant_id", "source_evidence_version_id"],
                    ["id", "tenant_id", "file_version_id"],
                )
    _create_processing_history_triggers()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER trg_processing_attempt_delete")
        op.execute("DROP TRIGGER trg_processing_attempt_terminal_update")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_processing_attempt_history ON processing_attempts")
        op.execute("DROP FUNCTION protect_processing_attempt_history()")
    with op.batch_alter_table("fact_versions") as batch_op:
        batch_op.drop_constraint(
            "fk_fact_version_evidence_tenant_version", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "ck_fact_version_evidence_pair", type_="check"
        )
        batch_op.drop_column("source_evidence_version_id")
    with op.batch_alter_table("source_evidence") as batch_op:
        batch_op.drop_constraint(
            "uq_source_evidence_id_tenant_version", type_="unique"
        )
