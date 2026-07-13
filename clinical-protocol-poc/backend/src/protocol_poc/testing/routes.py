from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import shutil
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.db import Base
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.testing.seed_service import seed_synthetic_study


router = APIRouter(prefix="/test", tags=["test-support"])


class SeedRequest(BaseModel):
    scenario: str


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory.begin() as session:
        yield session


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
        "passage": _passage(findings=[{
            "code": "UNSUPPORTED_CONTENT", "message": "Unsupported eligibility criterion",
        }]),
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
_study_commands: dict[str, dict[str, object]] = {}


@router.post("/reset")
def reset_test_state(request: Request) -> dict[str, str]:
    _study_scenarios.clear()
    _study_commands.clear()
    Base.metadata.drop_all(request.app.state.engine)
    Base.metadata.create_all(request.app.state.engine)
    storage_root = Path(get_settings().local_storage_path)
    shutil.rmtree(storage_root, ignore_errors=True)
    storage_root.mkdir(parents=True, exist_ok=True)
    return {"status": "reset"}


@router.post("/studies/{study_id}/seed")
def seed_study(
    study_id: str,
    request: SeedRequest,
    session: Session = Depends(database_session),
) -> dict[str, str]:
    if request.scenario not in SCENARIOS:
        return {"status": "unknown_scenario"}
    storage = LocalFileStorage(Path(get_settings().local_storage_path))
    _study_commands[study_id] = seed_synthetic_study(
        session, storage, study_id, request.scenario
    )
    _study_scenarios[study_id] = request.scenario
    return {"status": "seeded", "scenario": request.scenario}


@router.get("/studies/{study_id}/state")
def get_study_state(study_id: str) -> dict[str, Any]:
    scenario = _study_scenarios.get(study_id, "happy_path")
    return {
        "scenario": scenario,
        **SCENARIOS[scenario],
        "exportCommand": _study_commands.get(study_id),
    }
