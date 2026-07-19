from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
from protocol_poc.review.fact_service import FactNotFound, FactReviewError, FactReviewService
from protocol_poc.studies.service import StudyArchived, StudyNotFound, StudyService
from protocol_poc.tenancy import TenantContext


router = APIRouter(prefix="/api")


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory.begin() as session:
        yield session


def identity(request: Request) -> TenantContext:
    try:
        return verify_identity_headers(
            request.headers.get("X-Tenant-ID", ""), request.headers.get("X-Actor-ID", ""),
            request.headers.get("X-Identity-Timestamp", ""), request.headers.get("X-Identity-Signature", ""), get_settings(),
        )
    except IdentityVerificationError as error:
        raise HTTPException(status_code=401, detail={"code": "IDENTITY_INVALID"}) from error


class ReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "correct_and_approve", "reject", "defer", "resolve_conflict"]
    expected_version: int
    explicitly_confirmed: bool = False
    value: dict[str, Any] | None = None
    rationale: str = ""


@router.get("/studies/{study_id}/fact-review")
def review_queue(study_id: str, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
    ctx = identity(request)
    try:
        study = StudyService(session).get(ctx, study_id)
    except StudyNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "STUDY_NOT_FOUND"}) from error
    items = FactReviewService(session).review_items(ctx, study_id)
    return {"read_only": study.lifecycle == "archived", "items": [
        {
            "id": item.fact.id,
            "kind": item.fact.kind,
            "status": item.fact.status,
            "current_value": item.value,
            "confidence": item.confidence,
            "source_evidence": (
                {
                    "id": item.evidence_id,
                    "location": item.evidence_location,
                    "text": item.evidence_text,
                }
                if item.evidence_id is not None
                else None
            ),
            "critical": item.fact.critical,
            "version": item.fact.current_version,
            "extractor_version": item.extractor_version,
            "synopsis_version_id": item.synopsis_version_id,
            "downstream_impact": list(item.downstream_impact),
        }
        for item in items
    ]}


@router.post("/facts/{fact_id}/review")
def review_fact(fact_id: str, command: ReviewCommand, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
    ctx = identity(request)
    service = FactReviewService(session)
    try:
        if command.action == "approve":
            fact = service.approve(ctx, fact_id, expected_version=command.expected_version, explicitly_confirmed=command.explicitly_confirmed)
        elif command.action == "correct_and_approve":
            if command.value is None:
                raise HTTPException(status_code=422, detail={"code": "VALUE_REQUIRED"})
            fact = service.correct_and_approve(ctx, fact_id, expected_version=command.expected_version, value_json=command.value, rationale=command.rationale, explicitly_confirmed=command.explicitly_confirmed)
        elif command.action == "reject":
            fact = service.reject(ctx, fact_id, expected_version=command.expected_version, rationale=command.rationale)
        elif command.action == "defer":
            fact = service.defer(ctx, fact_id, expected_version=command.expected_version, rationale=command.rationale)
        else:
            fact = service.resolve_conflict(ctx, fact_id, expected_version=command.expected_version, resolution=command.rationale)
    except (StudyNotFound, FactNotFound) as error:
        raise HTTPException(status_code=404, detail={"code": "STUDY_NOT_FOUND"}) from error
    except StudyArchived as error:
        raise HTTPException(status_code=409, detail={"code": "STUDY_ARCHIVED"}) from error
    except FactReviewError as error:
        raise HTTPException(status_code=409, detail={"code": error.__class__.__name__.upper()}) from error
    return {"id": fact.id, "status": fact.status, "version": fact.current_version}
