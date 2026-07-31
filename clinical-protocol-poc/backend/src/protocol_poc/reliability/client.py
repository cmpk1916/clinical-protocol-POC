from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Literal, overload

import httpx


DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
InputRole = Literal["synopsis", "template"]
PassageSection = Literal[
    "synopsis", "objectives_endpoints", "study_design", "eligibility"
]
FactReviewAction = Literal[
    "approve",
    "correct_and_approve",
    "reject",
    "defer",
    "resume",
    "resolve_conflict",
]
PassageReviewAction = Literal["accept", "edit", "reject", "regenerate"]


class PilotHttpError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        payload: dict[str, object],
    ) -> None:
        super().__init__(f"pilot HTTP request failed: {status_code} {code}")
        self.status_code = status_code
        self.code = code
        self.payload = payload


class PilotClient:
    def __init__(
        self,
        base_url: str,
        tenant_id: str,
        actor_id: str,
        transport: httpx.BaseTransport | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if transport is not None and http_client is not None:
            raise ValueError("transport and http_client cannot both be provided")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=base_url,
            transport=transport,
            timeout=30.0,
        )
        self._identity_headers = {
            "X-Tenant-ID": tenant_id,
            "X-Actor-ID": actor_id,
        }

    def __enter__(self) -> PilotClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._owns_client:
            self._client.close()

    @overload
    def _request(
        self,
        method: str,
        path: str,
        *,
        binary: Literal[False] = False,
        **kwargs: object,
    ) -> dict[str, object]: ...

    @overload
    def _request(
        self,
        method: str,
        path: str,
        *,
        binary: Literal[True],
        **kwargs: object,
    ) -> bytes: ...

    def _request(
        self,
        method: str,
        path: str,
        *,
        binary: bool = False,
        **kwargs: object,
    ) -> dict[str, object] | bytes:
        response = self._client.request(
            method,
            path,
            headers=self._identity_headers,
            **kwargs,  # type: ignore[arg-type]
        )
        try:
            raw_payload: object = response.json()
        except ValueError:
            raw_payload = None
        payload = (
            {str(key): value for key, value in raw_payload.items()}
            if isinstance(raw_payload, dict)
            else {"body": response.text if raw_payload is None else raw_payload}
        )
        if response.is_error:
            detail = payload.get("detail", {})
            code = (
                detail.get("code", "HTTP_ERROR")
                if isinstance(detail, dict)
                else "HTTP_ERROR"
            )
            raise PilotHttpError(response.status_code, str(code), payload)
        if binary:
            return response.content
        if not isinstance(raw_payload, dict):
            raise PilotHttpError(response.status_code, "INVALID_RESPONSE", payload)
        return payload

    def create_study(self, name: str) -> dict[str, object]:
        return self._request("POST", "/api/studies", json={"name": name})

    def upload_input(
        self,
        study_id: str,
        role: InputRole,
        path: Path,
    ) -> dict[str, object]:
        files = {"file": (path.name, path.read_bytes(), DOCX_CONTENT_TYPE)}
        return self._request(
            "POST",
            f"/api/studies/{study_id}/inputs",
            data={"role": role},
            files=files,
        )

    def get_workspace(self, study_id: str) -> dict[str, object]:
        return self._request("GET", f"/api/studies/{study_id}/workspace")

    def process_synopsis(
        self, study_id: str, file_version_id: str
    ) -> dict[str, object]:
        return self._request(
            "POST", f"/api/studies/{study_id}/inputs/{file_version_id}/process"
        )

    def get_review_queue(self, study_id: str) -> dict[str, object]:
        return self._request("GET", f"/api/studies/{study_id}/fact-review")

    def review_fact(
        self,
        fact_id: str,
        *,
        action: FactReviewAction,
        expected_version: int,
        explicitly_confirmed: bool = False,
        value: dict[str, object] | None = None,
        rationale: str = "",
    ) -> dict[str, object]:
        return self._request(
            "POST",
            f"/api/facts/{fact_id}/review",
            json={
                "action": action,
                "expected_version": expected_version,
                "explicitly_confirmed": explicitly_confirmed,
                "value": value,
                "rationale": rationale,
            },
        )

    def generate_passage(
        self, study_id: str, section: PassageSection
    ) -> dict[str, object]:
        return self._request(
            "POST",
            f"/api/studies/{study_id}/passages",
            json={"section": section},
        )

    def list_passages(self, study_id: str) -> dict[str, object]:
        return self._request("GET", f"/api/studies/{study_id}/passages")

    def review_passage(
        self,
        passage_id: str,
        *,
        action: PassageReviewAction,
        expected_version: int,
        text: str = "",
        support_ids: tuple[str, ...] = (),
        rationale: str = "",
    ) -> dict[str, object]:
        return self._request(
            "POST",
            f"/api/passages/{passage_id}/review",
            json={
                "action": action,
                "expected_version": expected_version,
                "text": text,
                "support_ids": list(support_ids),
                "rationale": rationale,
            },
        )

    def preview_replacement(
        self,
        study_id: str,
        role: InputRole,
        *,
        proposed_version_id: str,
    ) -> dict[str, object]:
        return self._request(
            "POST",
            f"/api/studies/{study_id}/inputs/{role}/replacement-preview",
            json={"proposed_version_id": proposed_version_id},
        )

    def confirm_replacement(
        self,
        study_id: str,
        role: InputRole,
        *,
        proposed_version_id: str,
        expected_current_version_id: str,
        expected_study_version: int,
    ) -> dict[str, object]:
        return self._request(
            "POST",
            f"/api/studies/{study_id}/inputs/{role}/replacement-confirmation",
            json={
                "proposed_version_id": proposed_version_id,
                "expected_current_version_id": expected_current_version_id,
                "expected_study_version": expected_study_version,
            },
        )

    def create_export(
        self, study_id: str, command: dict[str, object]
    ) -> dict[str, object]:
        return self._request(
            "POST", f"/api/studies/{study_id}/exports", json=command
        )

    def download_artifact(self, download_url: str) -> bytes:
        prefix = "/api/export-artifacts/"
        artifact_id = download_url.removeprefix(prefix)
        if (
            not download_url.startswith(prefix)
            or not artifact_id
            or "/" in artifact_id
            or "?" in artifact_id
            or "#" in artifact_id
        ):
            raise ValueError("artifact download URL is outside the allowed route")
        return self._request("GET", download_url, binary=True)
