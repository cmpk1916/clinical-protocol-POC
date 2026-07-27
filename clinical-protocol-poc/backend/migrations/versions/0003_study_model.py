"""Create the tenant-scoped canonical study and fact model."""

import sqlalchemy as sa
from alembic import op


revision = "0003_study_model"
down_revision = "0002_files_evidence"
branch_labels = None
depends_on = None


# This migration intentionally owns a fixed historical schema. Importing ORM
# metadata here would let fields added by later revisions leak into a fresh
# database upgrade (notably 0009 processing history).
metadata = sa.MetaData()

studies = sa.Table(
    "studies",
    metadata,
    sa.Column("id", sa.String(length=128), primary_key=True),
    sa.Column("tenant_id", sa.String(length=128), nullable=False, index=True),
    sa.Column("name", sa.String(length=255), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("id", "tenant_id", name="uq_study_id_tenant"),
)


def _study_entity(name: str, constraint_name: str) -> sa.Table:
    return sa.Table(
        name,
        metadata,
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("study_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("id", "tenant_id", name=f"uq_{constraint_name}_id_tenant"),
        sa.ForeignKeyConstraint(
            ["study_id", "tenant_id"],
            ["studies.id", "studies.tenant_id"],
            name=f"fk_{constraint_name}_study_tenant",
        ),
    )


objectives = _study_entity("objectives", "objective")
timepoints = _study_entity("timepoints", "timepoint")
populations = _study_entity("populations", "population")
arms = _study_entity("arms", "arm")
interventions = _study_entity("interventions", "intervention")
eligibility_criteria = _study_entity("eligibility_criteria", "eligibility_criterion")
schedule_concepts = _study_entity("schedule_concepts", "schedule_concept")
endpoints = sa.Table(
    "endpoints",
    metadata,
    sa.Column("id", sa.String(length=128), primary_key=True),
    sa.Column("tenant_id", sa.String(length=128), nullable=False),
    sa.Column("study_id", sa.String(length=128), nullable=False),
    sa.Column("name", sa.String(length=512), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("hierarchy", sa.String(length=16), nullable=False),
    sa.Column("objective_id", sa.String(length=128)),
    sa.Column("timepoint_id", sa.String(length=128)),
    sa.UniqueConstraint("id", "tenant_id", name="uq_endpoint_id_tenant"),
    sa.ForeignKeyConstraint(
        ["study_id", "tenant_id"],
        ["studies.id", "studies.tenant_id"],
        name="fk_endpoint_study_tenant",
    ),
    sa.ForeignKeyConstraint(
        ["objective_id", "tenant_id"],
        ["objectives.id", "objectives.tenant_id"],
        name="fk_endpoint_objective_tenant",
    ),
    sa.ForeignKeyConstraint(
        ["timepoint_id", "tenant_id"],
        ["timepoints.id", "timepoints.tenant_id"],
        name="fk_endpoint_timepoint_tenant",
    ),
    sa.CheckConstraint(
        "hierarchy IN ('primary', 'secondary', 'exploratory')",
        name="ck_endpoint_hierarchy",
    ),
)
facts = sa.Table(
    "facts",
    metadata,
    sa.Column("id", sa.String(length=128), primary_key=True),
    sa.Column("tenant_id", sa.String(length=128), nullable=False),
    sa.Column("study_id", sa.String(length=128), nullable=False),
    sa.Column("kind", sa.String(length=64), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("critical", sa.Boolean(), nullable=False),
    sa.Column("deferred", sa.Boolean(), nullable=False),
    sa.Column("current_version", sa.Integer(), nullable=False),
    sa.UniqueConstraint("id", "tenant_id", name="uq_fact_id_tenant"),
    sa.ForeignKeyConstraint(
        ["study_id", "tenant_id"],
        ["studies.id", "studies.tenant_id"],
        name="fk_fact_study_tenant",
    ),
    sa.CheckConstraint(
        "status IN ('candidate','approved','rejected','superseded','conflicted')",
        name="ck_fact_status",
    ),
)
fact_versions = sa.Table(
    "fact_versions",
    metadata,
    sa.Column("id", sa.String(length=128), primary_key=True),
    sa.Column("tenant_id", sa.String(length=128), nullable=False),
    sa.Column("fact_id", sa.String(length=128), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("value_json", sa.JSON(), nullable=False),
    sa.Column("source_evidence_id", sa.String(length=128)),
    sa.Column("is_current", sa.Boolean(), nullable=False),
    sa.Column("rationale", sa.Text()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("fact_id", "version", name="uq_fact_version_number"),
    sa.ForeignKeyConstraint(
        ["fact_id", "tenant_id"],
        ["facts.id", "facts.tenant_id"],
        name="fk_fact_version_fact_tenant",
    ),
)
sa.Index(
    "uq_fact_version_current",
    fact_versions.c.fact_id,
    unique=True,
    sqlite_where=sa.text("is_current = 1"),
    postgresql_where=sa.text("is_current"),
)

TABLES = (
    studies,
    objectives,
    timepoints,
    populations,
    arms,
    interventions,
    eligibility_criteria,
    schedule_concepts,
    endpoints,
    facts,
    fact_versions,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        table.create(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind)
