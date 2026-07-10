from dataclasses import dataclass
from typing import Literal


Severity = Literal["info", "warning", "blocker"]


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    source: Literal["deterministic", "semantic"] = "deterministic"
