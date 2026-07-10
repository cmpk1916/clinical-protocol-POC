from decimal import Decimal

import pytest
from pydantic import ValidationError

from protocol_poc.studies.enums import FactStatus
from protocol_poc.studies.schemas import Endpoint, FactValue, validate_endpoint_relationships


def test_fact_status_is_closed_to_governed_states() -> None:
    assert {status.value for status in FactStatus} == {
        "candidate", "approved", "rejected", "superseded", "conflicted"
    }


def test_dose_requires_value_and_ucum_unit() -> None:
    with pytest.raises(ValidationError):
        FactValue(kind="dose", value="10", unit=None)


def test_dose_normalizes_numeric_value() -> None:
    value = FactValue(kind="dose", value="10.0", unit="mg")
    assert value.value == Decimal("10.0")


def test_endpoint_requires_objective_and_timepoint_links() -> None:
    endpoint = Endpoint(name="HbA1c change", hierarchy="primary")
    findings = validate_endpoint_relationships(endpoint)
    assert {finding.code for finding in findings} == {
        "ENDPOINT_OBJECTIVE_MISSING", "ENDPOINT_TIMEPOINT_MISSING"
    }
