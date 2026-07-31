from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    if isinstance(value, frozenset):
        return tuple(sorted((_plain(item) for item in value), key=repr))
    return value


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    expected: object
    actual: object
    volatile: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", _freeze(self.expected))
        object.__setattr__(self, "actual", _freeze(self.actual))


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    name: str
    media_type: str
    sha256: str
    snapshot_id: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class StudyRunResult:
    study_key: str
    checks: tuple[CheckResult, ...]
    initial_export_denied: bool = False
    input_history: tuple[Mapping[str, object], ...] = ()
    facts: tuple[Mapping[str, object], ...] = ()
    passages: Mapping[str, str] | None = None
    artifacts: tuple[ArtifactResult, ...] = ()
    study_id: str | None = None
    snapshot_id: str | None = None
    exported_unsupported_clinical_fact_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(
            self,
            "input_history",
            tuple(_freeze(item) for item in self.input_history),
        )
        object.__setattr__(self, "facts", tuple(_freeze(item) for item in self.facts))
        if self.passages is not None:
            object.__setattr__(self, "passages", _freeze(self.passages))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(item.passed for item in self.checks)


@dataclass(frozen=True, slots=True)
class PilotRunResult:
    studies: tuple[StudyRunResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.studies) and all(item.passed for item in self.studies)

    @property
    def exported_unsupported_clinical_fact_count(self) -> int:
        return sum(
            item.exported_unsupported_clinical_fact_count for item in self.studies
        )


def deterministic_projection(result: PilotRunResult) -> dict[str, object]:
    def stable_check(check: CheckResult) -> dict[str, object]:
        projected: dict[str, object] = {
            "name": check.name,
            "passed": check.passed,
        }
        if not check.volatile:
            projected.update(expected=_plain(check.expected), actual=_plain(check.actual))
        return projected

    return {
        "passed": result.passed,
        "exported_unsupported_clinical_fact_count": (
            result.exported_unsupported_clinical_fact_count
        ),
        "studies": [
            {
                "study_key": study.study_key,
                "passed": study.passed,
                "initial_export_denied": study.initial_export_denied,
                "checks": [stable_check(check) for check in study.checks],
                "input_history": [
                    {
                        key: value
                        for key, value in item.items()
                        if key not in {
                            "version_id",
                            "current_file_version_id",
                            "checksum_sha256",
                        }
                    }
                    for item in study.input_history
                ],
                "facts": [_plain(item) for item in study.facts],
                "passages": _plain(study.passages or {}),
                "artifacts": [
                    {
                        "name": artifact.name,
                        "media_type": artifact.media_type,
                        "size_bytes": artifact.size_bytes,
                    }
                    for artifact in study.artifacts
                ],
                "exported_unsupported_clinical_fact_count": (
                    study.exported_unsupported_clinical_fact_count
                ),
            }
            for study in result.studies
        ],
    }
