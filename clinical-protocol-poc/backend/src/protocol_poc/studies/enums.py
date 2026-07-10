from enum import StrEnum


class FactStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    CONFLICTED = "conflicted"
