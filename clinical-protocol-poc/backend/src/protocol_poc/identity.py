import hashlib
import hmac
import json
import re
import time
import unicodedata

from protocol_poc.config import Settings
from protocol_poc.tenancy import TenantContext


class IdentityVerificationError(ValueError):
    pass


def canonical_identity(tenant_id: str, actor_id: str, timestamp: str) -> bytes:
    _validate_identifier("tenant", tenant_id)
    _validate_identifier("actor", actor_id)
    _parse_timestamp(timestamp)
    return json.dumps([tenant_id, actor_id, timestamp], ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _validate_identifier(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise IdentityVerificationError(f"invalid {label} identity")
    if len(value.encode("utf-8")) > 128:
        raise IdentityVerificationError(f"{label} identity is too long")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise IdentityVerificationError(f"{label} identity contains control characters")


def _parse_timestamp(value: str) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]{0,18}", value):
        raise IdentityVerificationError("invalid identity timestamp")
    parsed = int(value)
    if parsed >= 2**63:
        raise IdentityVerificationError("invalid identity timestamp")
    return parsed


def verify_identity_headers(
    tenant_id: str,
    actor_id: str,
    timestamp: str,
    signature: str,
    settings: Settings,
    *,
    now: int | None = None,
) -> TenantContext:
    _validate_identifier("tenant", tenant_id)
    _validate_identifier("actor", actor_id)
    if settings.allow_insecure_identity_headers:
        if settings.environment not in {"test", "development"}:
            raise IdentityVerificationError("insecure identity mode is forbidden")
        return TenantContext(tenant_id, actor_id)
    secret = settings.identity_hmac_secret
    if not secret:
        raise IdentityVerificationError("identity verification is not configured")
    issued_at = _parse_timestamp(timestamp)
    current = int(time.time()) if now is None else now
    if abs(current - issued_at) > settings.identity_replay_window_seconds:
        raise IdentityVerificationError("expired identity assertion")
    expected = hmac.new(secret.encode(), canonical_identity(tenant_id, actor_id, timestamp), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise IdentityVerificationError("invalid identity signature")
    return TenantContext(tenant_id, actor_id)
