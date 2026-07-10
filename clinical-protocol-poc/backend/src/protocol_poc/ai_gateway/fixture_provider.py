from copy import deepcopy
from typing import Any

from protocol_poc.ai_gateway.tasks import TaskType


class FixtureProvider:
    provider_id = "fixture"
    model_id = "deterministic-v1"

    def __init__(self, response: dict[str, Any] | dict[str, dict[str, Any]]) -> None:
        self.response = response

    def invoke(self, task: TaskType, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        selected = self.response.get(task.value, self.response)
        if not isinstance(selected, dict):
            raise ValueError("fixture response must be an object")
        return deepcopy(selected)
