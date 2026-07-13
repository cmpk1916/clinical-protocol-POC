import pytest
from io import BytesIO
from zipfile import ZipFile

from protocol_poc.rendering.docx_renderer import DocxRenderer, RenderSnapshot, canonical_docx_xml
from protocol_poc.rendering.template_map import TemplateMappingError, build_template


def test_same_snapshot_and_renderer_version_produce_same_document_xml() -> None:
    renderer = DocxRenderer("renderer-v1")
    snapshot = RenderSnapshot("snapshot-a", {"study_design": "Participants receive 10 mg daily."})
    first = canonical_docx_xml(renderer.render(snapshot))
    second = canonical_docx_xml(renderer.render(snapshot))
    assert first == second


def test_ambiguous_insertion_point_blocks_render() -> None:
    template = build_template(["study_design", "study_design"])
    with pytest.raises(TemplateMappingError, match="ambiguous"):
        DocxRenderer("renderer-v1").render(
            RenderSnapshot("snapshot-a", {"study_design": "Text"}), template
        )


def test_generated_template_has_visible_structure_and_page_furniture() -> None:
    template = build_template(["synopsis", "objectives_endpoints", "study_design", "eligibility"])

    with ZipFile(BytesIO(template)) as package:
        document = package.read("word/document.xml").decode()
        header = package.read("word/header1.xml").decode()
        footer = package.read("word/footer1.xml").decode()
        styles = package.read("word/styles.xml").decode()

    assert "Synthetic Clinical Protocol" in document
    assert all(
        heading in document
        for heading in ("Synopsis", "Objectives and Endpoints", "Study Design", "Eligibility")
    )
    assert "Synthetic Clinical Protocol POC" in header
    assert "Not validated for clinical or regulatory use" in footer
    assert 'w:styleId="Heading1"' in styles
    assert '<w:spacing w:before="360" w:after="200"/>' in styles
    assert 'w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"' in document
