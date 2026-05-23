from __future__ import annotations

import logging
import time
from typing import cast

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent


logger = logging.getLogger("chromie.agent.conversation")


class ConversationAgent(BaseAgent):
    name = "conversation_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        started = time.perf_counter()

        logger.info(
            "conversation_agent_start sid=%s route=%s intent=%s agents=%s text_chars=%s text=%r use_llm=%s ollama_present=%s",
            request.sid,
            request.route_decision.route,
            request.route_decision.intent,
            request.route_decision.agents,
            len(request.text or ""),
            request.text,
            self.services.use_llm,
            self.services.ollama is not None,
        )

        if request.route_decision.route not in {"chat", "clarify"} and self.name not in request.route_decision.agents:
            logger.info(
                "conversation_agent_skip sid=%s reason=route_not_handled route=%s agents=%s",
                request.sid,
                request.route_decision.route,
                request.route_decision.agents,
            )
            return result

        if request.route_decision.speak_first:
            result.add_speak_immediate(request.route_decision.speak_first, style="brief")
            self.trace(result, "used router speak_first")
            logger.info(
                "conversation_agent_done sid=%s mode=router_speak_first elapsed_ms=%.1f text=%r",
                request.sid,
                (time.perf_counter() - started) * 1000.0,
                request.route_decision.speak_first,
            )
            return result

        text = request.text.strip()
        if not text:
            result.status = "ignored"
            result.reason = "empty_text"
            self.trace(result, "ignored empty text")
            logger.info(
                "conversation_agent_done sid=%s mode=ignored reason=empty_text elapsed_ms=%.1f",
                request.sid,
                (time.perf_counter() - started) * 1000.0,
            )
            return result

        if not self.services.use_llm:
            logger.warning(
                "conversation_agent_fallback sid=%s reason=llm_disabled",
                request.sid,
            )
            result.trace.append("conversation_agent: llm disabled")

        elif self.services.ollama is None:
            logger.warning(
                "conversation_agent_fallback sid=%s reason=ollama_client_missing",
                request.sid,
            )
            result.trace.append("conversation_agent: ollama client missing")

        else:
            try:
                logger.info(
                    "conversation_agent_llm_start sid=%s model_call_expected=True text=%r",
                    request.sid,
                    request.text,
                )

                response = await self._llm_reply(request)

                logger.info(
                    "conversation_agent_llm_done sid=%s response_chars=%s response=%r elapsed_ms=%.1f",
                    request.sid,
                    len(response),
                    response,
                    (time.perf_counter() - started) * 1000.0,
                )

                result.add_speak_immediate(response, style="brief")
                self.trace(result, "generated llm reply")
                return result

            except Exception as exc:
                logger.exception(
                    "conversation_agent_llm_failed sid=%s error_type=%s error=%s elapsed_ms=%.1f",
                    request.sid,
                    type(exc).__name__,
                    exc,
                    (time.perf_counter() - started) * 1000.0,
                )
                result.trace.append(f"conversation_agent: llm failed: {type(exc).__name__}: {exc}")

        fallback = self._fallback_reply(request)
        result.add_speak_immediate(fallback, style="brief")
        self.trace(result, "used fallback reply")

        logger.info(
            "conversation_agent_done sid=%s mode=fallback fallback=%r elapsed_ms=%.1f",
            request.sid,
            fallback,
            (time.perf_counter() - started) * 1000.0,
        )

        return result

    async def _llm_reply(self, request: AgentRunRequest) -> str:
        assert self.services.ollama is not None

        zh = self.is_zh(request)

        if zh:
            system = (
                "你是 Chromie 的对话 agent。"
                "请根据用户真实内容自然回复。"
                "回复要适合语音播放，默认一句话，不超过 20 个中文字。"
                "不要总是说“我明白”。"
                "如果 ASR 文本很奇怪或不清楚，就用一句话追问。"
            )
            prompt = (
                f"用户说：{request.text}\n"
                f"意图：{request.route_decision.intent}\n"
                "请只输出要说的话，不要输出 JSON。"
            )
        else:
            system = (
                "You are Chromie's conversation agent. "
                "Reply naturally to the user's actual message. "
                "The reply will be spoken aloud, so keep it to one short sentence. "
                "Do not always say 'I understand'. "
                "If the ASR text is strange or unclear, ask a short clarification question."
            )
            prompt = (
                f"User said: {request.text}\n"
                f"Intent: {request.route_decision.intent}\n"
                "Reply with only the spoken response text. Do not output JSON."
            )

        raw = await self.services.ollama.generate(
            prompt,
            system=system,
            options={
                "temperature": 0.45,
                "top_p": 0.9,
                "num_predict": 80,
            },
        )

        response = cast(str, raw)
        return self._clean_response(response, zh=zh)

    def _fallback_reply(self, request: AgentRunRequest) -> str:
        text = request.text.strip().lower()
        intent = request.route_decision.intent

        if self.is_zh(request):
            if request.route_decision.route == "clarify":
                return "你是指什么？"
            if intent == "emotional_support":
                return "听起来你有点累。"
            if text in {"你好", "喂", "哈喽"}:
                return "你好，我在。"
            return "我听到了，但我现在没连上大脑。"

        if request.route_decision.route == "clarify":
            return "What do you mean?"
        if intent == "emotional_support":
            return "That sounds tiring."
        if text in {"hello", "hello?", "hi", "hey", "what's up?", "whats up"}:
            return "Hey, I am here."

        return "I heard you, but my language model is not responding."

    def _clean_response(self, response: str, *, zh: bool) -> str:
        response = " ".join((response or "").strip().strip('"').split())

        if not response:
            return "我没太听清，你能再说一遍吗？" if zh else "I did not catch that. Could you say it again?"

        bad_prefixes = [
            "assistant:",
            "chromie:",
            "response:",
            "spoken response:",
        ]

        lowered = response.lower()
        for prefix in bad_prefixes:
            if lowered.startswith(prefix):
                response = response[len(prefix):].strip()
                break

        max_chars = self.services.max_speak_chars
        if len(response) > max_chars:
            response = response[:max_chars].rstrip("，,。.!！?？ ")
            response += "。" if zh else "."

        return response
