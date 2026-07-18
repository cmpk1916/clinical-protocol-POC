"""Add self-service study lifecycle fields."""

import sqlalchemy as sa
from alembic import op


revision = "0009_self_service_workflow"
down_revision = "0008_export_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("studies")}
    if "lifecycle" not in column_names:
        op.add_column(
            "studies",
            sa.Column(
                "lifecycle",
                sa.String(length=16),
                nullable=False,
                server_default="active",
            ),
        )
    if "updated_at" not in column_names:
        op.add_column(
            "studies",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    if "archived_at" not in column_names:
        op.add_column("studies", sa.Column("archived_at", sa.DateTime(timezone=True)))
    check_names = {
        constraint["name"] for constraint in inspector.get_check_constraints("studies")
    }
    if "ck_study_lifecycle" not in check_names:
        with op.batch_alter_table("studies") as batch_op:
            batch_op.create_check_constraint(
                "ck_study_lifecycle", "lifecycle IN ('active','archived')"
            )
    if "study_inputs" not in inspector.get_table_names():
        op.create_table(
            "study_inputs",
            sa.Column("id", sa.String(length=26), nullable=False),
            sa.Column("tenant_id", sa.String(length=128), nullable=False),
            sa.Column("study_id", sa.String(length=128), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("current_file_version_id", sa.String(length=26), nullable=False),
            sa.Column("conformance_status", sa.String(length=16), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "role IN ('synopsis', 'template')", name="ck_study_input_role"
            ),
            sa.CheckConstraint(
                "conformance_status IN ('conforming')",
                name="ck_study_input_conformance_status",
            ),
            sa.CheckConstraint(
                "revision > 0", name="ck_study_input_revision_positive"
            ),
            sa.ForeignKeyConstraint(
                ["study_id", "tenant_id"],
                ["studies.id", "studies.tenant_id"],
                name="fk_study_input_study_tenant",
            ),
            sa.ForeignKeyConstraint(
                ["current_file_version_id", "tenant_id"],
                ["file_versions.id", "file_versions.tenant_id"],
                name="fk_study_input_version_tenant",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "study_id", "role", name="uq_study_input_role"
            ),
            sa.UniqueConstraint("id", "tenant_id", name="uq_study_input_id_tenant"),
        )
        op.create_index(
            "ix_study_inputs_tenant_study",
            "study_inputs",
            ["tenant_id", "study_id"],
        )
    inspector = sa.inspect(bind)
    if "processing_attempts" not in inspector.get_table_names():
        op.create_table(
            "processing_attempts",
            sa.Column("id", sa.String(length=128), nullable=False),
            sa.Column("tenant_id", sa.String(length=128), nullable=False),
            sa.Column("study_id", sa.String(length=128), nullable=False),
            sa.Column("synopsis_version_id", sa.String(length=26), nullable=False),
            sa.Column("extractor_name", sa.String(length=64), nullable=False),
            sa.Column("extractor_version", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("error_code", sa.String(length=64)),
            sa.Column("findings_json", sa.JSON(), nullable=False),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint(
                "status IN ('pending','processing','succeeded','failed')",
                name="ck_processing_attempt_status",
            ),
            sa.ForeignKeyConstraint(
                ["study_id", "tenant_id"],
                ["studies.id", "studies.tenant_id"],
                name="fk_processing_attempt_study_tenant",
            ),
            sa.ForeignKeyConstraint(
                ["synopsis_version_id", "tenant_id"],
                ["file_versions.id", "file_versions.tenant_id"],
                name="fk_processing_attempt_version_tenant",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "id", "tenant_id", name="uq_processing_attempt_id_tenant"
            ),
        )
        op.create_index(
            "uq_processing_attempt_active",
            "processing_attempts",
            ["tenant_id", "study_id", "synopsis_version_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('pending','processing')"),
            sqlite_where=sa.text("status IN ('pending','processing')"),
        )
    fact_columns = {column["name"] for column in inspector.get_columns("facts")}
    with op.batch_alter_table("facts") as batch_op:
        if "processing_attempt_id" not in fact_columns:
            batch_op.add_column(
                sa.Column("processing_attempt_id", sa.String(length=128))
            )
            batch_op.create_foreign_key(
                "fk_fact_processing_attempt_tenant",
                "processing_attempts",
                ["processing_attempt_id", "tenant_id"],
                ["id", "tenant_id"],
            )
    fact_version_columns = {
        column["name"] for column in inspector.get_columns("fact_versions")
    }
    if "confidence" not in fact_version_columns:
        op.add_column("fact_versions", sa.Column("confidence", sa.Float()))


def downgrade() -> None:
    op.drop_column("fact_versions", "confidence")
    with op.batch_alter_table("facts") as batch_op:
        batch_op.drop_constraint(
            "fk_fact_processing_attempt_tenant", type_="foreignkey"
        )
        batch_op.drop_column("processing_attempt_id")
    op.drop_index(
        "uq_processing_attempt_active", table_name="processing_attempts"
    )
    op.drop_table("processing_attempts")
    op.drop_index("ix_study_inputs_tenant_study", table_name="study_inputs")
    op.drop_table("study_inputs")
    with op.batch_alter_table("studies") as batch_op:
        batch_op.drop_constraint("ck_study_lifecycle", type_="check")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("lifecycle")
