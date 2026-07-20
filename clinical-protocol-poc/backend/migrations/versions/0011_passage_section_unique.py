"""Enforce one governed passage for each study section."""

import sqlalchemy as sa
from alembic import op


revision = "0011_passage_section_unique"
down_revision = "0010_processing_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT tenant_id, study_id, section FROM passages "
            "GROUP BY tenant_id, study_id, section HAVING COUNT(*) > 1"
        )
    ).first()
    if duplicates is not None:
        raise RuntimeError("cannot enforce governed passage uniqueness while duplicate passages exist")
    unique_names = {item["name"] for item in sa.inspect(bind).get_unique_constraints("passages")}
    if "uq_passage_study_section_tenant" not in unique_names:
        with op.batch_alter_table("passages") as batch_op:
            batch_op.create_unique_constraint(
                "uq_passage_study_section_tenant", ["tenant_id", "study_id", "section"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    unique_names = {item["name"] for item in sa.inspect(bind).get_unique_constraints("passages")}
    if "uq_passage_study_section_tenant" in unique_names:
        with op.batch_alter_table("passages") as batch_op:
            batch_op.drop_constraint("uq_passage_study_section_tenant", type_="unique")
