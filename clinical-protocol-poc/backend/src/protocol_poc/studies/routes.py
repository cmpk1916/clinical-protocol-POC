from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
from protocol_poc.studies.models import Study
from protocol_poc.studies.document_workflow import UploadOutcome
from protocol_poc.studies.service import (
    StudyArchived,
    StudyNotFound,
    StudyService,
    StudyVersionConflict,
)
from protocol_poc.tenancy import TenantContext


router = APIRouter(prefix="/api/studies")


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory.begin() as session:
        yield session


def identity(request: Request) -> TenantContext:
    try:
        return verify_identity_headers(
            request.headers.get("X-Tenant-ID", ""),
            request.headers.get("X-Actor-ID", ""),
            request.headers.get("X-Identity-Timestamp", ""),
            request.headers.get("X-Identity-Signature", ""),
            get_settings(),
        )
    except IdentityVerificationError as error:
        raise HTTPException(status_code=401, detail={"code": "IDENTITY_INVALID"}) from error


class CreateStudyCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("study name must not be blank")
        return value


class VersionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


def _study_payload(study: Study) -> dict[str, object]:
    return {
        "id": study.id,
        "name": study.name,
        "lifecycle": study.lifecycle,
        "version": study.version,
        "created_at": study.created_at,
        "updated_at": study.updated_at,
        "archived_at": study.archived_at,
    }


def upload_outcome_payload(outcome: UploadOutcome) -> dict[str, object]:
    return {
        "job_id": outcome.job_id,
        "file_id": outcome.file_id,
        "version_id": outcome.version_id,
        "version": outcome.version,
        "checksum_sha256": outcome.checksum_sha256,
        "status": outcome.status,
        "current_file_version_id": outcome.current_file_version_id,
        "findings": [
            {"code": finding.code, "field": finding.field, "message": finding.message}
            for finding in outcome.findings
        ],
        "replacement_impact": list(outcome.replacement_impact),
    }


def _raise_domain_error(error: StudyNotFound | StudyVersionConflict | StudyArchived) -> None:
    if isinstance(error, StudyNotFound):
        raise HTTPException(status_code=404, detail={"code": "STUDY_NOT_FOUND"}) from error
    if isinstance(error, StudyArchived):
        raise HTTPException(status_code=409, detail={"code": "STUDY_ARCHIVED"}) from error
    raise HTTPException(status_code=409, detail={"code": "STUDY_VERSION_CONFLICT"}) from error


@router.post("")
def create_study(
    command: CreateStudyCommand,
    request: Request,
    session: Session = Depends(database_session),
) -> dict[str, object]:
    return _study_payload(StudyService(session).create(identity(request), command.name))


@router.get("")
def list_studies(
    request: Request,
    lifecycle: Literal["active", "archived"] = "active",
    session: Session = Depends(database_session),
) -> dict[str, object]:
    studies = StudyService(session).list(identity(request), lifecycle)
    return {"items": [_study_payload(study) for study in studies]}


@router.get("/{study_id}")
def get_study(
    study_id: str,
    request: Request,
    session: Session = Depends(database_session),
) -> dict[str, object]:
    try:
        study = StudyService(session).get(identity(request), study_id)
    except StudyNotFound as error:
        _raise_domain_error(error)
    return _study_payload(study)


@router.post("/{study_id}/archive")
def archive_study(
    study_id: str,
    command: VersionCommand,
    request: Request,
    session: Session = Depends(database_session),
) -> dict[str, object]:
    try:
        study = StudyService(session).archive(
            identity(request), study_id, command.expected_version
        )
    except (StudyNotFound, StudyVersionConflict, StudyArchived) as error:
        _raise_domain_error(error)
    return _study_payload(study)


@router.post("/{study_id}/restore")
def restore_study(
    study_id: str,
    command: VersionCommand,
    request: Request,
    session: Session = Depends(database_session),
) -> dict[str, object]:
    try:
        study = StudyService(session).restore(
            identity(request), study_id, command.expected_version
        )
    except (StudyNotFound, StudyVersionConflict, StudyArchived) as error:
        _raise_domain_error(error)
    return _study_payload(study)
