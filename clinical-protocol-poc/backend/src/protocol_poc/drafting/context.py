from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.guidance.models import GuidanceChunk, GuidanceRelease
from protocol_poc.studies.models import Fact, FactVersion
from protocol_poc.tenancy import TenantContext, require_tenant_context


@dataclass(frozen=True)
class DraftContext:
    section: str
    facts: dict[str, dict[str, Any]]
    guidance: dict[str, str]

    @property
    def fact_ids(self) -> tuple[str, ...]:
        return tuple(self.facts)

    @property
    def guidance_ids(self) -> tuple[str, ...]:
        return tuple(self.guidance)


class DraftContextBuilder:
    def __init__(self, session: Session) -> None:
        self.session = session

    def for_section(self, ctx: TenantContext, study_id: str, section: str) -> DraftContext:
        context = require_tenant_context(ctx)
        facts = self.session.execute(
            select(Fact, FactVersion)
            .join(FactVersion, (FactVersion.fact_id == Fact.id) & (FactVersion.tenant_id == Fact.tenant_id))
            .where(
                Fact.tenant_id == context.tenant_id, Fact.study_id == study_id,
                Fact.status == "approved", FactVersion.is_current.is_(True),
            )
            .order_by(Fact.id)
        ).all()
        guidance = self.session.execute(
            select(GuidanceChunk)
            .join(GuidanceRelease, (GuidanceRelease.id == GuidanceChunk.release_id) & (GuidanceRelease.tenant_id == GuidanceChunk.tenant_id))
            .where(GuidanceChunk.tenant_id == context.tenant_id, GuidanceRelease.state == "active")
            .order_by(GuidanceChunk.id)
        ).scalars()
        return DraftContext(
            section=section,
            facts={fact.id: {"fact_kind": fact.kind, **version.value_json} for fact, version in facts},
            guidance={chunk.id: chunk.content for chunk in guidance},
        )
