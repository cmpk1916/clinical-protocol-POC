from protocol_poc.quality.models import DimensionResult, QualityBlocker, QualityScorecard
from protocol_poc.rendering.scorecard import scorecard_html


def test_scorecard_html_has_separate_dimensions_and_no_composite_claim() -> None:
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
    card = QualityScorecard(
        dimensions,
        (QualityBlocker("EXAMPLE_BLOCKER", "Escaped <message>"),),
        "blocked",
    )
    html = scorecard_html("snapshot-a", "renderer-v1", card).decode()
    assert html.startswith("<!doctype html>")
    assert html.count('class="dimension"') == 6
    assert "EXAMPLE_BLOCKER" in html
    assert "Escaped &lt;message&gt;" in html
    assert "Synthetic POC output only" in html
    forbidden = ("overall", "composite", "readiness percentage", "%")
    assert all(term not in html.casefold() for term in forbidden)
