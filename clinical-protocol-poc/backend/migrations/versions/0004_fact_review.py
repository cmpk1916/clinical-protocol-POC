"""Add persisted conflict resolution records for guided review."""

import sqlalchemy as sa
from alembic import op


revision = "0004_fact_review"
down_revision = "0003_study_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_conflicts",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("fact_id", sa.String(length=128), nullable=False),
        sa.Column("conflicting_fact_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resolution", sa.String(length=512)),
        sa.Column("resolved_by", sa.String(length=128)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["fact_id", "tenant_id"],
            ["facts.id", "facts.tenant_id"],
            name="fk_conflict_fact_tenant",
        ),
        sa.CheckConstraint("status IN ('open','resolved')", name="ck_fact_conflict_status"),
    )


def downgrade() -> None:
    op.drop_table("fact_conflicts")
