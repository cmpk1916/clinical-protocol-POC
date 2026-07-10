from sqlalchemy import select
from sqlalchemy.orm import Session

from protocol_poc.guidance.index import GuidanceDocument, GuidanceIndex
from protocol_poc.guidance.models import GuidanceChunk, GuidanceRelease


class GuidanceService:
    def __init__(self, session: Session, index: GuidanceIndex | None = None) -> None:
        self.session = session
        self.index = index or GuidanceIndex()

    def rebuild_index(self, tenant_id: str) -> None:
        rows = self.session.execute(
            select(GuidanceChunk, GuidanceRelease)
            .join(GuidanceRelease, (GuidanceRelease.id == GuidanceChunk.release_id) & (GuidanceRelease.tenant_id == GuidanceChunk.tenant_id))
            .where(GuidanceRelease.tenant_id == tenant_id, GuidanceRelease.state == "active")
        ).all()
        self.index.rebuild([
            GuidanceDocument(chunk.id, release.id, chunk.tenant_id, chunk.content, chunk.content_hash)
            for chunk, release in rows
        ])

    def search(self, query: str, *, tenant_id: str) -> list[GuidanceDocument]:
        return self.index.search(query, tenant_id=tenant_id)
