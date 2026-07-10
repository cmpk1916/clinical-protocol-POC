"""Create tenant-scoped versioned files, evidence, and ingest jobs."""

from alembic import op
import sqlalchemy as sa

revision = "0002_files_evidence"
down_revision = "0001_tenant_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_records",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("study_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "study_id", "role", name="uq_file_record_identity"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_file_record_id_tenant"),
        sa.CheckConstraint("role IN ('synopsis', 'template')", name="ck_file_record_role"),
    )
    op.create_index("ix_file_records_tenant_id", "file_records", ["tenant_id"])
    op.create_table(
        "file_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("file_record_id", sa.String(26), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("display_filename", sa.String(255), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("file_record_id", "version", name="uq_file_version_number"),
        sa.UniqueConstraint("file_record_id", "checksum_sha256", name="uq_file_version_checksum"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_file_version_id_tenant"),
        sa.ForeignKeyConstraint(["file_record_id", "tenant_id"], ["file_records.id", "file_records.tenant_id"], name="fk_file_version_record_tenant"),
        sa.CheckConstraint("status IN ('succeeded')", name="ck_file_version_status"),
        sa.CheckConstraint("version > 0", name="ck_file_version_positive"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_file_version_size"),
        sa.CheckConstraint("length(checksum_sha256) = 64 AND lower(checksum_sha256) = checksum_sha256", name="ck_file_version_checksum_format"),
    )
    op.create_index("ix_file_versions_tenant_record", "file_versions", ["tenant_id", "file_record_id"])
    op.create_table(
        "source_evidence",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("file_version_id", sa.String(26), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("location_json", sa.JSON, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("file_version_id", "ordinal", name="uq_source_evidence_version_ordinal"),
        sa.ForeignKeyConstraint(["file_version_id", "tenant_id"], ["file_versions.id", "file_versions.tenant_id"], name="fk_evidence_version_tenant"),
        sa.CheckConstraint("ordinal >= 0", name="ck_source_evidence_ordinal"),
        sa.CheckConstraint("length(text_sha256) = 64 AND lower(text_sha256) = text_sha256", name="ck_source_evidence_checksum_format"),
    )
    op.create_index("ix_source_evidence_tenant_version", "source_evidence", ["tenant_id", "file_version_id"])
    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("study_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("file_version_id", sa.String(26)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["file_version_id", "tenant_id"], ["file_versions.id", "file_versions.tenant_id"], name="fk_ingest_job_version_tenant"),
        sa.CheckConstraint("role IN ('synopsis', 'template')", name="ck_ingest_job_role"),
        sa.CheckConstraint("status IN ('pending', 'processing', 'succeeded', 'failed')", name="ck_ingest_job_status"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_ingest_job_id_tenant"),
    )
    op.create_index("ix_ingest_jobs_tenant_study", "ingest_jobs", ["tenant_id", "study_id"])
    op.create_table(
        "cleanup_tasks",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("ingest_job_id", sa.String(26), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ingest_job_id", "tenant_id"], ["ingest_jobs.id", "ingest_jobs.tenant_id"], name="fk_cleanup_job_tenant"),
        sa.CheckConstraint("status IN ('pending', 'succeeded')", name="ck_cleanup_task_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_cleanup_task_attempts"),
        sa.CheckConstraint("length(checksum_sha256) = 64 AND lower(checksum_sha256) = checksum_sha256", name="ck_cleanup_task_checksum_format"),
    )
    op.create_index("ix_cleanup_tasks_tenant_status", "cleanup_tasks", ["tenant_id", "status"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION deny_file_version_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'file versions are immutable'; END; $$ LANGUAGE plpgsql""")
        op.execute("""CREATE TRIGGER file_versions_immutable BEFORE UPDATE OR DELETE ON file_versions FOR EACH ROW EXECUTE FUNCTION deny_file_version_mutation()""")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS file_versions_immutable ON file_versions")
        op.execute("DROP FUNCTION IF EXISTS deny_file_version_mutation()")
    op.drop_index("ix_cleanup_tasks_tenant_status", table_name="cleanup_tasks")
    op.drop_table("cleanup_tasks")
    op.drop_index("ix_ingest_jobs_tenant_study", table_name="ingest_jobs")
    op.drop_table("ingest_jobs")
    op.drop_index("ix_source_evidence_tenant_version", table_name="source_evidence")
    op.drop_table("source_evidence")
    op.drop_index("ix_file_versions_tenant_record", table_name="file_versions")
    op.drop_table("file_versions")
    op.drop_index("ix_file_records_tenant_id", table_name="file_records")
    op.drop_table("file_records")
