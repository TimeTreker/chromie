from __future__ import annotations

import re

from ..schema import AgentResult, AgentRunRequest, MemoryUpdate
from .base import BaseAgent


class MemoryAgent(BaseAgent):
    name = "memory_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.route_decision.route != "memory" and self.name not in request.route_decision.agents:
            return result

        entry = self._memory_entry(request)
        result.memory_updates.append(
            MemoryUpdate(
                type="extracted_memory",
                key=entry["kind"],
                value=entry,
                confidence=request.route_decision.confidence,
            )
        )
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

    def _memory_entry(self, request: AgentRunRequest) -> dict[str, str]:
        statement = self._refined_statement(request.text)
        intent = (request.route_decision.intent or "").lower()
        lowered = request.text.lower()
        kind = (
            "preference"
            if "preference" in intent
            or "favorite" in lowered
            or "preferred" in lowered
            or "prefer" in lowered
            else "note"
        )
        return {
            "scope": "session",
            "kind": kind,
            "text": statement,
            "persistence_policy": "ephemeral",
        }

    @staticmethod
    def _refined_statement(text: str) -> str:
        cleaned = " ".join((text or "").strip().split())
        cleaned = re.sub(
            r"^(?:please\s+)?(?:remember|memorize|note|save|store)\s+(?:that\s+)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        if cleaned:
            return f"User asked Chromie to remember: {cleaned}"
        return "User asked Chromie to remember the current session note."
