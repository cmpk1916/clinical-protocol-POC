from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.export.artifact_service import ExportArtifactRepository
from protocol_poc.export.orchestration import ExportCommand, ExportOrchestrator
from protocol_poc.export.service import ExportDenied
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
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

    snapshot_id: str
    blockers: list[str]
    artifacts: list[ArtifactResponse]


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory.begin() as session:
        yield session


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
    except ExportDenied as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "EXPORT_BLOCKED", "blockers": error.codes},
        ) from error
    except (OSError, ValueError) as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "EXPORT_FAILED", "blockers": ["EXPORT_FAILED"]},
        ) from error
    return ExportResponse(
        snapshot_id=result.snapshot_id,
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
            for item in result.artifacts
        ],
    )


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
