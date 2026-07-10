from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


FactKind = Literal[
    "string", "integer", "decimal", "coded_value", "duration", "dose", "structured_criterion"
]


class FactValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FactKind
    value: str | int | Decimal | dict[str, object]
    unit: str | None = None
    code_system: str | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> "FactValue":
        if self.kind in {"decimal", "duration", "dose"}:
            if self.unit is None or not self.unit.strip():
                raise ValueError(f"{self.kind} requires a UCUM unit")
            try:
                self.value = Decimal(str(self.value))
            except InvalidOperation as error:
                raise ValueError(f"{self.kind} requires a numeric value") from error
        elif self.kind == "integer" and not isinstance(self.value, int):
            raise ValueError("integer requires an integer value")
        elif self.kind == "coded_value" and not self.code_system:
            raise ValueError("coded_value requires code_system")
        elif self.kind == "structured_criterion" and not isinstance(self.value, dict):
            raise ValueError("structured_criterion requires an object")
        return self


class Endpoint(BaseModel):
    name: str = Field(min_length=1)
    hierarchy: Literal["primary", "secondary", "exploratory"]
    objective_id: str | None = None
    timepoint_id: str | None = None


class RelationshipFinding(BaseModel):
    code: str


def validate_endpoint_relationships(endpoint: Endpoint) -> list[RelationshipFinding]:
    findings: list[RelationshipFinding] = []
    if endpoint.objective_id is None:
        findings.append(RelationshipFinding(code="ENDPOINT_OBJECTIVE_MISSING"))
    if endpoint.timepoint_id is None:
        findings.append(RelationshipFinding(code="ENDPOINT_TIMEPOINT_MISSING"))
    return findings
