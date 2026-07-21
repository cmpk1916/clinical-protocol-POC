from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.audit.service import AuditService
from protocol_poc.drafting.models import Passage, PassageVersion, SupportLink
from protocol_poc.tenancy import TenantContext


class ImpactService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def invalidate_for_fact(self, ctx: TenantContext, fact_id: str) -> list[Passage]:
        return self.invalidate_for_facts(ctx, (fact_id,))

    def invalidate_for_facts(
        self, ctx: TenantContext, fact_ids: tuple[str, ...] | list[str]
    ) -> list[Passage]:
        """Stale accepted passages supported by any changed fact in one batch."""
        if not fact_ids:
            return []
        statement = (
            select(Passage)
            .join(PassageVersion, (PassageVersion.passage_id == Passage.id) & (PassageVersion.tenant_id == Passage.tenant_id))
            .join(SupportLink, (SupportLink.passage_version_id == PassageVersion.id) & (SupportLink.tenant_id == PassageVersion.tenant_id))
            .where(
                Passage.tenant_id == ctx.tenant_id,
                Passage.status == "accepted",
                PassageVersion.is_current.is_(True),
                SupportLink.support_type == "fact",
                SupportLink.support_id.in_(fact_ids),
            )
        )
        passages = list(self.session.scalars(statement).unique())
        for passage in passages:
            passage.status = "stale"
            passage.invalidation_reason = "supporting_fact_changed"
            self.audit.append(
                ctx,
                "passage.invalidated",
                "passage",
                passage.id,
                {
                    "fact_ids": list(fact_ids),
                    "reason": passage.invalidation_reason,
                },
            )
        return passages
