from __future__ import annotations

from pathlib import Path
import hashlib
import os
import tempfile
from typing import Literal, Protocol


class FileStorage(Protocol):
    def put(self, key: str, data: bytes) -> bool: ...
    def get(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...
    def object_checksum(self, key: str) -> str | None: ...


class IndeterminateWriteError(RuntimeError):
    def __init__(self, key: str, checksum_sha256: str) -> None:
        super().__init__("storage write outcome is indeterminate")
        self.key = key
        self.checksum_sha256 = checksum_sha256


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        target = (self._root / key).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError("invalid storage key")
        return target

    def put(self, key: str, data: bytes) -> bool:
        target = self._path(key)
        if target.exists():
            if target.read_bytes() != data:
                raise FileExistsError("storage key collision")
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        published = False
        try:
            with tempfile.NamedTemporaryFile(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
                published = True
            except FileExistsError:
                if target.read_bytes() == data:
                    return False
                raise FileExistsError("storage key collision") from None
            try:
                self._fsync_directory(target.parent)
            except Exception:
                if published:
                    target.unlink(missing_ok=True)
                raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return True

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def get(self, key: str) -> bytes | None:
        target = self._path(key)
        return target.read_bytes() if target.exists() else None

    def object_checksum(self, key: str) -> str | None:
        target = self._path(key)
        if not target.exists():
            return None
        return hashlib.sha256(target.read_bytes()).hexdigest()


class S3Client(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: bytes, IfNoneMatch: str, Metadata: dict[str, str]) -> object: ...
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]: ...
    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]: ...
    def delete_object(self, *, Bucket: str, Key: str) -> object: ...


class StorageErrorClassifier(Protocol):
    def classify_put(self, exc: Exception) -> Literal["precondition", "ambiguous", "other"]: ...
    def classify_head(self, exc: Exception) -> Literal["not_found", "ambiguous", "other"]: ...


class S3ErrorClassifier:
    _ambiguous_names = {"ReadTimeoutError", "ConnectTimeoutError", "EndpointConnectionError"}

    def classify_put(self, exc: Exception) -> Literal["precondition", "ambiguous", "other"]:
        code = self.error_code(exc)
        if code in {"412", "PreconditionFailed"}:
            return "precondition"
        if isinstance(exc, TimeoutError) or type(exc).__name__ in self._ambiguous_names:
            return "ambiguous"
        return "other"

    def classify_head(self, exc: Exception) -> Literal["not_found", "ambiguous", "other"]:
        code = self.error_code(exc)
        if code in {"404", "NoSuchKey", "NotFound"}:
            return "not_found"
        if isinstance(exc, TimeoutError) or type(exc).__name__ in self._ambiguous_names:
            return "ambiguous"
        return "other"

    @staticmethod
    def error_code(exc: Exception) -> str | None:
        direct = getattr(exc, "code", None)
        if isinstance(direct, (str, int)):
            return str(direct)
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            error = response.get("Error")
            if isinstance(error, dict):
                code = error.get("Code")
                if isinstance(code, (str, int)):
                    return str(code)
        return None


class S3FileStorage:
    """S3-compatible adapter; a configured client is injected by the deployment."""

    def __init__(self, client: S3Client, bucket: str, classifier: StorageErrorClassifier | None = None) -> None:
        self._client, self._bucket = client, bucket
        self._classifier = classifier or S3ErrorClassifier()

    def put(self, key: str, data: bytes) -> bool:
        checksum = hashlib.sha256(data).hexdigest()
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data, IfNoneMatch="*", Metadata={"sha256": checksum})
        except Exception as exc:
            classification = self._classifier.classify_put(exc)
            if classification == "other":
                raise
            try:
                existing = self._client.head_object(Bucket=self._bucket, Key=key)
            except Exception as head_exc:
                head_classification = self._classifier.classify_head(head_exc)
                if classification == "ambiguous" and head_classification in {"not_found", "ambiguous"}:
                    raise IndeterminateWriteError(key, checksum) from None
                raise exc
            metadata = existing.get("Metadata")
            if isinstance(metadata, dict) and metadata.get("sha256") == checksum:
                return False
            raise FileExistsError("storage key collision") from None
        return True

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def get(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if self._classifier.classify_head(exc) == "not_found":
                return None
            raise
        read = getattr(response.get("Body"), "read", None)
        if not callable(read):
            raise OSError("storage response has no readable body")
        content = read()
        if not isinstance(content, bytes):
            raise OSError("storage response body is not bytes")
        return content

    def object_checksum(self, key: str) -> str | None:
        try:
            existing = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if self._classifier.classify_head(exc) == "not_found":
                return None
            raise
        metadata = existing.get("Metadata")
        if isinstance(metadata, dict):
            checksum = metadata.get("sha256")
            if isinstance(checksum, str):
                return checksum
        return ""
