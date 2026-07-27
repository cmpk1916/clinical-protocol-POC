"""Add governed guidance sources, releases, chunks, and reusable patterns."""

import sqlalchemy as sa
from alembic import op


revision = "0005_guidance"
down_revision = "0004_fact_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guidance_sources",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("id", "tenant_id", name="uq_guidance_source_id_tenant"),
    )
    op.create_index("ix_guidance_sources_tenant_id", "guidance_sources", ["tenant_id"])
    op.create_table(
        "guidance_releases",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("id", "tenant_id", name="uq_guidance_release_id_tenant"),
        sa.UniqueConstraint("source_id", "version", name="uq_guidance_release_version"),
        sa.ForeignKeyConstraint(["source_id", "tenant_id"], ["guidance_sources.id", "guidance_sources.tenant_id"], name="fk_guidance_release_source_tenant"),
        sa.CheckConstraint("state IN ('draft','approved','active','retired')", name="ck_guidance_release_state"),
    )
    op.create_table(
        "guidance_chunks",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("release_id", sa.String(length=128), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("applicability_tags", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["release_id", "tenant_id"], ["guidance_releases.id", "guidance_releases.tenant_id"], name="fk_guidance_chunk_release_tenant"),
        sa.UniqueConstraint("release_id", "content_hash", name="uq_guidance_chunk_release_hash"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_guidance_chunk_hash"),
    )
    op.create_table(
        "reusable_patterns",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("release_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["release_id", "tenant_id"], ["guidance_releases.id", "guidance_releases.tenant_id"], name="fk_pattern_release_tenant"),
    )


def downgrade() -> None:
    op.drop_table("reusable_patterns")
    op.drop_table("guidance_chunks")
    op.drop_table("guidance_releases")
    op.drop_index("ix_guidance_sources_tenant_id", table_name="guidance_sources")
    op.drop_table("guidance_sources")
