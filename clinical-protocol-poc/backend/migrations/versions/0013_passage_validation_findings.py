"""Persist deterministic validation findings on passage versions."""

import sqlalchemy as sa
from alembic import op


revision = "0013_passage_validation_findings"
down_revision = "0012_passage_current_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("passage_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "validation_findings",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.alter_column("validation_findings", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("passage_versions") as batch_op:
        batch_op.drop_column("validation_findings")
