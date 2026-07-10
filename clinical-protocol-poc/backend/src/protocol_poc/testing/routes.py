from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/test", tags=["test-support"])


class SeedRequest(BaseModel):
    scenario: str


def _passage(*, stale: bool = False, findings: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "id": "passage-dose",
        "section": "Treatment administration",
        "text": "Participants receive 10 mg once daily.",
        "status": "stale" if stale else "valid",
        "stale": stale,
        "findings": findings or [],
        "evidence": ["Synopsis p. 4 supports 10 mg once daily"],
        "guidance": ["Draft only from approved facts."],
        "impact": ["Traceability table", "Export snapshot"],
    }


SCENARIOS: dict[str, dict[str, Any]] = {
    "happy_path": {
        "passage": _passage(),
        "export": {"blockers": [], "snapshotId": None, "artifacts": []},
    },
    "unsupported_eligibility": {
        "passage": _passage(
            findings=[
                {
                    "code": "UNSUPPORTED_CONTENT",
                    "message": "Unsupported eligibility criterion",
                }
            ]
        ),
        "export": {
            "blockers": ["Unsupported eligibility criterion"],
            "snapshotId": None,
            "artifacts": [],
        },
    },
    "fact_change_invalidation": {
        "passage": _passage(stale=True),
        "export": {
            "blockers": ["Approved dose changed after passage acceptance"],
            "snapshotId": None,
            "artifacts": [],
        },
    },
}

_study_scenarios: dict[str, str] = {}


@router.post("/reset")
def reset_test_state() -> dict[str, str]:
    _study_scenarios.clear()
    return {"status": "reset"}


@router.post("/studies/{study_id}/seed")
def seed_study(study_id: str, request: SeedRequest) -> dict[str, str]:
    if request.scenario not in SCENARIOS:
        return {"status": "unknown_scenario"}
    _study_scenarios[study_id] = request.scenario
    return {"status": "seeded", "scenario": request.scenario}


@router.get("/studies/{study_id}/state")
def get_study_state(study_id: str) -> dict[str, Any]:
    scenario = _study_scenarios.get(study_id, "happy_path")
    return {"scenario": scenario, **SCENARIOS[scenario]}
