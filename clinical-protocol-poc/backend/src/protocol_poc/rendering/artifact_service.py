from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from protocol_poc.quality.models import QualityScorecard
from protocol_poc.rendering.docx_renderer import DocxRenderer, RenderSnapshot
from protocol_poc.rendering.scorecard import scorecard_html
from protocol_poc.rendering.traceability import traceability_csv


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class Artifact:
    kind: str
    filename: str
    media_type: str
    snapshot_id: str
    renderer_version: str
    created_at: str
    content: bytes
    sha256_hex: str

    def verify_integrity(self) -> bool:
        return sha256(self.content).hexdigest() == self.sha256_hex


class ArtifactService:
    def __init__(self, renderer_version: str) -> None:
        self.renderer_version = renderer_version

    def create(
        self,
        snapshot: RenderSnapshot,
        scorecard: QualityScorecard,
        template: bytes,
    ) -> list[Artifact]:
        created_at = datetime.now(timezone.utc).isoformat()
        contents = (
            (
                "protocol_docx",
                "protocol.docx",
                DOCX_MEDIA_TYPE,
                DocxRenderer(self.renderer_version).render(snapshot, template),
            ),
            (
                "traceability_csv",
                "traceability.csv",
                "text/csv; charset=utf-8",
                traceability_csv(snapshot.traceability_rows),
            ),
            (
                "scorecard_html",
                "scorecard.html",
                "text/html; charset=utf-8",
                scorecard_html(snapshot.snapshot_id, self.renderer_version, scorecard),
            ),
        )
        return [
            Artifact(
                kind,
                filename,
                media_type,
                snapshot.snapshot_id,
                self.renderer_version,
                created_at,
                content,
                sha256(content).hexdigest(),
            )
            for kind, filename, media_type, content in contents
        ]
