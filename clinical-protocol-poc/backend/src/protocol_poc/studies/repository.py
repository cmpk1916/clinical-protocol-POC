from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.studies.models import Fact, Study
from protocol_poc.tenancy import TenantContext


class StudyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, ctx: TenantContext, study_id: str) -> Study | None:
        return self.session.scalar(select(Study).where(Study.id == study_id, Study.tenant_id == ctx.tenant_id))

    def get_fact(self, ctx: TenantContext, fact_id: str) -> Fact | None:
        return self.session.scalar(select(Fact).where(Fact.id == fact_id, Fact.tenant_id == ctx.tenant_id))
