"""Add immutable export snapshot records."""

from alembic import op

from protocol_poc.export.models import ExportSnapshot, SnapshotFact, SnapshotFinding, SnapshotGuidance, SnapshotPassage, SnapshotTemplate

revision = "0007_exports"
down_revision = "0006_passages"
branch_labels = None
depends_on = None

TABLES = (ExportSnapshot.__table__, SnapshotFact.__table__, SnapshotPassage.__table__, SnapshotGuidance.__table__, SnapshotTemplate.__table__, SnapshotFinding.__table__)


def upgrade() -> None:
    for table in TABLES:
        table.create(op.get_bind())


def downgrade() -> None:
    for table in reversed(TABLES):
        table.drop(op.get_bind())
