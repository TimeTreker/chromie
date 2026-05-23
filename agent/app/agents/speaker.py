from __future__ import annotations

from ..schema import AgentResult, AgentRunRequest, SpeakItem
from .base import BaseAgent


class SpeakerAgent(BaseAgent):
    name = "speaker_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if not request.route_decision.should_speak:
            result.speak_immediate = []
            result.speak_after = []
            self.trace(result, "speech disabled by route")
            return result

        if not result.speak_immediate and not result.speak_after:
            default = self._default_speech(request, result)
            if default:
                result.add_speak_immediate(default, style="brief")

        result.speak_immediate = self._dedupe_and_trim(result.speak_immediate)
        result.speak_after = self._dedupe_and_trim(result.speak_after)
        self.trace(result, "normalized speech")
        return result

    def _default_speech(self, request: AgentRunRequest, result: AgentResult) -> str | None:
        zh = self.is_zh(request)
        route = request.route_decision.route

        if route == "robot_action" and result.actions:
            if any(action.requires_confirmation for action in result.actions):
                return "这个动作需要你确认一下。" if zh else "Please confirm that action first."
            return "好的。" if zh else "Okay."

        if route == "tool":
            return "我看一下。" if zh else "Let me check."

        if route == "memory":
            return "我记下了。" if zh else "I will remember that."

        if route == "clarify":
            return "你是指什么？" if zh else "What do you mean?"

        if route == "chat":
            return "我明白。" if zh else "I understand."

        return None

    def _dedupe_and_trim(self, items: list[SpeakItem]) -> list[SpeakItem]:
        seen: set[str] = set()
        out: list[SpeakItem] = []
        max_chars = self.services.max_speak_chars
        for item in items:
            text = " ".join(item.text.strip().split())
            if not text or text in seen:
                continue
            if len(text) > max_chars:
                text = text[:max_chars].rstrip("，,。.!！?？ ")
                text += "。" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "."
            seen.add(text)
            out.append(item.model_copy(update={"text": text}))
        return out
