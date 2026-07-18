from dataclasses import dataclass
import re
from typing import Any, Sequence


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


class LocalExtractor:
    _headings = {
        "study_identity": "study identity",
        "objectives": "objectives",
        "endpoints": "endpoints",
        "arms_interventions": "arms and interventions",
        "population": "study population",
        "eligibility": "eligibility criteria",
    }
    _labels = {
        "study_identity": "short title:",
        "objectives": "objective:",
        "endpoints": "endpoint:",
        "arms_interventions": "arm:",
        "population": "population:",
        "eligibility": "eligibility:",
    }
    _endpoint = re.compile(r"^(?P<name>.+?)\s+at\s+(?P<timepoint>Week\s+\d+)$", re.IGNORECASE)
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
        for field, heading in self._headings.items():
            if sum(normalized == heading for _, _, normalized in items) > 1:
                findings.append(
                    ExtractionFinding(
                        "SYNOPSIS_HEADING_AMBIGUOUS",
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} heading.",
                    )
                )
        if findings:
            return ExtractionProposal((), tuple(findings))

        values: dict[str, tuple[str, str]] = {}
        for field, label in self._labels.items():
            matches = []
            for item_id, text, _normalized in items:
                value = self._label_value(text, label)
                if value:
                    matches.append((item_id, value))
            if len(matches) != 1:
                code = "SYNOPSIS_VALUE_MISSING" if not matches else "SYNOPSIS_VALUE_AMBIGUOUS"
                findings.append(
                    ExtractionFinding(
                        code,
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} value.",
                    )
                )
            else:
                values[field] = matches[0]
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
        if findings:
            return ExtractionProposal((), tuple(findings))
        assert endpoint_match is not None and arm_match is not None

        identity_id, identity = values["study_identity"]
        objective_id, objective = values["objectives"]
        population_id, population = values["population"]
        eligibility_id, eligibility = values["eligibility"]
        candidates = (
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
