from __future__ import annotations

from ..schema import AgentResult, AgentRunRequest, MemoryUpdate
from .base import BaseAgent


class MemoryAgent(BaseAgent):
    """Apply one model-authored session-memory proposal without semantic inference."""

    name = "memory_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if (
            request.route_decision.route != "memory"
            and self.name not in request.route_decision.agents
        ):
            return result

        proposal = request.route_decision.memory_update
        if proposal is None:
            proposal = next(
                (
                    item.memory_update
                    for item in request.route_decision.routes
                    if item.route == "memory" and item.memory_update is not None
                ),
                None,
            )
        if proposal is None:
            result.status = "clarify"
            result.reason = "memory_update_missing"
            self.trace(result, "memory proposal missing; semantic inference forbidden")
            return result

        entry = proposal.model_dump(mode="json")
        if proposal.operation == "remember":
            result.memory_updates.append(
                MemoryUpdate(
                    type="extracted_memory",
                    key=proposal.key or proposal.kind,
                    value=entry,
                    confidence=proposal.confidence,
                    metadata={"source": "goal_interpreter_memory_proposal"},
                )
            )
            action_type = "memory_store"
            action_target = "memory.store"
        elif proposal.operation == "forget":
            result.memory_updates.append(
                MemoryUpdate(
                    type="durable_memory_forget",
                    key=proposal.key,
                    value=entry,
                    confidence=proposal.confidence,
                    metadata={"source": "goal_interpreter_memory_proposal"},
                )
            )
            action_type = "memory_store"
            action_target = "memory.forget"
        else:
            result.memory_updates.append(
                MemoryUpdate(
                    type="durable_memory_clear",
                    value=entry,
                    confidence=proposal.confidence,
                    metadata={"source": "goal_interpreter_memory_proposal"},
                )
            )
            action_type = "memory_store"
            action_target = "memory.clear_profile"
        result.memory_updates.append(
            MemoryUpdate(
                type="user_statement",
                key=proposal.key,
                value={
                    "text": proposal.text,
                    "kind": proposal.kind,
                    "operation": proposal.operation,
                },
                confidence=proposal.confidence,
                metadata={"source": "model_authored_memory_proposal"},
            )
        )
        result.add_action(
            action_type,
            action_target,
            params=entry,
            blocking=False,
            timeout_ms=1000,
            reason="model_authored_memory_update",
        )
        self.trace(result, f"applied model-authored memory {proposal.operation} proposal")
        return result
