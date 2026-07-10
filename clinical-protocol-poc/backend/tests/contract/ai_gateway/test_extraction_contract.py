import pytest

from protocol_poc.ai_gateway.fixture_provider import FixtureProvider
from protocol_poc.ai_gateway.schemas import ExtractionInput, GatewaySchemaError
from protocol_poc.ai_gateway.service import AIGateway
from protocol_poc.ai_gateway.tasks import TaskType


def test_extraction_rejects_missing_source_location() -> None:
    provider = FixtureProvider({"candidates": [{"kind": "dose", "value": {"kind": "dose", "value": "10", "unit": "mg"}}]})
    gateway = AIGateway(provider)

    with pytest.raises(GatewaySchemaError):
        gateway.run(TaskType.EXTRACT_FACTS, ExtractionInput(evidence_ids=["e1"]))

    assert gateway.calls[-1].status == "failed"
    assert gateway.calls[-1].schema_valid is False


def test_gateway_rejects_unregistered_task_schema_pair() -> None:
    gateway = AIGateway(FixtureProvider({"candidates": []}))
    with pytest.raises(GatewaySchemaError):
        gateway.run(TaskType.DRAFT_PASSAGE, ExtractionInput(evidence_ids=["e1"]))
