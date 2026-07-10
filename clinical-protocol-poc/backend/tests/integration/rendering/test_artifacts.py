from protocol_poc.rendering.artifact_service import ArtifactService
from protocol_poc.rendering.docx_renderer import RenderSnapshot


def test_artifact_set_uses_one_snapshot_and_verified_hashes() -> None:
    snapshot = RenderSnapshot(
        "snapshot-a",
        {"study_design": "Participants receive 10 mg daily."},
        traceability_rows=[{
            "section": "study_design", "passage": "Participants receive 10 mg daily.",
            "claim": "dose", "fact_value": "10 mg", "evidence_location": "paragraph 3",
            "guidance_release": "release-1", "review_state": "accepted", "validation_status": "pass",
        }],
    )
    artifacts = ArtifactService("renderer-v1").create(snapshot, {"export_status": "eligible"})
    assert {item.kind for item in artifacts} == {"protocol_docx", "traceability_json", "scorecard_json"}
    assert {item.snapshot_id for item in artifacts} == {"snapshot-a"}
    assert {item.renderer_version for item in artifacts} == {"renderer-v1"}
    assert all(item.verify_integrity() for item in artifacts)


def test_tampered_artifact_fails_integrity_verification() -> None:
    artifact = ArtifactService("renderer-v1").create(RenderSnapshot("snapshot-a", {}), {})[0]
    artifact.content += b"tampered"
    assert artifact.verify_integrity() is False
