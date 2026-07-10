from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
from protocol_poc.review.fact_service import FactReviewError, FactReviewService
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
    facts = FactReviewService(session).review_queue(ctx, study_id)
    return {"items": [{"id": fact.id, "kind": fact.kind, "status": fact.status, "critical": fact.critical, "version": fact.current_version} for fact in facts]}


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
    except FactReviewError as error:
        raise HTTPException(status_code=409, detail={"code": error.__class__.__name__.upper()}) from error
    return {"id": fact.id, "status": fact.status, "version": fact.current_version}
