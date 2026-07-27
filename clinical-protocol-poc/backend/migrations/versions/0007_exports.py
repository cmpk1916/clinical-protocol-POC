"""Add immutable export snapshot records."""

import sqlalchemy as sa
from alembic import op


revision = "0007_exports"
down_revision = "0006_passages"
branch_labels = None
depends_on = None


def _snapshot_table(name: str, *columns: sa.Column[object]) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("snapshot_id", sa.String(length=128), nullable=False),
        *columns,
        sa.ForeignKeyConstraint(["snapshot_id"], ["export_snapshots.id"], name=f"fk_{name.removesuffix('s')}_snapshot"),
    )


def upgrade() -> None:
    op.create_table(
        "export_snapshots",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("study_id", sa.String(length=128), nullable=False),
        sa.Column("study_version", sa.Integer(), nullable=False),
        sa.Column("renderer_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_snapshots_tenant_id", "export_snapshots", ["tenant_id"])
    _snapshot_table(
        "snapshot_facts",
        sa.Column("source_fact_id", sa.String(length=128), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
    )
    _snapshot_table(
        "snapshot_passages",
        sa.Column("source_passage_id", sa.String(length=128), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("review_state", sa.String(length=32), nullable=False),
    )
    _snapshot_table(
        "snapshot_guidance",
        sa.Column("guidance_id", sa.String(length=128), nullable=False),
        sa.Column("release_id", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
    )
    _snapshot_table(
        "snapshot_templates",
        sa.Column("template_version_id", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
    )
    _snapshot_table(
        "snapshot_findings",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
    )


def downgrade() -> None:
    for table in ("snapshot_findings", "snapshot_templates", "snapshot_guidance", "snapshot_passages", "snapshot_facts"):
        op.drop_table(table)
    op.drop_index("ix_export_snapshots_tenant_id", table_name="export_snapshots")
    op.drop_table("export_snapshots")
