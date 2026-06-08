from __future__ import annotations

import logging

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.tool")


class ToolAgent(BaseAgent):
    name = "tool_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.route_decision.route != "tool" and self.name not in request.route_decision.agents:
            return result

        planner = self.services.task_graph_planner
        if planner is not None and request.route_decision.route == "tool":
            try:
                graph = await planner.plan(
                    user_request=request.text,
                    language=self.language(request),
                    context=request.context,
                )
                result.task_graphs.append(graph.model_dump(mode="json"))
                result.add_speak_immediate(
                    "我已经准备好一个执行计划。" if self.is_zh(request) else "I prepared a task plan.",
                    style="brief",
                )
                self.trace(result, f"planned TaskGraph {graph.graph_id} with {len(graph.nodes)} node(s)")
                return result
            except Exception as exc:
                logger.warning(
                    "task_graph_planning_failed sid=%s error_type=%s error=%s",
                    request.sid,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                result.trace.append(f"tool_agent: TaskGraph planning failed: {type(exc).__name__}: {exc}")

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
