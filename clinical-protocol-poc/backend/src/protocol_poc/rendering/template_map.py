from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


class TemplateMappingError(ValueError):
    pass


DISCLAIMER_TOKEN = "[[POC_DISCLAIMER]]"

SECTION_HEADINGS = {
    "synopsis": "Synopsis",
    "objectives_endpoints": "Objectives and Endpoints",
    "study_design": "Study Design",
    "eligibility": "Eligibility",
}


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


def replace_unique_disclaimer(document_xml: str, text: str) -> str:
    count = document_xml.count(DISCLAIMER_TOKEN)
    if count == 0:
        raise TemplateMappingError("missing POC disclaimer insertion point")
    if count > 1:
        raise TemplateMappingError("ambiguous POC disclaimer insertion point")
    return document_xml.replace(DISCLAIMER_TOKEN, escape(text))


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
    section_paragraphs = "".join(
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r>'
        f'<w:t>{escape(SECTION_HEADINGS.get(section, section.replace("_", " ").title()))}</w:t>'
        '</w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
        f'<w:r><w:t>{escape(insertion_token(section))}</w:t></w:r></w:p>'
        for section in sections
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<w:body>'
        '<w:p><w:pPr><w:pStyle w:val="POCTitle"/></w:pPr><w:r>'
        '<w:t>Synthetic Clinical Protocol</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="POCDisclaimer"/></w:pPr><w:r>'
        f'<w:t>{escape(DISCLAIMER_TOKEN)}</w:t></w:r></w:p>'
        f'{section_paragraphs}'
        '<w:sectPr><w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        '</w:body></w:document>'
    ).encode()
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>'
        '<w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
        '<w:spacing w:after="120" w:line="300" w:lineRule="auto"/>'
        '</w:pPr></w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        '<w:style w:type="paragraph" w:styleId="POCTitle"><w:name w:val="POC Title"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/>'
        '<w:spacing w:before="0" w:after="160"/></w:pPr><w:rPr><w:b/>'
        '<w:color w:val="17365D"/><w:sz w:val="40"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="POCDisclaimer">'
        '<w:name w:val="POC Disclaimer"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:jc w:val="center"/><w:spacing w:before="0" w:after="360"/></w:pPr>'
        '<w:rPr><w:i/><w:color w:val="9C0006"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:keepNext/><w:spacing w:before="360" w:after="200"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="2E74B5"/><w:sz w:val="32"/></w:rPr>'
        '</w:style></w:styles>'
    ).encode()
    header = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:rPr><w:b/>'
        '<w:color w:val="666666"/><w:sz w:val="18"/></w:rPr>'
        '<w:t>Synthetic Clinical Protocol POC</w:t></w:r></w:p></w:hdr>'
    ).encode()
    footer = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr>'
        '<w:color w:val="9C0006"/><w:sz w:val="16"/></w:rPr>'
        '<w:t>Not validated for clinical or regulatory use</w:t></w:r></w:p></w:ftr>'
    ).encode()
    return _write_zip({
        "[Content_Types].xml": b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>',
        "_rels/.rels": b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": document,
        "word/_rels/document.xml.rels": b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "word/header1.xml": header,
        "word/footer1.xml": footer,
        "word/styles.xml": styles,
    })


def deterministic_package(entries: dict[str, bytes]) -> bytes:
    return _write_zip(entries)
