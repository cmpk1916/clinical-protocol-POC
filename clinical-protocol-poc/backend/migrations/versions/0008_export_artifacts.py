"""Add immutable export artifact records."""

import sqlalchemy as sa
from alembic import op


revision = "0008_export_artifacts"
down_revision = "0007_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_artifacts",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("filename", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("renderer_version", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_hex", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["export_snapshots.id"], name="fk_export_artifact_snapshot"),
        sa.UniqueConstraint("tenant_id", "snapshot_id", "filename", name="uq_export_artifact_snapshot_filename"),
        sa.UniqueConstraint("storage_key", name="uq_export_artifact_storage_key"),
        sa.CheckConstraint("filename IN ('protocol.docx','traceability.csv','scorecard.html')", name="ck_export_artifact_filename"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_export_artifact_size"),
        sa.CheckConstraint("length(sha256_hex) = 64 AND lower(sha256_hex) = sha256_hex", name="ck_export_artifact_sha256"),
    )


def downgrade() -> None:
    op.drop_table("export_artifacts")
