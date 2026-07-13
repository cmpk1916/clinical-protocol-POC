from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, cast
from xml.etree import ElementTree
from zipfile import ZipFile

from protocol_poc.rendering.scorecard import DISCLAIMER
from protocol_poc.rendering.template_map import (
    build_template,
    deterministic_package,
    replace_unique_disclaimer,
    replace_unique_target,
)


@dataclass(frozen=True)
class RenderSnapshot:
    snapshot_id: str
    passages: dict[str, str]
    traceability_rows: list[dict[str, Any]] = field(default_factory=list)


class DocxRenderer:
    def __init__(self, renderer_version: str) -> None:
        self.renderer_version = renderer_version

    def render(self, snapshot: RenderSnapshot, template: bytes | None = None) -> bytes:
        package = template or build_template(list(snapshot.passages))
        with ZipFile(BytesIO(package)) as archive:
            entries = {name: archive.read(name) for name in archive.namelist() if not name.startswith("docProps/")}
        document = entries["word/document.xml"].decode("utf-8")
        document = replace_unique_disclaimer(document, DISCLAIMER)
        for section, text in snapshot.passages.items():
            document = replace_unique_target(document, section, text)
        entries["word/document.xml"] = document.encode("utf-8")
        return deterministic_package(entries)


def canonical_docx_xml(content: bytes) -> bytes:
    with ZipFile(BytesIO(content)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return cast(bytes, ElementTree.tostring(root, encoding="utf-8"))
