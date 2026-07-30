from __future__ import annotations

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent


class VisionAgent(BaseAgent):
    name = "vision_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if self.name not in request.route_decision.agents:
            return result

        result.add_action(
            "vision_system",
            "vision.query",
            params={"text": request.text, "context": request.context},
            blocking=True,
            timeout_ms=5000,
            reason="vision_request_planned_by_agent",
        )
        self.trace(result, "planned vision query")
        return result
