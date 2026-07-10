from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import cast
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
OFFICE_REL_TYPES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
}
WORD_MAIN_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
}
MACRO_MAIN_TYPES = {
    "application/vnd.ms-word.document.macroenabled.main+xml",
    "application/vnd.ms-word.template.macroenabledtemplate.main+xml",
}
MACRO_NAMES = ("vbaproject", "vbadata", "vbasignature", "vbaprojectsignature")
MACRO_CONTENT_MARKERS = ("macroenabled", "vba", "ms-office.vba")


class UnsafeDocumentError(ValueError):
    """A stable, non-content-bearing error for an unsafe DOCX package."""


@dataclass(frozen=True, slots=True)
class DocxLimits:
    max_upload_bytes: int = 25 * 1024 * 1024
    max_entries: int = 1_000
    max_entry_bytes: int = 10 * 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024
    max_compression_ratio: float = 100.0


@dataclass(frozen=True, slots=True)
class EvidenceLocation:
    part: str
    kind: str
    index: int | None = None
    table: int | None = None
    row: int | None = None
    cell: int | None = None
    paragraph: int | None = None
    container_path: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedEvidence:
    location: EvidenceLocation
    text: str


class DocxParser:
    def __init__(self, limits: DocxLimits | None = None) -> None:
        self._limits = limits or DocxLimits()

    def parse(self, source: bytes) -> list[ParsedEvidence]:
        if len(source) > self._limits.max_upload_bytes:
            raise UnsafeDocumentError("upload size limit exceeded")
        if not source.startswith(b"PK"):
            raise UnsafeDocumentError("invalid ZIP signature")
        try:
            with ZipFile(BytesIO(source)) as package:
                names = self._validate_directory(package)
                if not {"[Content_Types].xml", "_rels/.rels"}.issubset(names):
                    raise UnsafeDocumentError("required Word package parts missing")
                parsed: dict[str, Element] = {}
                for name in sorted(names):
                    if name.lower().endswith((".xml", ".rels")):
                        parsed[name] = self._parse_xml(self._read_bounded(package, name))
                self._reject_external_relationships(parsed)
                main_part = self._resolve_main_part(parsed["_rels/.rels"], names)
                self._validate_content_types(parsed["[Content_Types].xml"], main_part)
                document = parsed.get(main_part)
                if document is None:
                    raise UnsafeDocumentError("main document XML missing")
        except UnsafeDocumentError:
            raise
        except (BadZipFile, DefusedXmlException, ParseError, OSError, RuntimeError, ValueError) as exc:
            raise UnsafeDocumentError("malformed DOCX package") from exc
        return self._extract(document, main_part)

    def _validate_directory(self, package: ZipFile) -> set[str]:
        infos = package.infolist()
        if len(infos) > self._limits.max_entries:
            raise UnsafeDocumentError("ZIP entry count limit exceeded")
        seen: set[str] = set()
        total = 0
        for info in infos:
            path = PurePosixPath(info.filename)
            if not info.filename or "\\" in info.filename or info.filename.startswith("/") or ".." in path.parts:
                raise UnsafeDocumentError("unsafe ZIP member path")
            normalized = str(path)
            if normalized in seen:
                raise UnsafeDocumentError("duplicate normalized ZIP member path")
            seen.add(normalized)
            if info.flag_bits & 0x1:
                raise UnsafeDocumentError("encrypted ZIP entry rejected")
            lower_name = normalized.lower()
            if any(marker in lower_name for marker in MACRO_NAMES):
                raise UnsafeDocumentError("macro artifact rejected")
            if info.file_size > self._limits.max_entry_bytes:
                raise UnsafeDocumentError("ZIP entry size limit exceeded")
            total += info.file_size
            if total > self._limits.max_total_bytes:
                raise UnsafeDocumentError("ZIP total size limit exceeded")
            if info.file_size and (info.compress_size == 0 or info.file_size / info.compress_size > self._limits.max_compression_ratio):
                raise UnsafeDocumentError("ZIP compression ratio limit exceeded")
        return seen

    def _read_bounded(self, package: ZipFile, name: str) -> bytes:
        with package.open(name) as stream:
            data = stream.read(self._limits.max_entry_bytes + 1)
        if len(data) > self._limits.max_entry_bytes:
            raise UnsafeDocumentError("ZIP entry size limit exceeded")
        return data

    @staticmethod
    def _parse_xml(data: bytes) -> Element:
        try:
            return cast(Element, ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True))
        except DefusedXmlException as exc:
            raise UnsafeDocumentError("DTD or entity declarations rejected") from exc

    @staticmethod
    def _reject_external_relationships(parsed: dict[str, Element]) -> None:
        for name, root in parsed.items():
            if not name.lower().endswith(".rels"):
                continue
            for relationship in root.findall(f"{REL_NS}Relationship"):
                if relationship.attrib.get("TargetMode", "").casefold() == "external":
                    raise UnsafeDocumentError("external relationship rejected")

    @staticmethod
    def _resolve_main_part(root: Element, names: set[str]) -> str:
        relationships = [item for item in root.findall(f"{REL_NS}Relationship") if item.attrib.get("Type") in OFFICE_REL_TYPES]
        if len(relationships) != 1:
            raise UnsafeDocumentError("exactly one officeDocument relationship required")
        relationship = relationships[0]
        if relationship.attrib.get("TargetMode", "Internal").casefold() != "internal":
            raise UnsafeDocumentError("external relationship rejected")
        target = relationship.attrib.get("Target", "")
        path = PurePosixPath(target)
        if not target or target.startswith("/") or "\\" in target or ".." in path.parts or ":" in target:
            raise UnsafeDocumentError("invalid officeDocument relationship target")
        normalized = str(path)
        if normalized not in names:
            raise UnsafeDocumentError("officeDocument target missing")
        return normalized

    @staticmethod
    def _validate_content_types(root: Element, main_part: str) -> None:
        overrides: dict[str, str] = {}
        content_values: list[str] = []
        for item in root:
            content_type = item.attrib.get("ContentType", "").casefold()
            content_values.append(content_type)
            if item.tag == f"{CT_NS}Override":
                overrides[item.attrib.get("PartName", "").lstrip("/")] = content_type
        if any(marker in value for value in content_values for marker in MACRO_CONTENT_MARKERS):
            raise UnsafeDocumentError("macro-enabled content type rejected")
        main_type = overrides.get(main_part)
        if main_type in MACRO_MAIN_TYPES:
            raise UnsafeDocumentError("macro-enabled main document rejected")
        if main_type not in WORD_MAIN_TYPES:
            raise UnsafeDocumentError("invalid Word main document content type")

    @staticmethod
    def _text(paragraph: Element) -> str:
        return " ".join("".join(node.text or "" for node in paragraph.iter(f"{WORD_NS}t")).split())

    def _extract(self, document: Element, main_part: str) -> list[ParsedEvidence]:
        body = document.find(f"{WORD_NS}body")
        if body is None:
            raise UnsafeDocumentError("malformed Word document XML")
        result: list[ParsedEvidence] = []
        counters = {"paragraph": 0, "table": 0}
        self._walk_blocks(list(body), main_part, (), result, counters, None)
        return result

    def _walk_blocks(
        self,
        children: list[Element],
        main_part: str,
        path: tuple[int, ...],
        result: list[ParsedEvidence],
        counters: dict[str, int],
        cell_coordinates: tuple[int, int, int] | None,
    ) -> None:
        cell_paragraph = 0
        for child_index, child in enumerate(children):
            child_path = (*path, child_index)
            if child.tag == f"{WORD_NS}p":
                text_value = self._text(child)
                if cell_coordinates is None:
                    location = EvidenceLocation(main_part, "paragraph", index=counters["paragraph"], container_path=child_path)
                    counters["paragraph"] += 1
                else:
                    table, row_number, cell_number = cell_coordinates
                    location = EvidenceLocation(main_part, "table_cell", table=table, row=row_number, cell=cell_number, paragraph=cell_paragraph, container_path=child_path)
                    cell_paragraph += 1
                if text_value:
                    result.append(ParsedEvidence(location, text_value))
            elif child.tag == f"{WORD_NS}tbl":
                table_index = counters["table"]
                counters["table"] += 1
                for row_index, row in enumerate(child.findall(f"{WORD_NS}tr")):
                    for cell_index, cell in enumerate(row.findall(f"{WORD_NS}tc")):
                        self._walk_blocks(list(cell), main_part, (*child_path, row_index, cell_index), result, counters, (table_index, row_index, cell_index))
            elif child.tag == f"{WORD_NS}sdt":
                content = child.find(f"{WORD_NS}sdtContent")
                if content is None:
                    if any(True for _ in child.iter(f"{WORD_NS}t")):
                        raise UnsafeDocumentError("unsupported text-bearing structure")
                    continue
                self._walk_blocks(list(content), main_part, child_path, result, counters, cell_coordinates)
            elif child.tag == f"{WORD_NS}sectPr":
                continue
            elif any(True for _ in child.iter(f"{WORD_NS}t")):
                raise UnsafeDocumentError("unsupported text-bearing structure")
