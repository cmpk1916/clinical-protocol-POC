from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from protocol_poc.ai_gateway.fixture_provider import FixtureProvider
from protocol_poc.ai_gateway.service import AIGateway
from protocol_poc.config import get_settings
from protocol_poc.drafting.service import DraftingService
from protocol_poc.identity import IdentityVerificationError, verify_identity_headers


router = APIRouter(prefix="/api")


class GenerateRequest(BaseModel):
    section: str


def database_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory.begin() as session:
        yield session


@router.post("/studies/{study_id}/passages")
def generate_passage(study_id: str, command: GenerateRequest, request: Request, session: Session = Depends(database_session)) -> dict[str, str]:
    try:
        ctx = verify_identity_headers(
            request.headers.get("X-Tenant-ID", ""), request.headers.get("X-Actor-ID", ""),
            request.headers.get("X-Identity-Timestamp", ""), request.headers.get("X-Identity-Signature", ""), get_settings(),
        )
    except IdentityVerificationError as error:
        raise HTTPException(status_code=401, detail={"code": "IDENTITY_INVALID"}) from error
    fixture = {"text": "", "placeholders": [], "claims": [], "fact_ids": [], "guidance_ids": []}
    result = DraftingService(session, AIGateway(FixtureProvider(fixture))).generate(ctx, study_id, section=command.section)
    return {"passage_id": result.passage_id, "text": result.text, "status": result.status}
