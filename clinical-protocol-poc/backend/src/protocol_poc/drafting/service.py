from dataclasses import dataclass

from sqlalchemy.orm import Session

from protocol_poc.ai_gateway.schemas import DraftInput, DraftOutput, GatewaySchemaError
from protocol_poc.ai_gateway.service import AIGateway
from protocol_poc.ai_gateway.tasks import TaskType
from protocol_poc.drafting.context import DraftContextBuilder
from protocol_poc.drafting.models import Claim, Passage, PassageVersion, SupportLink
from protocol_poc.tenancy import TenantContext


@dataclass(frozen=True)
class DraftResult:
    passage_id: str
    text: str
    status: str


class DraftingService:
    SCOPED_SECTIONS = {"synopsis", "objectives_endpoints", "study_design", "eligibility"}
    REQUIRED_FACTS = {
        "synopsis": {},
        "objectives_endpoints": {"objective": "objective", "endpoint": "endpoint"},
        "study_design": {"dose": "intervention dose"},
        "eligibility": {"eligibility": "eligibility criteria"},
    }

    def __init__(self, session: Session, gateway: AIGateway) -> None:
        self.session = session
        self.gateway = gateway

    def generate(self, ctx: TenantContext, study_id: str, *, section: str) -> DraftResult:
        if section not in self.SCOPED_SECTIONS:
            raise ValueError("section is outside the bounded drafting scope")
        context = DraftContextBuilder(self.session).for_section(ctx, study_id, section)
        available_kinds = {value["kind"] for value in context.facts.values()}
        missing = [label for kind, label in self.REQUIRED_FACTS[section].items() if kind not in available_kinds]
        if missing:
            placeholders = [f"[[REQUIRED: {label}]]" for label in missing]
            output = DraftOutput(text="\n".join(placeholders), placeholders=placeholders)
            status = "blocked"
        else:
            raw = self.gateway.run(
                TaskType.DRAFT_PASSAGE,
                DraftInput(section=section, fact_ids=list(context.fact_ids), guidance_ids=list(context.guidance_ids)),
            )
            if not isinstance(raw, DraftOutput):
                raise GatewaySchemaError("unexpected draft output")
            if not set(raw.fact_ids).issubset(context.fact_ids) or not set(raw.guidance_ids).issubset(context.guidance_ids):
                raise GatewaySchemaError("draft referenced support outside supplied context")
            output = raw
            status = "blocked" if output.placeholders else "ready_for_review"
        passage = Passage(tenant_id=ctx.tenant_id, study_id=study_id, section=section, status=status, current_version=1)
        self.session.add(passage)
        self.session.flush()
        version = PassageVersion(tenant_id=ctx.tenant_id, passage_id=passage.id, version=1, text=output.text, placeholders=output.placeholders, is_current=True)
        self.session.add(version)
        self.session.flush()
        self.session.add_all([
            Claim(tenant_id=ctx.tenant_id, passage_version_id=version.id, text=str(claim.get("text", "")), metadata_json=claim)
            for claim in output.claims
        ])
        self.session.add_all([
            SupportLink(tenant_id=ctx.tenant_id, passage_version_id=version.id, support_type="fact", support_id=support_id)
            for support_id in output.fact_ids
        ] + [
            SupportLink(tenant_id=ctx.tenant_id, passage_version_id=version.id, support_type="guidance", support_id=support_id)
            for support_id in output.guidance_ids
        ])
        self.session.flush()
        return DraftResult(passage.id, output.text, status)
