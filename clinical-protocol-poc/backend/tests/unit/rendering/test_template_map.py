import pytest

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
