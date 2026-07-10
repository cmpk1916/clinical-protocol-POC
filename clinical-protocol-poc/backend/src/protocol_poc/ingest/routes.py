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


router = APIRouter(prefix="/api")


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


@router.post("/studies/{study_id}/inputs", status_code=status.HTTP_201_CREATED)
async def upload_input(study_id: str, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
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
    parser = DocxParser(DocxLimits(settings.max_upload_bytes, settings.max_zip_entries, settings.max_zip_entry_bytes, settings.max_zip_total_bytes, settings.max_zip_compression_ratio))
    service = IngestService(session, LocalFileStorage(Path(settings.local_storage_path)), parser)
    try:
        result = service.ingest(context, study_id, UploadInput(role, uploaded.filename or "", uploaded.content_type or "", content))
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnsafeDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": result.job_id, "file_id": result.file_id, "version_id": result.version_id, "version": result.version, "checksum_sha256": result.checksum_sha256, "status": result.status}
