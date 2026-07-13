from pathlib import Path
from io import BytesIO

import pytest

from protocol_poc.files.service import IndeterminateWriteError, LocalFileStorage, S3FileStorage


def test_local_storage_is_idempotent_and_never_overwrites(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    assert storage.put("safe/key.docx", b"first") is True
    assert storage.put("safe/key.docx", b"first") is False
    with pytest.raises(FileExistsError, match="collision"):
        storage.put("safe/key.docx", b"different")
    assert (tmp_path / "safe/key.docx").read_bytes() == b"first"
    assert list(tmp_path.rglob("*.tmp")) == []


def test_local_storage_requires_directory_fsync_before_success(tmp_path: Path) -> None:
    class FsyncFails(LocalFileStorage):
        called = False

        @staticmethod
        def _fsync_directory(path: Path) -> None:
            FsyncFails.called = True
            raise OSError("fsync failed")

    with pytest.raises(OSError, match="fsync"):
        FsyncFails(tmp_path).put("key.docx", b"data")
    assert FsyncFails.called
    assert not (tmp_path / "key.docx").exists()


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, IfNoneMatch: str, Metadata: dict[str, str]) -> object:
        if Key in self.objects:
            error = RuntimeError("precondition")
            error.code = "PreconditionFailed"  # type: ignore[attr-defined]
            raise error
        self.objects[Key] = (Body, Metadata)
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        return {"Metadata": self.objects[Key][1]}

    def delete_object(self, *, Bucket: str, Key: str) -> object:
        self.objects.pop(Key, None)
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        if Key not in self.objects:
            error = RuntimeError("missing")
            error.code = "NoSuchKey"  # type: ignore[attr-defined]
            raise error
        return {"Body": BytesIO(self.objects[Key][0])}


def test_s3_adapter_uses_conditional_create_and_checksum_idempotency() -> None:
    client = FakeS3()
    storage = S3FileStorage(client, "bucket")
    assert storage.put("server/key", b"first") is True
    assert storage.put("server/key", b"first") is False
    with pytest.raises(FileExistsError, match="collision"):
        storage.put("server/key", b"different")
    assert client.objects["server/key"][0] == b"first"


def test_s3_adapter_does_not_misclassify_provider_errors() -> None:
    class Denied(FakeS3):
        def put_object(self, **kwargs: object) -> object:
            error = RuntimeError("denied")
            error.code = "AccessDenied"  # type: ignore[attr-defined]
            raise error

    with pytest.raises(RuntimeError, match="denied"):
        S3FileStorage(Denied(), "bucket").put("key", b"data")


def test_s3_adapter_recovers_only_matching_ambiguous_timeout() -> None:
    class ReadTimeoutError(Exception):
        pass

    class TimedOut(FakeS3):
        def put_object(self, *, Bucket: str, Key: str, Body: bytes, IfNoneMatch: str, Metadata: dict[str, str]) -> object:
            self.objects[Key] = (Body, Metadata)
            raise ReadTimeoutError("unknown outcome")

    client = TimedOut()
    assert S3FileStorage(client, "bucket").put("key", b"data") is False


def test_s3_ambiguous_unresolved_head_is_indeterminate() -> None:
    class EndpointConnectionError(Exception):
        pass

    class Unresolved(FakeS3):
        def put_object(self, **kwargs: object) -> object:
            raise EndpointConnectionError("post-send outcome unknown")

        def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            raise EndpointConnectionError("head unavailable")

    with pytest.raises(IndeterminateWriteError) as captured:
        S3FileStorage(Unresolved(), "bucket").put("server/key", b"clinical bytes")
    assert captured.value.key == "server/key"
    assert len(captured.value.checksum_sha256) == 64
    assert "clinical bytes" not in str(captured.value)


def test_s3_ambiguous_different_checksum_is_collision() -> None:
    class ConnectTimeoutError(Exception):
        pass

    class Different(FakeS3):
        def put_object(self, **kwargs: object) -> object:
            self.objects["key"] = (b"other", {"sha256": "0" * 64})
            raise ConnectTimeoutError("unknown")

    with pytest.raises(FileExistsError, match="collision"):
        S3FileStorage(Different(), "bucket").put("key", b"data")


def test_local_storage_reads_exact_bytes_and_missing_is_none(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    storage.put("tenant/artifact.bin", b"exact bytes")
    assert storage.get("tenant/artifact.bin") == b"exact bytes"
    assert storage.get("tenant/missing.bin") is None
    with pytest.raises(ValueError, match="invalid storage key"):
        storage.get("../escape")


def test_s3_storage_reads_exact_bytes_and_missing_is_none() -> None:
    storage = S3FileStorage(FakeS3(), "bucket")
    storage.put("tenant/artifact.bin", b"exact bytes")
    assert storage.get("tenant/artifact.bin") == b"exact bytes"
    assert storage.get("tenant/missing.bin") is None
