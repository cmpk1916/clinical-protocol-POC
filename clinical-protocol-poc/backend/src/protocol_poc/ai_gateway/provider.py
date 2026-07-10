from typing import Any, Protocol

from protocol_poc.ai_gateway.tasks import TaskType


class AIProvider(Protocol):
    provider_id: str
    model_id: str

    def invoke(self, task: TaskType, payload: dict[str, Any]) -> dict[str, Any]: ...
