from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComposedPassage:
    text: str
    claims: tuple[dict[str, object], ...]
    fact_ids: tuple[str, ...]
    placeholders: tuple[str, ...] = ()


class LocalComposer:
    """Pure, closed-world templates for the four supported synthetic sections."""

    _required = {
        "synopsis": (("study_identity", "study identity"), ("population", "study population")),
        "objectives_endpoints": (("objective", "objective"), ("endpoint", "endpoint"), ("timepoint", "endpoint timepoint")),
        "study_design": (("arm", "arm"), ("intervention", "intervention"), ("dose", "intervention dose"), ("duration", "study duration")),
        "eligibility": (("eligibility", "eligibility criteria"),),
    }

    def compose(self, section: str, approved_facts: dict[str, dict[str, Any]]) -> ComposedPassage:
        if section not in self._required:
            raise ValueError("section is outside the bounded drafting scope")
        selected = {kind: self._single(approved_facts, kind) for kind, _label in self._required[section]}
        missing = [label for kind, label in self._required[section] if selected[kind] is None]
        if missing:
            placeholders = tuple(f"[[REQUIRED: {label}]]" for label in missing)
            return ComposedPassage("\n".join(placeholders), (), (), placeholders)

        facts = {kind: item for kind, item in selected.items() if item is not None}
        fact_ids = tuple(str(item[0]) for item in facts.values())
        values = {kind: self._value(item[1]) for kind, item in facts.items()}
        if section == "synopsis":
            text = f"{values['study_identity']} is a synthetic study in {values['population']}."
        elif section == "objectives_endpoints":
            text = f"The objective is to {values['objective']}; the endpoint is {values['endpoint']} at {values['timepoint']}."
        elif section == "study_design":
            text = f"{values['arm']} receives {values['intervention']}, {values['dose']}, for {values['duration']}."
        else:
            text = f"Eligibility is limited to {values['eligibility']}."
        return ComposedPassage(text, ({"text": text, "fact_ids": list(fact_ids)},), fact_ids)

    @staticmethod
    def _single(facts: dict[str, dict[str, Any]], kind: str) -> tuple[str, dict[str, Any]] | None:
        matches = [
            (fact_id, value)
            for fact_id, value in facts.items()
            if value.get("fact_kind", value.get("kind")) == kind
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _value(value: dict[str, Any]) -> str:
        kind = value["kind"]
        if kind == "dose":
            return " ".join(str(value[key]) for key in ("value", "unit", "frequency"))
        if kind == "structured_criterion":
            criterion = value.get("value")
            if isinstance(criterion, dict) and isinstance(criterion.get("text"), str):
                return str(criterion["text"])
            raise ValueError("eligibility criterion is malformed")
        raw = value.get("value")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("approved fact value is malformed")
        return str(raw)
