import pytest

from protocol_poc.export.gate import ExportGate, ExportState


@pytest.mark.parametrize("blocker", [
    "UNSUPPORTED_CONTENT", "UNRESOLVED_CRITICAL_FACT", "CRITICAL_CONTRADICTION",
    "INCOMPLETE_PROVENANCE", "REQUIRED_PLACEHOLDER", "VALIDATION_INCOMPLETE",
    "STALE_PASSAGE",
])
def test_each_hard_blocker_denies_export(blocker: str) -> None:
    state = ExportState()
    state.add_blocker(blocker)
    decision = ExportGate().evaluate(state)
    assert decision.allowed is False
    assert blocker in decision.blocker_codes


def test_validator_exception_denies_export() -> None:
    assert ExportGate().evaluate(ExportState(validator_exception=True)).allowed is False
