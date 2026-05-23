from __future__ import annotations

from ..schema import AgentResult, AgentRunRequest, MemoryUpdate
from .base import BaseAgent


class MemoryAgent(BaseAgent):
    name = "memory_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.route_decision.route != "memory" and self.name not in request.route_decision.agents:
            return result

        result.memory_updates.append(
            MemoryUpdate(
                type="user_statement",
                key=None,
                value={"text": request.text, "intent": request.route_decision.intent},
                confidence=request.route_decision.confidence,
            )
        )
        result.add_action(
            "memory_store",
            "memory.store",
            params={"text": request.text, "intent": request.route_decision.intent},
            blocking=False,
            timeout_ms=1000,
            reason="memory_update_planned_by_agent",
        )
        if not result.speak_immediate:
            result.add_speak_immediate("我记下了。" if self.is_zh(request) else "I will remember that.", style="brief")
        self.trace(result, "planned memory update")
        return result
