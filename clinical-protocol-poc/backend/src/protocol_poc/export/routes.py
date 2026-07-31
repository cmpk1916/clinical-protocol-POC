from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.export.artifact_service import ArtifactDescriptor, ExportArtifactRepository
from protocol_poc.export.orchestration import ExportCommand, ExportOrchestrator
from protocol_poc.export.service import ExportDenied
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
from protocol_poc.studies.service import StudyNotFound, StudyService
from protocol_poc.tenancy import TenantContext


router = APIRouter(prefix="/api")
RENDERER_VERSION = "renderer-v1"


def _camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(item.title() for item in rest)


class ExportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_camel)

    expected_study_version: int
    template_version_id: str
    template_hash: str


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_camel)

    id: str
    name: str
    media_type: str
    sha256: str
    snapshot_id: str
    download_url: str


class ExportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_camel)

    snapshot_id: str | None
    blockers: list[str]
    artifacts: list[ArtifactResponse]


def database_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def _identity(request: Request) -> TenantContext:
    try:
        return verify_identity_headers(
            request.headers.get("X-Tenant-ID", ""),
            request.headers.get("X-Actor-ID", ""),
            request.headers.get("X-Identity-Timestamp", ""),
            request.headers.get("X-Identity-Signature", ""),
            get_settings(),
        )
    except IdentityVerificationError as error:
        raise HTTPException(
            status_code=401, detail={"code": "IDENTITY_INVALID"}
        ) from error


def _export_response(
    snapshot_id: str | None,
    artifacts: tuple[ArtifactDescriptor, ...],
) -> ExportResponse:
    return ExportResponse(
        snapshot_id=snapshot_id,
        blockers=[],
        artifacts=[
            ArtifactResponse(
                id=item.id,
                name=item.name,
                media_type=item.media_type,
                sha256=item.sha256,
                snapshot_id=item.snapshot_id,
                download_url=item.download_url,
            )
            for item in artifacts
        ],
    )


@router.get(
    "/studies/{study_id}/exports/latest",
    response_model=ExportResponse,
    response_model_by_alias=True,
)
def latest_export(
    study_id: str,
    request: Request,
    session: Session = Depends(database_session),
) -> ExportResponse:
    ctx = _identity(request)
    try:
        StudyService(session).get(ctx, study_id)
        latest = ExportArtifactRepository(
            session,
            LocalFileStorage(Path(get_settings().local_storage_path)),
        ).latest_for_study(ctx, study_id)
    except StudyNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "STUDY_NOT_FOUND"},
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "EXPORT_INTEGRITY_FAILED"},
        ) from error
    if latest is None:
        return _export_response(None, ())
    return _export_response(latest.snapshot_id, latest.descriptors)


@router.post(
    "/studies/{study_id}/exports",
    status_code=status.HTTP_201_CREATED,
    response_model=ExportResponse,
    response_model_by_alias=True,
)
def export(
    study_id: str,
    command: dict[str, object],
    request: Request,
    session: Session = Depends(database_session),
) -> ExportResponse:
    ctx = _identity(request)
    parsed = ExportRequest.model_validate(command)
    settings = get_settings()
    storage = LocalFileStorage(Path(settings.local_storage_path))
    result = None
    try:
        result = ExportOrchestrator(session, storage, RENDERER_VERSION).create(
            ctx,
            study_id,
            ExportCommand(
                parsed.expected_study_version,
                parsed.template_version_id,
                parsed.template_hash,
            ),
        )
        session.commit()
    except ExportDenied as error:
        session.commit()
        raise HTTPException(
            status_code=409,
            detail={"code": "EXPORT_BLOCKED", "blockers": error.codes},
        ) from error
    except (OSError, ValueError, SQLAlchemyError) as error:
        session.rollback()
        if result is not None:
            ExportArtifactRepository(session, storage).delete_storage_keys(result.storage_keys)
        raise HTTPException(
            status_code=409,
            detail={"code": "EXPORT_FAILED", "blockers": ["EXPORT_FAILED"]},
        ) from error
    return _export_response(result.snapshot_id, result.artifacts)


@router.get("/export-artifacts/{artifact_id}")
def download_artifact(
    artifact_id: str,
    request: Request,
    session: Session = Depends(database_session),
) -> StreamingResponse:
    ctx = _identity(request)
    storage = LocalFileStorage(Path(get_settings().local_storage_path))
    try:
        record, content = ExportArtifactRepository(session, storage).get(ctx, artifact_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND"}) from error
    except OSError as error:
        raise HTTPException(status_code=409, detail={"code": "ARTIFACT_INTEGRITY_FAILED"}) from error
    return StreamingResponse(
        BytesIO(content),
        media_type=record.media_type,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )
