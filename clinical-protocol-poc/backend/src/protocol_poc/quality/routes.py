from collections.abc import Iterator
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers
from protocol_poc.quality.service import QualityService


router = APIRouter(prefix="/api")


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


@router.get("/studies/{study_id}/quality")
def quality(study_id: str, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
    try:
        ctx = verify_identity_headers(request.headers.get("X-Tenant-ID", ""), request.headers.get("X-Actor-ID", ""), request.headers.get("X-Identity-Timestamp", ""), request.headers.get("X-Identity-Signature", ""), get_settings())
    except IdentityVerificationError as error:
        raise HTTPException(status_code=401, detail={"code": "IDENTITY_INVALID"}) from error
    return asdict(QualityService(session).calculate(ctx, study_id))
