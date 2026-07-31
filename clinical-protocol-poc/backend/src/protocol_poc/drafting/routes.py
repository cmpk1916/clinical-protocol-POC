from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.drafting.models import Claim, Passage, PassageVersion, SupportLink
from protocol_poc.drafting.review_service import PassageBlocked, PassageReviewError, PassageReviewService, PassageVersionConflict
from protocol_poc.drafting.service import DraftingService, PassageAlreadyExists
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
from protocol_poc.studies.service import StudyArchived, StudyNotFound, StudyService
from protocol_poc.tenancy import TenantContext


router = APIRouter(prefix="/api")


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: Literal["synopsis", "objectives_endpoints", "study_design", "eligibility"]


class PassageReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "edit", "reject", "regenerate"]
    expected_version: int
    text: str = ""
    support_ids: tuple[str, ...] = ()
    rationale: str = ""


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


@router.get("/studies/{study_id}/passages")
def list_passages(study_id: str, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
    ctx = identity(request)
    try:
        study = StudyService(session).get(ctx, study_id)
    except StudyNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "STUDY_NOT_FOUND"}) from error
    passages = list(session.scalars(select(Passage).where(
        Passage.tenant_id == ctx.tenant_id, Passage.study_id == study_id,
    ).order_by(Passage.section)))
    return {"read_only": study.lifecycle == "archived", "passages": [_passage_payload(session, ctx, item) for item in passages]}


@router.post("/studies/{study_id}/passages")
def generate_passage(study_id: str, command: GenerateRequest, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
    ctx = identity(request)
    try:
        result = DraftingService(session).generate(ctx, study_id, section=command.section)
    except StudyNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "STUDY_NOT_FOUND"}) from error
    except StudyArchived as error:
        raise HTTPException(status_code=409, detail={"code": "STUDY_ARCHIVED"}) from error
    except PassageAlreadyExists as error:
        raise HTTPException(status_code=409, detail={"code": "PASSAGE_ALREADY_EXISTS"}) from error
    return {"passage_id": result.passage_id, "text": result.text, "status": result.status, "version": result.version}


@router.post("/passages/{passage_id}/review")
def review_passage(passage_id: str, command: PassageReviewCommand, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
    ctx = identity(request)
    review = PassageReviewService(session)
    try:
        if command.action == "accept":
            passage = review.accept(ctx, passage_id, expected_version=command.expected_version)
            result = {"id": passage.id, "status": passage.status, "version": passage.current_version}
        elif command.action == "edit":
            passage = review.edit(ctx, passage_id, expected_version=command.expected_version, text=command.text, support_ids=command.support_ids)
            result = {"id": passage.id, "status": passage.status, "version": passage.current_version}
        elif command.action == "reject":
            passage = review.reject(ctx, passage_id, expected_version=command.expected_version, rationale=command.rationale)
            result = {"id": passage.id, "status": passage.status, "version": passage.current_version}
        else:
            generated = DraftingService(session).regenerate(ctx, passage_id, expected_version=command.expected_version)
            result = {"id": generated.passage_id, "status": generated.status, "version": generated.version}
    except StudyNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "STUDY_NOT_FOUND"}) from error
    except StudyArchived as error:
        raise HTTPException(status_code=409, detail={"code": "STUDY_ARCHIVED"}) from error
    except PassageVersionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "PASSAGE_VERSION_CONFLICT"}) from error
    except (PassageBlocked, PassageReviewError, ValueError) as error:
        raise HTTPException(status_code=409, detail={"code": error.__class__.__name__.upper()}) from error
    return result


def _passage_payload(session: Session, ctx: TenantContext, passage: Passage) -> dict[str, object]:
    version = session.scalar(select(PassageVersion).where(
        PassageVersion.tenant_id == ctx.tenant_id,
        PassageVersion.passage_id == passage.id,
        PassageVersion.is_current.is_(True),
    ))
    if version is None:
        raise RuntimeError("current passage version missing")
    claims = list(session.scalars(select(Claim).where(Claim.tenant_id == ctx.tenant_id, Claim.passage_version_id == version.id)))
    links = list(session.scalars(select(SupportLink).where(SupportLink.tenant_id == ctx.tenant_id, SupportLink.passage_version_id == version.id)))
    facts = next(
        (
            list(claim.metadata_json["fact_ids"])
            for claim in claims
            if isinstance(claim.metadata_json.get("fact_ids"), list)
        ),
        sorted(link.support_id for link in links if link.support_type == "fact"),
    )
    guidance = sorted(link.support_id for link in links if link.support_type == "guidance")
    return {
        "id": passage.id, "section": passage.section, "text": version.text, "status": passage.status,
        "version": passage.current_version, "placeholders": version.placeholders, "stale": passage.status == "stale",
        "findings": version.validation_findings,
        "claims": [{"text": claim.text, **claim.metadata_json} for claim in claims],
        "fact_support_ids": facts, "guidance_support_ids": guidance,
    }
