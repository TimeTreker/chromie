from __future__ import annotations

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent


class ConversationAgent(BaseAgent):
    name = "conversation_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.route_decision.route not in {"chat", "clarify"} and self.name not in request.route_decision.agents:
            return result

        if request.route_decision.speak_first:
            result.add_speak_immediate(request.route_decision.speak_first, style="brief")
            self.trace(result, "used router speak_first")
            return result

        text = request.text.strip()
        if not text:
            result.status = "ignored"
            result.reason = "empty_text"
            self.trace(result, "ignored empty text")
            return result

        if self.services.use_llm and self.services.ollama is not None:
            try:
                response = await self._llm_reply(request)
                result.add_speak_immediate(response, style="brief")
                self.trace(result, "generated llm reply")
                return result
            except Exception:
                # Fall through to deterministic fallback.
                pass

        result.add_speak_immediate(self._fallback_reply(request), style="brief")
        self.trace(result, "used fallback reply")
        return result

    async def _llm_reply(self, request: AgentRunRequest) -> str:
        assert self.services.ollama is not None
        zh = self.is_zh(request)
        system = (
            "你是 Chromie 的对话 agent。请用自然、口语化、很短的一句话回复。"
            "默认不超过 20 个中文字。不要解释你的内部流程。"
            if zh
            else "You are Chromie's conversation agent. Reply in one short spoken sentence. "
            "Keep it natural, warm, and under 16 words. Do not reveal internal routing."
        )
        prompt = f"User said: {request.text}\nIntent: {request.route_decision.intent}\nReply for voice:"
        response = await self.services.ollama.generate_text(
            prompt,
            system=system,
            options={"temperature": 0.35, "num_predict": 80},
        )
        return self._clean_response(response, zh=zh)

    def _fallback_reply(self, request: AgentRunRequest) -> str:
        intent = request.route_decision.intent
        if self.is_zh(request):
            if request.route_decision.route == "clarify":
                return "你是指什么？"
            if intent == "emotional_support":
                return "听起来你有点累。"
            return "我明白。"
        if request.route_decision.route == "clarify":
            return "What do you mean?"
        if intent == "emotional_support":
            return "That sounds tiring."
        return "I understand."

    def _clean_response(self, response: str, *, zh: bool) -> str:
        response = " ".join((response or "").strip().strip('"').split())
        if not response:
            return "我明白。" if zh else "I understand."
        max_chars = self.services.max_speak_chars
        if len(response) > max_chars:
            response = response[:max_chars].rstrip("，,。.!！?？ ")
            response += "。" if zh else "."
        return response
