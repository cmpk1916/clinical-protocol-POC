"""Add governed guidance sources, releases, chunks, and reusable patterns."""

from alembic import op

from protocol_poc.guidance.models import GuidanceChunk, GuidanceRelease, GuidanceSource, ReusablePattern

revision = "0005_guidance"
down_revision = "0004_fact_review"
branch_labels = None
depends_on = None

TABLES = (GuidanceSource.__table__, GuidanceRelease.__table__, GuidanceChunk.__table__, ReusablePattern.__table__)


def upgrade() -> None:
    for table in TABLES:
        table.create(op.get_bind())


def downgrade() -> None:
    for table in reversed(TABLES):
        table.drop(op.get_bind())
