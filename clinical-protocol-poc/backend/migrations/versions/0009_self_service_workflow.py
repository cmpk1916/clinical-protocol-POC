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


def downgrade() -> None:
    op.drop_index("ix_study_inputs_tenant_study", table_name="study_inputs")
    op.drop_table("study_inputs")
    with op.batch_alter_table("studies") as batch_op:
        batch_op.drop_constraint("ck_study_lifecycle", type_="check")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("lifecycle")
