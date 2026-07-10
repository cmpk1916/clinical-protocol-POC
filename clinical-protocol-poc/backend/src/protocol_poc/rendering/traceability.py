import csv
from io import StringIO
import json
from typing import Any


FIELDS = (
    "section", "passage", "claim", "fact_value", "evidence_location",
    "guidance_release", "review_state", "validation_status",
)


def traceability_json(rows: list[dict[str, Any]]) -> bytes:
    normalized = [{field: row.get(field, "") for field in FIELDS} for row in rows]
    return json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()


def traceability_csv(rows: list[dict[str, Any]]) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)
    return output.getvalue().encode()
