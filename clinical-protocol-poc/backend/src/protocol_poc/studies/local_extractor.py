from dataclasses import dataclass
import re
from typing import Any, Sequence

from protocol_poc.studies.document_contract import DocumentContract


LOCAL_EXTRACTOR_VERSION = "local-rules-v1"


@dataclass(frozen=True, slots=True)
class ExtractionFinding:
    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class LocalCandidate:
    kind: str
    value_json: dict[str, Any]
    source_evidence_id: str
    confidence: float = 1.0
    critical: bool = False


@dataclass(frozen=True, slots=True)
class ExtractionProposal:
    candidates: tuple[LocalCandidate, ...]
    findings: tuple[ExtractionFinding, ...]
    extractor_version: str = LOCAL_EXTRACTOR_VERSION

    def __post_init__(self) -> None:
        if self.candidates and self.findings:
            raise ValueError("an extraction proposal cannot contain candidates and findings")
        if not self.candidates and not self.findings:
            raise ValueError("an extraction proposal must contain candidates or findings")


class LocalExtractor:
    _headings = DocumentContract.synopsis_headings()
    _labels = {
        "study_identity": "short title:",
        "objectives": "objective:",
        "endpoints": "endpoint:",
        "arms_interventions": "arm:",
        "population": "population:",
        "eligibility": "eligibility:",
    }
    _duration_label = "duration:"
    _endpoint = re.compile(r"^(?P<name>.+?)\s+at\s+(?P<timepoint>Week\s+\d+)$", re.IGNORECASE)
    _duration = re.compile(r"^(?P<count>[1-9]\d*)\s+(?P<unit>day|days|week|weeks)$", re.IGNORECASE)
    _arm = re.compile(
        r"^Arm:\s*(?P<arm>[^;]+);\s*Intervention:\s*(?P<intervention>.+?)"
        r"(?:\s+(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg)\s+"
        r"(?P<frequency>once daily))?$",
        re.IGNORECASE,
    )

    def extract(self, evidence: Sequence[object]) -> ExtractionProposal:
        items = tuple(
            (self._id(item), self._text(item), self._normalize(self._text(item)))
            for item in evidence
            if self._text(item).strip()
        )
        findings: list[ExtractionFinding] = []
        if DocumentContract.unsupported_synopsis_headings(
            tuple(text for _, text, _ in items)
        ):
            findings.append(
                ExtractionFinding(
                    "SYNOPSIS_HEADING_UNSUPPORTED",
                    "synopsis",
                    "The synopsis contains a heading outside the supported vocabulary.",
                )
            )
        for field, headings in self._headings.items():
            heading_matches = [
                normalized for _, _, normalized in items if normalized in headings
            ]
            if not heading_matches:
                findings.append(
                    ExtractionFinding(
                        "SYNOPSIS_HEADING_MISSING",
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} heading.",
                    )
                )
            elif len(heading_matches) > 1:
                code = (
                    "SYNOPSIS_HEADING_DUPLICATE"
                    if len(set(heading_matches)) == 1
                    else "SYNOPSIS_HEADING_AMBIGUOUS"
                )
                findings.append(
                    ExtractionFinding(
                        code,
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} heading.",
                    )
                )
        if findings:
            return ExtractionProposal((), tuple(findings))

        values: dict[str, tuple[str, str]] = {}
        for field, label in self._labels.items():
            label_matches: list[tuple[str, str]] = []
            for item_id, text, _normalized in items:
                value = self._label_value(text, label)
                if value:
                    label_matches.append((item_id, value))
            if len(label_matches) != 1:
                code = "SYNOPSIS_VALUE_MISSING" if not label_matches else "SYNOPSIS_VALUE_AMBIGUOUS"
                findings.append(
                    ExtractionFinding(
                        code,
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} value.",
                    )
                )
            else:
                values[field] = label_matches[0]
        if findings:
            return ExtractionProposal((), tuple(findings))

        endpoint_id, endpoint_text = values["endpoints"]
        endpoint_match = self._endpoint.fullmatch(endpoint_text)
        if endpoint_match is None:
            findings.append(
                ExtractionFinding(
                    "SYNOPSIS_TIMEPOINT_MISSING",
                    "endpoints",
                    "Endpoint values must end with a supported Week N timepoint.",
                )
            )
        arm_id, arm_text = values["arms_interventions"]
        arm_match = self._arm.fullmatch(f"Arm: {arm_text}")
        if arm_match is None or arm_match.group("value") is None:
            findings.append(
                ExtractionFinding(
                    "SYNOPSIS_DOSE_MISSING",
                    "arms_interventions",
                    "Intervention values must include an N mg dose and once daily frequency.",
                )
            )
        duration_matches = [
            (item_id, self._label_value(text, self._duration_label))
            for item_id, text, _normalized in items
            if self._has_label(text, self._duration_label)
        ]
        duration_id: str | None = None
        duration_match: re.Match[str] | None = None
        if len(duration_matches) > 1:
            findings.append(
                ExtractionFinding(
                    "SYNOPSIS_VALUE_AMBIGUOUS",
                    "duration",
                    "The supported synopsis requires exactly one duration value.",
                )
            )
        elif duration_matches:
            duration_id, duration = duration_matches[0]
            duration_match = self._duration.fullmatch(duration or "")
            if duration_match is None:
                findings.append(
                    ExtractionFinding(
                        "SYNOPSIS_DURATION_INVALID",
                        "duration",
                        "Duration must be a positive integer followed by day(s) or week(s).",
                    )
                )
        if findings:
            return ExtractionProposal((), tuple(findings))
        assert endpoint_match is not None and arm_match is not None

        identity_id, identity = values["study_identity"]
        objective_id, objective = values["objectives"]
        population_id, population = values["population"]
        eligibility_id, eligibility = values["eligibility"]
        candidates: tuple[LocalCandidate, ...] = (
            self._candidate("study_identity", identity, identity_id),
            self._candidate("objective", objective, objective_id),
            self._candidate("endpoint", endpoint_match.group("name"), endpoint_id),
            self._candidate("timepoint", endpoint_match.group("timepoint"), endpoint_id),
            self._candidate("arm", arm_match.group("arm"), arm_id),
            self._candidate("intervention", arm_match.group("intervention"), arm_id),
            LocalCandidate(
                "dose",
                {
                    "kind": "dose",
                    "value": arm_match.group("value"),
                    "unit": arm_match.group("unit").lower(),
                    "frequency": arm_match.group("frequency").lower(),
                },
                arm_id,
                critical=True,
            ),
            self._candidate("population", population, population_id),
            LocalCandidate(
                "eligibility",
                {"kind": "structured_criterion", "value": {"text": eligibility}},
                eligibility_id,
                critical=True,
            ),
        )
        if duration_match is not None and duration_id is not None:
            duration_count = int(duration_match.group("count"))
            duration_unit = duration_match.group("unit").casefold().removesuffix("s")
            normalized_duration = f"{duration_count} {duration_unit if duration_count == 1 else f'{duration_unit}s'}"
            candidates += (self._candidate("duration", normalized_duration, duration_id),)
        return ExtractionProposal(candidates, ())

    @staticmethod
    def _candidate(kind: str, value: str, evidence_id: str) -> LocalCandidate:
        return LocalCandidate(kind, {"kind": "string", "value": value}, evidence_id)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _label_value(text: str, label: str) -> str | None:
        words = label.removesuffix(":").split()
        pattern = r"^\s*" + r"\s+".join(map(re.escape, words)) + r"\s*:\s*(.+?)\s*$"
        match = re.fullmatch(pattern, text, re.IGNORECASE)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match is not None else None

    @staticmethod
    def _has_label(text: str, label: str) -> bool:
        words = label.removesuffix(":").split()
        pattern = r"^\s*" + r"\s+".join(map(re.escape, words)) + r"\s*:\s*.*$"
        return re.fullmatch(pattern, text, re.IGNORECASE) is not None

    @staticmethod
    def _id(item: object) -> str:
        value = getattr(item, "id", None)
        if not isinstance(value, str):
            raise TypeError("evidence items must provide a string id")
        return value

    @staticmethod
    def _text(item: object) -> str:
        value = getattr(item, "text", None)
        if not isinstance(value, str):
            raise TypeError("evidence items must provide text")
        return value
