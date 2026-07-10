"""Add passage versions, claims, and support links."""

from alembic import op

from protocol_poc.drafting.models import Claim, Passage, PassageVersion, SupportLink

revision = "0006_passages"
down_revision = "0005_guidance"
branch_labels = None
depends_on = None

TABLES = (Passage.__table__, PassageVersion.__table__, Claim.__table__, SupportLink.__table__)


def upgrade() -> None:
    for table in TABLES:
        table.create(op.get_bind())


def downgrade() -> None:
    for table in reversed(TABLES):
        table.drop(op.get_bind())
