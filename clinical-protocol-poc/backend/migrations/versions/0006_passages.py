"""Add passage versions, claims, and support links."""

import sqlalchemy as sa
from alembic import op


revision = "0006_passages"
down_revision = "0005_guidance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passages",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("study_id", sa.String(length=128), nullable=False),
        sa.Column("section", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("invalidation_reason", sa.String(length=128)),
        sa.UniqueConstraint("id", "tenant_id", name="uq_passage_id_tenant"),
        sa.ForeignKeyConstraint(["study_id", "tenant_id"], ["studies.id", "studies.tenant_id"], name="fk_passage_study_tenant"),
        sa.CheckConstraint("section IN ('synopsis','objectives_endpoints','study_design','eligibility')", name="ck_passage_section"),
        sa.CheckConstraint("status IN ('draft','blocked','ready_for_review','accepted','rejected','stale')", name="ck_passage_status"),
    )
    op.create_table(
        "passage_versions",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("passage_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("placeholders", sa.JSON(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("passage_id", "version", name="uq_passage_version_number"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_passage_version_id_tenant"),
        sa.ForeignKeyConstraint(["passage_id", "tenant_id"], ["passages.id", "passages.tenant_id"], name="fk_passage_version_passage_tenant"),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("passage_version_id", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["passage_version_id", "tenant_id"], ["passage_versions.id", "passage_versions.tenant_id"], name="fk_claim_passage_version_tenant"),
    )
    op.create_table(
        "support_links",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("passage_version_id", sa.String(length=128), nullable=False),
        sa.Column("support_type", sa.String(length=16), nullable=False),
        sa.Column("support_id", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["passage_version_id", "tenant_id"], ["passage_versions.id", "passage_versions.tenant_id"], name="fk_support_passage_version_tenant"),
        sa.CheckConstraint("support_type IN ('fact','guidance')", name="ck_support_type"),
        sa.UniqueConstraint("passage_version_id", "support_type", "support_id", name="uq_support_link"),
    )


def downgrade() -> None:
    op.drop_table("support_links")
    op.drop_table("claims")
    op.drop_table("passage_versions")
    op.drop_table("passages")
