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


def downgrade() -> None:
    with op.batch_alter_table("studies") as batch_op:
        batch_op.drop_constraint("ck_study_lifecycle", type_="check")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("lifecycle")
