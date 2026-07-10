from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re

from protocol_poc.validation.findings import Finding


@dataclass(frozen=True)
class ApprovedClinicalModel:
    doses: set[tuple[str, str]] = field(default_factory=set)
    timepoints: set[int] = field(default_factory=set)
    age_ranges: set[tuple[int, int]] = field(default_factory=set)
    durations: set[tuple[int, str]] = field(default_factory=set)


def normalize_decimal(value: str) -> str:
    try:
        normalized = Decimal(value).normalize()
    except InvalidOperation as error:
        raise ValueError("invalid decimal") from error
    return format(normalized, "f")


def canonical_dose(value: str, unit: str) -> Decimal:
    factors = {"g": Decimal("1000"), "mg": Decimal("1"), "mcg": Decimal("0.001"), "µg": Decimal("0.001")}
    return Decimal(normalize_decimal(value)) * factors[unit.casefold()]


def canonical_duration(value: int, unit: str) -> int:
    factors = {"d": 1, "day": 1, "days": 1, "wk": 7, "week": 7, "weeks": 7}
    return value * factors[unit.casefold()]


def validate_clinical_values(text: str, approved: ApprovedClinicalModel) -> list[Finding]:
    findings: list[Finding] = []
    doses = {canonical_dose(value, unit) for value, unit in approved.doses}
    for value, unit in re.findall(r"\b(\d+(?:\.\d+)?)\s*(mcg|mg|g|µg)\b", text, re.IGNORECASE):
        if canonical_dose(value, unit) not in doses:
            findings.append(Finding("UNSUPPORTED_DOSE", "blocker", f"Dose {value} {unit} is not an approved fact"))
    for week in re.findall(r"\bWeek\s+(\d+)\b", text, re.IGNORECASE):
        if int(week) not in approved.timepoints:
            findings.append(Finding("TIMEPOINT_MISMATCH", "blocker", f"Week {week} is not an approved timepoint"))
    for low, high in re.findall(r"\baged?\s+(\d+)\s+(?:to|-)\s+(\d+)\s+years\b", text, re.IGNORECASE):
        if (int(low), int(high)) not in approved.age_ranges:
            findings.append(Finding("UNSUPPORTED_ELIGIBILITY", "blocker", f"Age range {low} to {high} is not approved"))
    durations = {canonical_duration(value, unit) for value, unit in approved.durations}
    for value, unit in re.findall(r"\bfor\s+(\d+)\s+(days?|weeks?)\b", text, re.IGNORECASE):
        if canonical_duration(int(value), unit) not in durations:
            findings.append(Finding("DURATION_MISMATCH", "blocker", f"Duration {value} {unit} is not approved"))
    if re.search(r"\bdose\b", text, re.IGNORECASE) and not re.search(r"\b\d+(?:\.\d+)?\s*(?:mcg|mg|g|µg)\b", text, re.IGNORECASE):
        findings.append(Finding("CLINICAL_VALUE_UNPARSEABLE", "blocker", "Dose claim could not be parsed deterministically"))
    return findings
