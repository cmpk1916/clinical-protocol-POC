from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from protocol_poc.rendering.docx_renderer import DocxRenderer, RenderSnapshot
from protocol_poc.rendering.traceability import traceability_json


@dataclass
class Artifact:
    kind: str
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

    def create(self, snapshot: RenderSnapshot, scorecard: dict[str, Any]) -> list[Artifact]:
        created_at = datetime.now(timezone.utc).isoformat()
        contents = {
            "protocol_docx": DocxRenderer(self.renderer_version).render(snapshot),
            "traceability_json": traceability_json(snapshot.traceability_rows),
            "scorecard_json": json.dumps(scorecard, sort_keys=True, separators=(",", ":")).encode(),
        }
        return [
            Artifact(kind, snapshot.snapshot_id, self.renderer_version, created_at, content, sha256(content).hexdigest())
            for kind, content in contents.items()
        ]
