from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..clients.ollama_client import OllamaClient
from ..schema import AgentResult, AgentRunRequest

if TYPE_CHECKING:
    from ..capabilities.catalog import CapabilityCatalog
    from ..task_graph.planner import TaskGraphPlanner


@dataclass(slots=True)
class AgentServices:
    ollama: OllamaClient | None = None
    use_llm: bool = True
    max_speak_chars: int = 120
    task_graph_planner: "TaskGraphPlanner | None" = None
    capability_catalog: "CapabilityCatalog | None" = None
    capability_match_limit: int = 8


class BaseAgent(ABC):
    name: str = "base_agent"

    def __init__(self, services: AgentServices) -> None:
        self.services = services

    def can_handle(self, request: AgentRunRequest) -> bool:
        return self.name in request.route_decision.agents

    @abstractmethod
    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        """Mutate and return the cumulative AgentResult."""

    def language(self, request: AgentRunRequest) -> str:
        return request.language or request.route_decision.language or "en-US"

    def is_zh(self, request: AgentRunRequest) -> bool:
        return self.language(request).startswith("zh")

    def trace(self, result: AgentResult, message: str) -> None:
        result.handled_by.append(self.name)
        result.trace.append(f"{self.name}: {message}")

    def get_context(self, request: AgentRunRequest, key: str, default: Any = None) -> Any:
        return request.context.get(key, default)
