from dataclasses import dataclass
from hashlib import sha256
import json

from pydantic import BaseModel, ValidationError

from protocol_poc.ai_gateway.provider import AIProvider
from protocol_poc.ai_gateway.schemas import (
    ClaimMapInput, ClaimMapOutput, DraftInput, DraftOutput, ExplainFindingInput,
    ExplainFindingOutput, ExtractionInput, ExtractionOutput, GatewaySchemaError,
    GuidanceInput, GuidanceOutput, SemanticReviewInput, SemanticReviewOutput,
)
from protocol_poc.ai_gateway.tasks import TaskType


@dataclass(frozen=True)
class GatewayCall:
    task_type: TaskType
    provider_id: str
    model_id: str
    prompt_version: str
    reference_ids: tuple[str, ...]
    response_hash: str | None
    schema_valid: bool
    status: str


CONTRACTS: dict[TaskType, tuple[type[BaseModel], type[BaseModel]]] = {
    TaskType.EXTRACT_FACTS: (ExtractionInput, ExtractionOutput),
    TaskType.RETRIEVE_GUIDANCE: (GuidanceInput, GuidanceOutput),
    TaskType.DRAFT_PASSAGE: (DraftInput, DraftOutput),
    TaskType.MAP_CLAIMS: (ClaimMapInput, ClaimMapOutput),
    TaskType.SEMANTIC_REVIEW: (SemanticReviewInput, SemanticReviewOutput),
    TaskType.EXPLAIN_FINDING: (ExplainFindingInput, ExplainFindingOutput),
}


class AIGateway:
    def __init__(self, provider: AIProvider, prompt_version: str = "v1") -> None:
        self.provider = provider
        self.prompt_version = prompt_version
        self.calls: list[GatewayCall] = []

    def run(self, task: TaskType, input_value: BaseModel) -> BaseModel:
        input_type, output_type = CONTRACTS[task]
        references = tuple(getattr(input_value, "evidence_ids", ()) or getattr(input_value, "fact_ids", ()))
        if type(input_value) is not input_type:
            self._record(task, references, None, False, "failed")
            raise GatewaySchemaError(f"invalid input schema for {task.value}")
        try:
            raw = self.provider.invoke(task, input_value.model_dump(mode="json"))
            encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
            result = output_type.model_validate(raw)
        except (ValidationError, TypeError, ValueError) as error:
            response_hash = sha256(encoded).hexdigest() if "encoded" in locals() else None
            self._record(task, references, response_hash, False, "failed")
            raise GatewaySchemaError(f"provider output failed {task.value} schema") from error
        self._record(task, references, sha256(encoded).hexdigest(), True, "succeeded")
        return result

    def _record(self, task: TaskType, references: tuple[str, ...], response_hash: str | None, valid: bool, status: str) -> None:
        self.calls.append(GatewayCall(task, self.provider.provider_id, self.provider.model_id, self.prompt_version, references, response_hash, valid, status))
