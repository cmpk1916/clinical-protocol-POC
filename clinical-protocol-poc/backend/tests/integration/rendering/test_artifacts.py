from io import BytesIO
from zipfile import ZipFile

from protocol_poc.quality.models import DimensionResult, QualityScorecard
from protocol_poc.rendering.artifact_service import ArtifactService
from protocol_poc.rendering.docx_renderer import RenderSnapshot
from protocol_poc.rendering.template_map import build_template


def scorecard() -> QualityScorecard:
    dimensions = {
        name: DimensionResult("pass", 1, 1)
        for name in (
            "completeness",
            "consistency",
            "traceability",
            "template_conformance",
            "writer_review_status",
            "approved_guidance_coverage",
        )
    }
    return QualityScorecard(dimensions, (), "eligible")


def snapshot() -> RenderSnapshot:
    return RenderSnapshot(
        "snapshot-a",
        {"study_design": "Participants receive 10 mg daily."},
        traceability_rows=[{
            "section": "study_design",
            "passage": "Participants receive 10 mg daily.",
            "claim": "dose",
            "fact_value": "10 mg",
            "evidence_location": "paragraph 3",
            "guidance_release": "release-1",
            "review_state": "accepted",
            "validation_status": "pass",
        }],
    )


def test_artifact_set_is_docx_csv_html_with_one_snapshot() -> None:
    artifacts = ArtifactService("renderer-v1").create(
        snapshot(), scorecard(), build_template(["study_design"])
    )
    assert [(item.filename, item.media_type) for item in artifacts] == [
        (
            "protocol.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("traceability.csv", "text/csv; charset=utf-8"),
        ("scorecard.html", "text/html; charset=utf-8"),
    ]
    assert {item.snapshot_id for item in artifacts} == {"snapshot-a"}
    assert {item.renderer_version for item in artifacts} == {"renderer-v1"}
    assert all(item.verify_integrity() for item in artifacts)

    docx = artifacts[0].content
    with ZipFile(BytesIO(docx)) as package:
        document_xml = package.read("word/document.xml").decode()
    assert "Participants receive 10 mg daily." in document_xml
    assert "Synthetic POC output only" in document_xml
    assert "[[" not in document_xml

    csv_text = artifacts[1].content.decode()
    assert csv_text.startswith(
        "section,passage,claim,fact_value,evidence_location,guidance_release,review_state,validation_status\n"
    )
    assert "paragraph 3" in csv_text

    html = artifacts[2].content.decode()
    assert 'data-snapshot-id="snapshot-a"' in html
    assert 'data-renderer-version="renderer-v1"' in html
    assert "Synthetic POC output only" in html


def test_artifacts_are_byte_deterministic_and_tampering_fails_integrity() -> None:
    service = ArtifactService("renderer-v1")
    template = build_template(["study_design"])
    first = service.create(snapshot(), scorecard(), template)
    second = service.create(snapshot(), scorecard(), template)
    assert [(item.content, item.sha256_hex) for item in first] == [
        (item.content, item.sha256_hex) for item in second
    ]
    first[0].content += b"tampered"
    assert first[0].verify_integrity() is False
