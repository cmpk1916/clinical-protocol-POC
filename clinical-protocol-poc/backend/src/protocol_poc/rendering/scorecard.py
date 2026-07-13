from html import escape

from protocol_poc.quality.models import QualityScorecard


DIMENSION_ORDER = (
    "completeness",
    "consistency",
    "traceability",
    "template_conformance",
    "writer_review_status",
    "approved_guidance_coverage",
)

DISCLAIMER = (
    "Synthetic POC output only; not validated and no clinical, regulatory, submission, "
    "operational, or readiness claim is made."
)


def scorecard_html(
    snapshot_id: str,
    renderer_version: str,
    scorecard: QualityScorecard,
) -> bytes:
    dimensions = "".join(
        _dimension_html(name, scorecard)
        for name in DIMENSION_ORDER
    )
    blockers = "".join(
        f"<li><code>{escape(item.code)}</code>: {escape(item.message)}</li>"
        for item in scorecard.blockers
    ) or "<li>None</li>"
    document = (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Synthetic protocol quality scorecard</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:60rem;margin:2rem auto;"
        "line-height:1.5;color:#17202a}table{border-collapse:collapse}"
        "th,td{border:1px solid #aeb6bf;padding:.55rem;text-align:left}"
        "th{background:#eaf2f8}.notice{border-left:.3rem solid #b03a2e;padding:.8rem;"
        "background:#fdedec}</style></head>"
        f'<body data-snapshot-id="{escape(snapshot_id, quote=True)}" '
        f'data-renderer-version="{escape(renderer_version, quote=True)}">'
        "<h1>Synthetic protocol quality scorecard</h1>"
        f'<p class="notice">{escape(DISCLAIMER)}</p>'
        f"<p>Snapshot: <code>{escape(snapshot_id)}</code></p>"
        f"<p>Renderer: <code>{escape(renderer_version)}</code></p>"
        f"<p>Export status: <strong>{escape(scorecard.export_status)}</strong></p>"
        "<table><thead><tr><th>Dimension</th><th>Status</th><th>Passed</th>"
        f"<th>Applicable</th><th>Findings</th></tr></thead><tbody>{dimensions}</tbody></table>"
        f"<h2>Blocking findings</h2><ul>{blockers}</ul>"
        "</body></html>"
    )
    return document.encode("utf-8")


def _dimension_html(name: str, scorecard: QualityScorecard) -> str:
    result = scorecard.dimensions[name]
    findings = ", ".join(result.finding_codes) or "None"
    return (
        '<tr class="dimension">'
        f"<th>{escape(name.replace('_', ' ').title())}</th>"
        f"<td>{escape(result.status)}</td>"
        f"<td>{result.passed_count}</td>"
        f"<td>{result.applicable_count}</td>"
        f"<td>{escape(findings)}</td>"
        "</tr>"
    )
