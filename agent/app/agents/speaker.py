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

        if hasattr(result, "normalize_speech"):
            result.normalize_speech(self.services.max_speak_chars)
        else:
            result.speak_immediate = self._dedupe_and_trim(result.speak_immediate)
            result.speak_after = self._dedupe_and_trim(result.speak_after)
        if result.speak_immediate or result.speak_after:
            self.trace(result, "normalized model-authored speech")
        else:
            self.trace(result, "no model-authored speech available")
        return result

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
