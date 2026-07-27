"""Build the deterministic DOCX inputs accepted by the self-service workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend" / "src"))

from protocol_poc.rendering.template_map import build_template, deterministic_package  # noqa: E402


def _paragraph(text: str, style: str | None = None) -> str:
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{properties}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def build_synopsis() -> bytes:
    paragraphs = (
        _paragraph("Study identity", "Heading1"),
        _paragraph("Short title: SELF-24"),
        _paragraph("Objectives", "Heading1"),
        _paragraph("Objective: Evaluate synthetic symptom-score change"),
        _paragraph("Endpoints", "Heading1"),
        _paragraph("Endpoint: Change from baseline at Week 24"),
        _paragraph("Arms and interventions", "Heading1"),
        _paragraph("Arm: Treatment; Intervention: Synthetic Compound 10 mg once daily"),
        _paragraph("Population", "Heading1"),
        _paragraph("Population: Adults with synthetic condition X"),
        _paragraph("Eligibility", "Heading1"),
        _paragraph("Eligibility: Adults aged 18 through 75 years"),
        _paragraph("Duration: 24 weeks"),
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<w:body>"
        f"{''.join(paragraphs)}"
        '<w:sectPr><w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    ).encode()
    template_entries = build_template([])
    from io import BytesIO
    from zipfile import ZipFile

    with ZipFile(BytesIO(template_entries)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["word/document.xml"] = document
    return deterministic_package(entries)


def write_fixtures(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "synopsis.docx").write_bytes(build_synopsis())
    (output_directory / "template.docx").write_bytes(
        build_template(["synopsis", "objectives_endpoints", "study_design", "eligibility"])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir",
        type=Path,
        default=REPOSITORY_ROOT / "fixtures" / "self-service",
        help="directory for synopsis.docx and template.docx",
    )
    args = parser.parse_args()
    write_fixtures(args.outdir)


if __name__ == "__main__":
    main()
