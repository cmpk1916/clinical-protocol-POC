"""Require one current immutable version for each governed passage."""

import sqlalchemy as sa
from alembic import op


revision = "0012_passage_current_version_unique"
down_revision = "0011_passage_section_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT passage_id FROM passage_versions WHERE is_current "
            "GROUP BY passage_id HAVING COUNT(*) > 1"
        )
    ).first()
    if duplicates is not None:
        raise RuntimeError("cannot enforce one current passage version while duplicates exist")
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("passage_versions")}
    if "uq_passage_version_current" not in indexes:
        op.create_index(
            "uq_passage_version_current", "passage_versions", ["passage_id"],
            unique=True,
            sqlite_where=sa.text("is_current = 1"),
            postgresql_where=sa.text("is_current"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("passage_versions")}
    if "uq_passage_version_current" in indexes:
        op.drop_index("uq_passage_version_current", table_name="passage_versions")
