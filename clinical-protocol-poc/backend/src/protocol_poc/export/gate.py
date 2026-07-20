from dataclasses import dataclass, field


HARD_BLOCKERS = frozenset({
    "UNSUPPORTED_CONTENT", "UNRESOLVED_CRITICAL_FACT", "CRITICAL_CONTRADICTION",
    "INCOMPLETE_PROVENANCE", "REQUIRED_PLACEHOLDER", "VALIDATION_INCOMPLETE",
    "STALE_PASSAGE", "VALIDATOR_EXCEPTION", "STUDY_VERSION_CHANGED",
    "TEMPLATE_VERSION_INVALID", "TEMPLATE_HASH_MISMATCH",
    "STUDY_ARCHIVED", "INPUT_PROCESSING_INCOMPLETE", "TEMPLATE_NOT_CONFORMED",
    "FACT_REVIEW_INCOMPLETE", "PASSAGE_REVIEW_INCOMPLETE",
})


@dataclass
class ExportState:
    blocker_codes: list[str] = field(default_factory=list)
    quality_blocker_codes: list[str] = field(default_factory=list)
    validator_exception: bool = False

    def add_blocker(self, code: str) -> None:
        self.blocker_codes.append(code)

    def add_quality_blocker(self, code: str) -> None:
        self.quality_blocker_codes.append(code)


@dataclass(frozen=True)
class ExportDecision:
    allowed: bool
    blocker_codes: tuple[str, ...]


class ExportGate:
    def evaluate(self, state: ExportState) -> ExportDecision:
        codes = [*state.blocker_codes, *state.quality_blocker_codes]
        if state.validator_exception:
            codes.append("VALIDATOR_EXCEPTION")
        blockers = tuple(dict.fromkeys(
            code
            for code in codes
            if code in HARD_BLOCKERS or code in state.quality_blocker_codes
        ))
        return ExportDecision(not blockers, blockers)
