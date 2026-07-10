"""Add persisted conflict resolution records for guided review."""

from alembic import op

from protocol_poc.review.conflicts import FactConflict

revision = "0004_fact_review"
down_revision = "0003_study_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    FactConflict.__table__.create(op.get_bind())


def downgrade() -> None:
    FactConflict.__table__.drop(op.get_bind())
