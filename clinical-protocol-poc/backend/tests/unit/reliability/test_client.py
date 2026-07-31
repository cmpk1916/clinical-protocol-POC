import json
from pathlib import Path

import httpx
import pytest

from protocol_poc.reliability.client import (
    DOCX_CONTENT_TYPE,
    PilotClient,
    PilotHttpError,
)


def test_client_sends_tenant_scoped_self_service_request_shapes(tmp_path: Path) -> None:
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        if request.url.path == "/api/export-artifacts/artifact-1":
            return httpx.Response(200, content=b"synthetic artifact")
        if request.url.path == "/api/studies":
            return httpx.Response(200, json={"id": "study-1"})
        return httpx.Response(200, json={"ok": True})

    document = tmp_path / "synopsis.docx"
    document.write_bytes(b"synthetic docx")
    export_command = {
        "expected_study_version": 3,
        "template_version_id": "template-v2",
        "template_hash": "a" * 64,
    }

    with PilotClient(
        "http://pilot.test",
        "pilot-tenant",
        "pilot-runner",
        transport=httpx.MockTransport(handler),
    ) as client:
        study = client.create_study("Synthetic standard")
        client.upload_input("study-1", "synopsis", document)
        client.get_workspace("study-1")
        client.process_synopsis("study-1", "synopsis-v1")
        client.get_review_queue("study-1")
        client.review_fact(
            "fact-1",
            action="approve",
            expected_version=2,
            explicitly_confirmed=True,
        )
        client.generate_passage("study-1", "study_design")
        client.list_passages("study-1")
        client.review_passage(
            "passage-1",
            action="edit",
            expected_version=1,
            text="Synthetic passage.",
            support_ids=("fact-1",),
        )
        client.preview_replacement(
            "study-1", "synopsis", proposed_version_id="synopsis-v2"
        )
        client.confirm_replacement(
            "study-1",
            "synopsis",
            proposed_version_id="synopsis-v2",
            expected_current_version_id="synopsis-v1",
            expected_study_version=2,
        )
        client.create_export("study-1", export_command)
        artifact = client.download_artifact("/api/export-artifacts/artifact-1")
        with pytest.raises(ValueError, match="outside the allowed route"):
            client.download_artifact("/test/reset")

    assert study["id"] == "study-1"
    assert artifact == b"synthetic artifact"
    assert [(request.method, request.url.path) for request in recorded] == [
        ("POST", "/api/studies"),
        ("POST", "/api/studies/study-1/inputs"),
        ("GET", "/api/studies/study-1/workspace"),
        ("POST", "/api/studies/study-1/inputs/synopsis-v1/process"),
        ("GET", "/api/studies/study-1/fact-review"),
        ("POST", "/api/facts/fact-1/review"),
        ("POST", "/api/studies/study-1/passages"),
        ("GET", "/api/studies/study-1/passages"),
        ("POST", "/api/passages/passage-1/review"),
        ("POST", "/api/studies/study-1/inputs/synopsis/replacement-preview"),
        ("POST", "/api/studies/study-1/inputs/synopsis/replacement-confirmation"),
        ("POST", "/api/studies/study-1/exports"),
        ("GET", "/api/export-artifacts/artifact-1"),
    ]
    assert all(request.headers["X-Tenant-ID"] == "pilot-tenant" for request in recorded)
    assert all(request.headers["X-Actor-ID"] == "pilot-runner" for request in recorded)
    assert all(not request.url.path.startswith("/test") for request in recorded)
    assert json.loads(recorded[0].content) == {"name": "Synthetic standard"}
    upload_body = recorded[1].content
    assert b'name="role"' in upload_body and b"synopsis" in upload_body
    assert b'filename="synopsis.docx"' in upload_body
    assert b"synthetic docx" in upload_body
    assert DOCX_CONTENT_TYPE.encode() in upload_body
    assert recorded[3].content == b""
    assert json.loads(recorded[5].content) == {
        "action": "approve",
        "expected_version": 2,
        "explicitly_confirmed": True,
        "value": None,
        "rationale": "",
    }
    assert json.loads(recorded[8].content) == {
        "action": "edit",
        "expected_version": 1,
        "text": "Synthetic passage.",
        "support_ids": ["fact-1"],
        "rationale": "",
    }
    assert json.loads(recorded[6].content) == {"section": "study_design"}
    assert json.loads(recorded[9].content) == {
        "proposed_version_id": "synopsis-v2",
    }
    assert json.loads(recorded[10].content) == {
        "proposed_version_id": "synopsis-v2",
        "expected_current_version_id": "synopsis-v1",
        "expected_study_version": 2,
    }
    assert json.loads(recorded[11].content) == export_command


def test_client_raises_structured_error_for_expected_export_denial() -> None:
    payload = {
        "detail": {
            "code": "EXPORT_BLOCKED",
            "blockers": ["UNSUPPORTED_CONTENT"],
        }
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json=payload)

    with PilotClient(
        "http://pilot.test",
        "pilot-tenant",
        "pilot-runner",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(PilotHttpError) as captured:
            client.create_export(
                "study-1",
                {
                    "expected_study_version": 1,
                    "template_version_id": "template-v1",
                    "template_hash": "a" * 64,
                },
            )

    assert (captured.value.status_code, captured.value.code) == (
        409,
        "EXPORT_BLOCKED",
    )
    assert captured.value.payload["detail"] == payload["detail"]


def test_injected_http_client_remains_owned_by_the_caller() -> None:
    injected = httpx.Client(
        base_url="http://injected.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"id": "study-1"})
        ),
    )

    with PilotClient(
        "http://ignored.test",
        "pilot-tenant",
        "pilot-runner",
        http_client=injected,
    ) as client:
        assert client.create_study("Synthetic study")["id"] == "study-1"

    assert injected.is_closed is False
    injected.close()
