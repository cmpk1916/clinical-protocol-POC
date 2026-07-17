from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from protocol_poc.studies.models import Fact, Study
from protocol_poc.tenancy import TenantContext


class StudyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, ctx: TenantContext, study_id: str) -> Study | None:
        return self.session.scalar(select(Study).where(Study.id == study_id, Study.tenant_id == ctx.tenant_id))

    def add(self, study: Study) -> None:
        self.session.add(study)

    def list(self, ctx: TenantContext, lifecycle: str) -> list[Study]:
        statement = (
            select(Study)
            .where(Study.tenant_id == ctx.tenant_id, Study.lifecycle == lifecycle)
            .order_by(Study.created_at, Study.id)
        )
        return list(self.session.scalars(statement))

    def transition(
        self,
        ctx: TenantContext,
        study_id: str,
        *,
        expected_version: int,
        current_lifecycle: str,
        next_lifecycle: str,
        updated_at: datetime,
        archived_at: datetime | None,
    ) -> bool:
        result = self.session.execute(
            update(Study)
            .where(
                Study.id == study_id,
                Study.tenant_id == ctx.tenant_id,
                Study.version == expected_version,
                Study.lifecycle == current_lifecycle,
            )
            .values(
                lifecycle=next_lifecycle,
                version=Study.version + 1,
                updated_at=updated_at,
                archived_at=archived_at,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def get_fact(self, ctx: TenantContext, fact_id: str) -> Fact | None:
        return self.session.scalar(select(Fact).where(Fact.id == fact_id, Fact.tenant_id == ctx.tenant_id))
