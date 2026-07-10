from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from protocol_poc.ingest.docx_parser import DocxLimits, DocxParser, UnsafeDocumentError


CONTENT_TYPES = b'''<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="xml" ContentType="application/xml"/>
 <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
ROOT_RELS = b'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''


def make_docx(document: bytes, extra: dict[str, bytes] | None = None) -> bytes:
    output = BytesIO()
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": document,
        **(extra or {}),
    }
    with ZipFile(output, "w", ZIP_DEFLATED) as package:
        for name, data in parts.items():
            package.writestr(name, data)
    return output.getvalue()


DOCUMENT = b'''<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
 <w:p><w:r><w:t> First  paragraph </w:t></w:r></w:p>
 <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell text</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>'''


def test_parser_preserves_paragraph_and_table_locations() -> None:
    evidence = DocxParser().parse(make_docx(DOCUMENT))
    assert evidence[0].location.kind == "paragraph"
    assert evidence[0].location.index == 0
    assert evidence[0].text == "First paragraph"
    assert any(item.location.kind == "table_cell" for item in evidence)
    cell = evidence[1]
    assert (cell.location.table, cell.location.row, cell.location.cell, cell.location.paragraph) == (0, 0, 0, 0)
    assert [item.text for item in evidence] == ["First paragraph", "Cell text"]


def test_parser_keeps_mixed_order_distinct_cell_paragraphs_and_filters_empty() -> None:
    document = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:p/><w:p><w:r><w:t>before</w:t></w:r></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell one</w:t></w:r></w:p><w:p/><w:p><w:r><w:t>cell two</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
      <w:p><w:r><w:t>after</w:t></w:r></w:p>
    </w:body></w:document>'''
    evidence = DocxParser().parse(make_docx(document))
    assert [item.text for item in evidence] == ["before", "cell one", "cell two", "after"]
    assert evidence[0].location.index == 1
    assert (evidence[1].location.table, evidence[1].location.row, evidence[1].location.cell, evidence[1].location.paragraph) == (0, 0, 0, 0)
    assert evidence[2].location.paragraph == 2
    assert evidence[3].location.index == 2


def test_parser_traverses_content_controls_and_nested_tables_in_order() -> None:
    document = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:sdt><w:sdtContent><w:p><w:r><w:t>controlled</w:t></w:r></w:p></w:sdtContent></w:sdt>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>outer</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>nested</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''
    evidence = DocxParser().parse(make_docx(document))
    assert [item.text for item in evidence] == ["controlled", "outer", "nested"]
    assert evidence[0].location.container_path == (0, 0)
    assert evidence[2].location.table == 1
    assert evidence[2].location.container_path != evidence[1].location.container_path


def test_parser_fails_closed_for_unsupported_text_bearing_block() -> None:
    document = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:custom><w:r><w:t>hidden</w:t></w:r></w:custom></w:body></w:document>'''
    with pytest.raises(UnsafeDocumentError, match="unsupported text-bearing"):
        DocxParser().parse(make_docx(document))


def test_parser_rejects_external_relationships() -> None:
    rels = b'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="https://evil.invalid" TargetMode="External"/>
    </Relationships>'''
    with pytest.raises(UnsafeDocumentError, match="external relationship"):
        DocxParser().parse(make_docx(DOCUMENT, {"word/_rels/document.xml.rels": rels}))


@pytest.mark.parametrize("name", ["../escape", "/absolute", "word\\bad.xml"])
def test_parser_rejects_unsafe_member_paths(name: str) -> None:
    with pytest.raises(UnsafeDocumentError, match="path"):
        DocxParser().parse(make_docx(DOCUMENT, {name: b"x"}))


def test_parser_rejects_macros() -> None:
    with pytest.raises(UnsafeDocumentError, match="macro"):
        DocxParser().parse(make_docx(DOCUMENT, {"word/vbaProject.bin": b"macro"}))


def test_parser_rejects_dtd() -> None:
    with pytest.raises(UnsafeDocumentError, match="DTD or entity"):
        DocxParser().parse(make_docx(b'<!DOCTYPE x [<!ENTITY x "bad">]><x>&x;</x>'))


def test_parser_rejects_bad_signature_and_missing_parts() -> None:
    with pytest.raises(UnsafeDocumentError, match="ZIP"):
        DocxParser().parse(b"not a zip")
    empty = BytesIO()
    with ZipFile(empty, "w"):
        pass
    with pytest.raises(UnsafeDocumentError, match="required"):
        DocxParser().parse(empty.getvalue())


def test_parser_rejects_missing_or_external_office_document_relationship() -> None:
    with pytest.raises(UnsafeDocumentError, match="officeDocument"):
        DocxParser().parse(make_docx(DOCUMENT, {"_rels/.rels": b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/> '}))
    external = ROOT_RELS.replace(b'Target="word/document.xml"', b'Target="https://evil.invalid" TargetMode="External"')
    with pytest.raises(UnsafeDocumentError, match="external relationship"):
        DocxParser().parse(make_docx(DOCUMENT, {"_rels/.rels": external}))


def test_parser_rejects_wrong_main_content_type_and_malformed_other_xml() -> None:
    wrong = CONTENT_TYPES.replace(b"wordprocessingml.document.main+xml", b"application/xml")
    with pytest.raises(UnsafeDocumentError, match="content type"):
        DocxParser().parse(make_docx(DOCUMENT, {"[Content_Types].xml": wrong}))
    with pytest.raises(UnsafeDocumentError, match="malformed"):
        DocxParser().parse(make_docx(DOCUMENT, {"customXml/item.xml": b"<broken>"}))


@pytest.mark.parametrize("artifact", ["word/vbaData.xml", "word/_xmlsignatures/vbaProjectSignature.bin", "WORD/VBAPROJECT.BIN"])
def test_parser_rejects_macro_artifact_variants(artifact: str) -> None:
    with pytest.raises(UnsafeDocumentError, match="macro"):
        DocxParser().parse(make_docx(DOCUMENT, {artifact: b"x"}))


def test_parser_enforces_declared_uncompressed_limits() -> None:
    parser = DocxParser(DocxLimits(max_entry_bytes=50, max_total_bytes=100))
    with pytest.raises(UnsafeDocumentError, match="entry size"):
        parser.parse(make_docx(DOCUMENT))


def test_parser_enforces_upload_entry_total_and_ratio_limits() -> None:
    package = make_docx(DOCUMENT)
    with pytest.raises(UnsafeDocumentError, match="upload size"):
        DocxParser(DocxLimits(max_upload_bytes=len(package) - 1)).parse(package)
    with pytest.raises(UnsafeDocumentError, match="entry count"):
        DocxParser(DocxLimits(max_entries=2)).parse(package)
    with pytest.raises(UnsafeDocumentError, match="total size"):
        DocxParser(DocxLimits(max_total_bytes=100, max_entry_bytes=10_000)).parse(package)
    with pytest.raises(UnsafeDocumentError, match="compression ratio"):
        DocxParser(DocxLimits(max_compression_ratio=1.0)).parse(package)


def test_parser_rejects_duplicate_normalized_names() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", ROOT_RELS)
        package.writestr("word/document.xml", DOCUMENT)
        package.writestr("word/./document.xml", DOCUMENT)
    with pytest.raises(UnsafeDocumentError, match="duplicate normalized"):
        DocxParser().parse(output.getvalue())


def test_directory_validation_rejects_encrypted_flag() -> None:
    class EncryptedInfo:
        filename = "word/document.xml"
        flag_bits = 0x1
        file_size = 1
        compress_size = 1

    class PackageDirectory:
        def infolist(self) -> list[EncryptedInfo]:
            return [EncryptedInfo()]

    with pytest.raises(UnsafeDocumentError, match="encrypted"):
        DocxParser()._validate_directory(PackageDirectory())  # type: ignore[arg-type]
