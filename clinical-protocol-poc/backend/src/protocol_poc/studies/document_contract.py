from dataclasses import dataclass
import re
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ContractFinding:
    code: str
    field: str
    message: str


class DocumentContract:
    _template_tokens = (
        ("synopsis", "[[SECTION:synopsis]]"),
        ("objectives_endpoints", "[[SECTION:objectives_endpoints]]"),
        ("study_design", "[[SECTION:study_design]]"),
        ("eligibility", "[[SECTION:eligibility]]"),
        ("poc_disclaimer", "[[POC_DISCLAIMER]]"),
    )
    _synopsis_fields = (
        ("study_identity", ("study identity",), ("short title:",)),
        ("objectives", ("objectives",), ("objective:",)),
        ("endpoints", ("endpoints",), ("endpoint:",)),
        (
            "arms_interventions",
            ("arms and interventions", "arms/interventions", "arms / interventions"),
            ("arm:", "intervention:"),
        ),
        ("population", ("population", "study population"), ("population:",)),
        (
            "eligibility",
            ("eligibility", "eligibility criteria"),
            ("eligibility:", "inclusion:", "exclusion:"),
        ),
    )
    _synopsis_value_only_fields = (("duration", "duration:"),)

    @classmethod
    def synopsis_headings(cls) -> dict[str, tuple[str, ...]]:
        """Return the single supported heading vocabulary for synopsis consumers."""
        return {field: headings for field, headings, _labels in cls._synopsis_fields}

    @classmethod
    def unsupported_synopsis_headings(cls, lines: Sequence[str]) -> tuple[str, ...]:
        supported = {
            heading
            for _field, headings, _labels in cls._synopsis_fields
            for heading in headings
        }
        normalized = tuple(cls._normalize(line) for line in lines if line.strip())
        return tuple(line for line in normalized if ":" not in line and line not in supported)

    def validate_template(
        self, evidence: Sequence[object]
    ) -> tuple[ContractFinding, ...]:
        combined = "\n".join(self._evidence_text(item) for item in evidence)
        findings: list[ContractFinding] = []
        for field, token in self._template_tokens:
            count = combined.count(token)
            if count == 0:
                findings.append(
                    ContractFinding(
                        "TEMPLATE_TOKEN_MISSING",
                        field,
                        f"Required template token {token} is missing.",
                    )
                )
            elif count > 1:
                findings.append(
                    ContractFinding(
                        "TEMPLATE_TOKEN_DUPLICATE",
                        field,
                        f"Required template token {token} must appear exactly once.",
                    )
                )
        return tuple(findings)

    def validate_synopsis(
        self, evidence: Sequence[object]
    ) -> tuple[ContractFinding, ...]:
        text_items = tuple(self._evidence_text(item) for item in evidence)
        lines = tuple(self._normalize(text) for text in text_items if text.strip())
        findings: list[ContractFinding] = []
        if self.unsupported_synopsis_headings(lines):
            findings.append(
                ContractFinding(
                    "SYNOPSIS_HEADING_UNSUPPORTED",
                    "synopsis",
                    "The synopsis contains a heading outside the supported vocabulary.",
                )
            )
        for field, headings, labels in self._synopsis_fields:
            heading_matches = [line for line in lines if line in headings]
            value_matches = [
                line
                for line in lines
                for label in labels
                if line.startswith(label) and bool(line.removeprefix(label).strip())
            ]
            if len(heading_matches) != 1:
                if not heading_matches:
                    code = "SYNOPSIS_HEADING_MISSING"
                elif len(set(heading_matches)) == 1:
                    code = "SYNOPSIS_HEADING_DUPLICATE"
                else:
                    code = "SYNOPSIS_HEADING_AMBIGUOUS"
                findings.append(
                    ContractFinding(
                        code,
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} heading.",
                    )
                )
            if len(value_matches) != 1:
                code = (
                    "SYNOPSIS_VALUE_MISSING"
                    if not value_matches
                    else "SYNOPSIS_VALUE_AMBIGUOUS"
                )
                findings.append(
                    ContractFinding(
                        code,
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} value.",
                    )
                )
        for field, label in self._synopsis_value_only_fields:
            matches = [
                line for line in lines
                if line.startswith(label) and bool(line.removeprefix(label).strip())
            ]
            if len(matches) != 1:
                findings.append(
                    ContractFinding(
                        "SYNOPSIS_VALUE_MISSING" if not matches else "SYNOPSIS_VALUE_AMBIGUOUS",
                        field,
                        f"The supported synopsis requires exactly one {field.replace('_', ' ')} value.",
                    )
                )
        return tuple(findings)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _evidence_text(item: object) -> str:
        value = getattr(item, "text", None)
        if not isinstance(value, str):
            raise TypeError("evidence items must provide text")
        return value
