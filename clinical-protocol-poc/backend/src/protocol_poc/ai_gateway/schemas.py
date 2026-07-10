from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from protocol_poc.studies.schemas import FactValue


class GatewaySchemaError(ValueError):
    """Raised when a task or provider response violates its allowlisted contract."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractionInput(StrictModel):
    evidence_ids: list[str] = Field(min_length=1)


class SourceLocation(StrictModel):
    kind: str
    index: int = Field(ge=0)


class ExtractedCandidate(StrictModel):
    kind: str
    value: FactValue
    source_evidence_id: str
    source_location: SourceLocation
    critical: bool = False
    confidence: float = Field(ge=0, le=1)


class ExtractionOutput(StrictModel):
    candidates: list[ExtractedCandidate]


class GuidanceInput(StrictModel):
    query: str


class GuidanceOutput(StrictModel):
    result_ids: list[str]


class DraftInput(StrictModel):
    section: str
    fact_ids: list[str]
    guidance_ids: list[str]


class DraftOutput(StrictModel):
    text: str
    placeholders: list[str] = []
    claims: list[dict[str, Any]] = []
    fact_ids: list[str] = []
    guidance_ids: list[str] = []


class ClaimMapInput(StrictModel):
    passage: str


class ClaimMapOutput(StrictModel):
    claims: list[dict[str, Any]]


class SemanticReviewInput(StrictModel):
    passage: str


class SemanticReviewOutput(StrictModel):
    findings: list[dict[str, Any]]


class ExplainFindingInput(StrictModel):
    finding_code: str


class ExplainFindingOutput(StrictModel):
    explanation: str
