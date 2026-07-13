"""Add immutable export artifact records."""

from alembic import op

from protocol_poc.export.models import ExportArtifactRecord

revision = "0008_export_artifacts"
down_revision = "0007_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ExportArtifactRecord.__table__.create(op.get_bind())


def downgrade() -> None:
    ExportArtifactRecord.__table__.drop(op.get_bind())
