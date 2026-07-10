import hashlib
import hmac

import pytest

from protocol_poc.config import Settings
from protocol_poc.identity import IdentityVerificationError, canonical_identity, verify_identity_headers


def test_signed_identity_and_fail_closed_modes() -> None:
    timestamp = "1000"
    signature = hmac.new(b"secret", canonical_identity("tenant", "actor", timestamp), hashlib.sha256).hexdigest()
    context = verify_identity_headers("tenant", "actor", timestamp, signature, Settings(identity_hmac_secret="secret"), now=1000)
    assert (context.tenant_id, context.actor_id) == ("tenant", "actor")
    with pytest.raises(IdentityVerificationError, match="not configured"):
        verify_identity_headers("tenant", "actor", timestamp, signature, Settings(), now=1000)
    with pytest.raises(IdentityVerificationError, match="forbidden"):
        verify_identity_headers("tenant", "actor", "", "", Settings(allow_insecure_identity_headers=True, environment="production"), now=1000)


def test_identity_encoding_is_injective_and_stable() -> None:
    assert canonical_identity("tenant", "actor", "1000") == b'["tenant","actor","1000"]'
    with pytest.raises(IdentityVerificationError, match="control"):
        canonical_identity("a\nb", "c", "1000")
    with pytest.raises(IdentityVerificationError, match="control"):
        canonical_identity("a", "b\nc", "1000")


@pytest.mark.parametrize("value", [" leading", "trailing ", "tab\tvalue", "nul\0value", "\x85control", "x" * 129])
def test_identity_rejects_ambiguous_or_overlong_values(value: str) -> None:
    with pytest.raises(IdentityVerificationError):
        canonical_identity(value, "actor", "1000")


@pytest.mark.parametrize("timestamp", ["", "+1", "-1", "01", "1.0", str(2**63)])
def test_identity_rejects_noncanonical_timestamp(timestamp: str) -> None:
    with pytest.raises(IdentityVerificationError, match="timestamp"):
        canonical_identity("tenant", "actor", timestamp)
