from dataclasses import dataclass

from protocol_poc.validation.findings import Finding


@dataclass(frozen=True)
class ClaimInput:
    text: str
    support_ids: tuple[str, ...]


def validate_claim_support(claims: list[ClaimInput]) -> list[Finding]:
    return [
        Finding("CLAIM_SUPPORT_MISSING", "blocker", "Clinical claim has no approved support link")
        for claim in claims
        if claim.text.strip() and not claim.support_ids
    ]
