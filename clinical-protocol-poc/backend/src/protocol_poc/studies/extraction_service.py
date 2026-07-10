from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from protocol_poc.ai_gateway.schemas import ExtractionInput, ExtractionOutput, GatewaySchemaError
from protocol_poc.ai_gateway.service import AIGateway
from protocol_poc.ai_gateway.tasks import TaskType
from protocol_poc.common.ids import new_id
from protocol_poc.studies.enums import FactStatus
from protocol_poc.studies.models import Fact, FactVersion
from protocol_poc.tenancy import TenantContext


@dataclass(frozen=True)
class EvidenceRef:
    id: str
    location: dict[str, Any]


class ExtractionService:
    def __init__(self, session: Session, gateway: AIGateway) -> None:
        self.session = session
        self.gateway = gateway

    def extract(self, ctx: TenantContext, study_id: str, evidence: list[EvidenceRef]) -> list[Fact]:
        by_id = {item.id: item for item in evidence}
        output = self.gateway.run(TaskType.EXTRACT_FACTS, ExtractionInput(evidence_ids=list(by_id)))
        if not isinstance(output, ExtractionOutput):
            raise GatewaySchemaError("unexpected extraction output")
        for candidate in output.candidates:
            source = by_id.get(candidate.source_evidence_id)
            if source is None or source.location != candidate.source_location.model_dump():
                raise GatewaySchemaError("candidate source location does not match supplied evidence")
        facts: list[Fact] = []
        for candidate in output.candidates:
            fact = Fact(
                id=new_id(), tenant_id=ctx.tenant_id, study_id=study_id, kind=candidate.kind,
                status=FactStatus.CANDIDATE.value, critical=candidate.critical, current_version=1,
            )
            version = FactVersion(
                tenant_id=ctx.tenant_id, fact_id=fact.id, version=1,
                value_json={
                    "value": candidate.value.model_dump(mode="json"),
                    "source_location": candidate.source_location.model_dump(),
                    "confidence": candidate.confidence,
                },
                source_evidence_id=candidate.source_evidence_id,
                is_current=True,
            )
            self.session.add_all([fact, version])
            facts.append(fact)
        self.session.flush()
        return facts
