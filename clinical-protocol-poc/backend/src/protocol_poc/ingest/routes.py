from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from protocol_poc.config import get_settings
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.ingest.docx_parser import DocxLimits, DocxParser, UnsafeDocumentError
from protocol_poc.ingest.service import IngestService, UploadInput, UploadValidationError
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
from protocol_poc.studies.document_workflow import (
    DocumentWorkflowService,
    UploadOutcome,
)
from protocol_poc.studies.service import (
    StudyArchived,
    StudyNotFound,
    StudyVersionConflict,
)


router = APIRouter(prefix="/api")


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


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
            {
                "code": finding.code,
                "field": finding.field,
                "message": finding.message,
            }
            for finding in outcome.findings
        ],
        "replacement_impact": list(outcome.replacement_impact),
    }


def _raise_upload_error(error: Exception) -> None:
    if isinstance(error, StudyNotFound):
        raise HTTPException(status_code=404, detail={"code": "STUDY_NOT_FOUND"}) from error
    if isinstance(error, StudyArchived):
        raise HTTPException(status_code=409, detail={"code": "STUDY_ARCHIVED"}) from error
    if isinstance(error, StudyVersionConflict):
        raise HTTPException(status_code=409, detail={"code": "STUDY_VERSION_CONFLICT"}) from error
    if isinstance(error, UploadValidationError):
        raise HTTPException(status_code=422, detail={"code": "INVALID_UPLOAD"}) from error
    if isinstance(error, UnsafeDocumentError):
        raise HTTPException(status_code=400, detail={"code": "UNSAFE_DOCUMENT"}) from error
    raise error


@router.post("/studies/{study_id}/inputs", status_code=status.HTTP_201_CREATED)
async def upload_input(
    study_id: str, request: Request, session: Session = Depends(database_session)
) -> dict[str, object]:
    settings = get_settings()
    try:
        context = verify_identity_headers(
            request.headers.get("X-Tenant-ID", ""),
            request.headers.get("X-Actor-ID", ""),
            request.headers.get("X-Identity-Timestamp", ""),
            request.headers.get("X-Identity-Signature", ""),
            settings,
        )
    except IdentityVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid multipart request") from exc
    role = form.get("role")
    uploaded = form.get("file")
    if not isinstance(role, str) or not isinstance(uploaded, UploadFile):
        raise HTTPException(status_code=422, detail="role and file are required")
    content = await uploaded.read(settings.max_upload_bytes + 1)
    parser = DocxParser(
        DocxLimits(
            settings.max_upload_bytes,
            settings.max_zip_entries,
            settings.max_zip_entry_bytes,
            settings.max_zip_total_bytes,
            settings.max_zip_compression_ratio,
        )
    )
    ingest = IngestService(session, LocalFileStorage(Path(settings.local_storage_path)), parser)
    service = DocumentWorkflowService(session, ingest)
    try:
        outcome = service.upload(
            context,
            study_id,
            UploadInput(
                role,
                uploaded.filename or "",
                uploaded.content_type or "",
                content,
            ),
        )
    except (
        StudyNotFound,
        StudyArchived,
        StudyVersionConflict,
        UploadValidationError,
        UnsafeDocumentError,
    ) as error:
        _raise_upload_error(error)
    return upload_outcome_payload(outcome)
