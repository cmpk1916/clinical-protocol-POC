from dataclasses import dataclass
from typing import Literal


DimensionStatus = Literal["pass", "needs_review", "blocked", "not_applicable"]


@dataclass(frozen=True)
class QualityBlocker:
    code: str
    message: str
    linked_id: str | None = None


@dataclass(frozen=True)
class DimensionResult:
    status: DimensionStatus
    passed_count: int
    applicable_count: int
    finding_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityScorecard:
    dimensions: dict[str, DimensionResult]
    blockers: tuple[QualityBlocker, ...]
    export_status: Literal["blocked", "eligible"]
    disclaimer: str = "Synthetic POC output only; no clinical, regulatory, submission, or operational readiness is claimed."
