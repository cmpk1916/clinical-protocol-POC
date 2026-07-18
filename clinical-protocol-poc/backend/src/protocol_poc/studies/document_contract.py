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
        for field, headings, labels in self._synopsis_fields:
            has_heading = any(line in headings for line in lines)
            has_value = any(
                line.startswith(label) and bool(line.removeprefix(label).strip())
                for line in lines
                for label in labels
            )
            if not has_heading or not has_value:
                findings.append(
                    ContractFinding(
                        "SYNOPSIS_REQUIREMENT_MISSING",
                        field,
                        f"The supported synopsis requires a {field.replace('_', ' ')} section and value.",
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
