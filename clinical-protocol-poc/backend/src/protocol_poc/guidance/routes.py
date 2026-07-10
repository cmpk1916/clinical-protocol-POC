from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from protocol_poc.config import get_settings
from protocol_poc.guidance.service import GuidanceService
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers


router = APIRouter(prefix="/api/guidance")


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


@router.get("/search")
def search_guidance(query: str, request: Request, session: Session = Depends(database_session)) -> dict[str, object]:
    try:
        ctx = verify_identity_headers(
            request.headers.get("X-Tenant-ID", ""), request.headers.get("X-Actor-ID", ""),
            request.headers.get("X-Identity-Timestamp", ""), request.headers.get("X-Identity-Signature", ""), get_settings(),
        )
    except IdentityVerificationError as error:
        raise HTTPException(status_code=401, detail={"code": "IDENTITY_INVALID"}) from error
    service = GuidanceService(session)
    service.rebuild_index(ctx.tenant_id)
    return {"items": [item.__dict__ for item in service.search(query, tenant_id=ctx.tenant_id)]}
