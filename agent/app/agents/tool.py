from __future__ import annotations

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent


class ToolAgent(BaseAgent):
    name = "tool_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.route_decision.route != "tool" and self.name not in request.route_decision.agents:
            return result

        intent = request.route_decision.intent or "tool_request"
        result.add_action(
            "tool_executor",
            f"tool.{intent}",
            params={"text": request.text, "language": request.language, "context": request.context},
            blocking=True,
            timeout_ms=5000,
            reason="tool_request_planned_by_agent",
        )
        if not result.speak_immediate:
            result.add_speak_immediate("我看一下。" if self.is_zh(request) else "Let me check.", style="brief")
        self.trace(result, f"planned tool.{intent}")
        return result
