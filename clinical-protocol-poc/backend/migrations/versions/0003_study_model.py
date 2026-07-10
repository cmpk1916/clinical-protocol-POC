"""Create the tenant-scoped canonical study and fact model."""

from alembic import op

from protocol_poc.studies.models import (
    ArmRecord,
    EligibilityCriterionRecord,
    EndpointRecord,
    Fact,
    FactVersion,
    InterventionRecord,
    ObjectiveRecord,
    PopulationRecord,
    ScheduleConceptRecord,
    Study,
    TimepointRecord,
)

revision = "0003_study_model"
down_revision = "0002_files_evidence"
branch_labels = None
depends_on = None

TABLES = (
    Study.__table__,
    ObjectiveRecord.__table__,
    TimepointRecord.__table__,
    PopulationRecord.__table__,
    ArmRecord.__table__,
    InterventionRecord.__table__,
    EligibilityCriterionRecord.__table__,
    ScheduleConceptRecord.__table__,
    EndpointRecord.__table__,
    Fact.__table__,
    FactVersion.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        table.create(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind)
