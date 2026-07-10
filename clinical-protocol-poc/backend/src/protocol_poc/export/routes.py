from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.export.service import ExportDenied, ExportService
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers


router = APIRouter(prefix="/api")


class ExportRequest(BaseModel):
    expected_study_version: int
    template_version_id: str
    template_hash: str


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory.begin() as session:
        yield session


@router.post("/studies/{study_id}/exports")
def export(study_id: str, command: ExportRequest, request: Request, session: Session = Depends(database_session)) -> dict[str, str]:
    try:
        ctx = verify_identity_headers(request.headers.get("X-Tenant-ID", ""), request.headers.get("X-Actor-ID", ""), request.headers.get("X-Identity-Timestamp", ""), request.headers.get("X-Identity-Signature", ""), get_settings())
    except IdentityVerificationError as error:
        raise HTTPException(status_code=401, detail={"code": "IDENTITY_INVALID"}) from error
    try:
        snapshot = ExportService(session).create_snapshot(ctx, study_id, expected_study_version=command.expected_study_version, template_version_id=command.template_version_id, template_hash=command.template_hash)
    except ExportDenied as error:
        raise HTTPException(status_code=409, detail={"code": "EXPORT_BLOCKED", "blockers": error.codes}) from error
    return {"snapshot_id": snapshot.id}
