from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


class TemplateMappingError(ValueError):
    pass


def insertion_token(section: str) -> str:
    return f"[[SECTION:{section}]]"


def replace_unique_target(document_xml: str, section: str, text: str) -> str:
    token = insertion_token(section)
    count = document_xml.count(token)
    if count == 0:
        raise TemplateMappingError(f"missing insertion point for {section}")
    if count > 1:
        raise TemplateMappingError(f"ambiguous insertion point for {section}")
    return document_xml.replace(token, escape(text))


def _write_zip(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, entries[name])
    return output.getvalue()


def build_template(sections: list[str]) -> bytes:
    paragraphs = "".join(
        f'<w:p><w:r><w:t>{escape(insertion_token(section))}</w:t></w:r></w:p>'
        for section in sections
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}<w:sectPr/></w:body></w:document>"
    ).encode()
    return _write_zip({
        "[Content_Types].xml": b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": document,
    })


def deterministic_package(entries: dict[str, bytes]) -> bytes:
    return _write_zip(entries)
