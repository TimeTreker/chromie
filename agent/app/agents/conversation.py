from __future__ import annotations

import logging
import time
from typing import Any, cast

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.conversation")


class ConversationAgent(BaseAgent):
    name = "conversation_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        started = time.perf_counter()
        logger.info(
            "conversation_agent_start sid=%s route=%s intent=%s agents=%s text_chars=%s text=%r use_llm=%s ollama_present=%s history_turns=%s pending_tasks=%s conversation_id=%s",
            request.sid,
            request.route_decision.route,
            request.route_decision.intent,
            request.route_decision.agents,
            len(request.text or ""),
            request.text,
            self.services.use_llm,
            self.services.ollama is not None,
            len(self._history_from_request(request)),
            len(self._pending_tasks_from_request(request)),
            self._conversation_id(request),
        )

        if getattr(result, "metadata", {}).get("capability_handled"):
            result.trace.append("conversation_agent: skipped because capability agent handled the request")
            return result

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
            logger.warning("conversation_agent_fallback sid=%s reason=llm_disabled", request.sid)
            result.trace.append("conversation_agent: llm disabled")
        elif self.services.ollama is None:
            logger.warning("conversation_agent_fallback sid=%s reason=ollama_client_missing", request.sid)
            result.trace.append("conversation_agent: ollama client missing")
        else:
            try:
                logger.info(
                    "conversation_agent_llm_start sid=%s model_call_expected=True text=%r history_turns=%s pending_tasks=%s conversation_id=%s",
                    request.sid,
                    request.text,
                    len(self._history_from_request(request)),
                    len(self._pending_tasks_from_request(request)),
                    self._conversation_id(request),
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
                self.trace(result, "generated llm reply with short-term context")
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

        fallback = self._fallback_reply(request)
        result.add_speak_immediate(fallback, style="brief")
        self.trace(result, "used fallback reply")
        return result

    async def _llm_reply(self, request: AgentRunRequest) -> str:
        assert self.services.ollama is not None
        zh = self.is_zh(request)
        history_block = self._format_history(request, zh=zh)
        pending_block = self._format_pending_tasks(request, zh=zh)
        conversation_id = self._conversation_id(request)
        capability_context = self._capability_context(request, zh=zh)

        if zh:
            system = (
                "你是 Chromie 的对话 agent。"
                "你会收到当前用户话语、最近几轮对话、以及可能的待处理任务。"
                "如果用户说‘那个/它/什么时候/结果呢/继续’这类追问，请根据最近上下文理解。"
                "如果用户问之前任务什么时候有结果，而待处理任务还在进行中，就说明还在处理。"
                "不要假装记得上下文里没有的事情，也不要编造工具结果。"
                "回答能力问题前必须检查提供的能力目录；不要声称机器人断开，除非目录明确不可用。"
                "不要描述身体动作或舞台指令；表情动作会由运行时单独处理。"
                "回复要适合语音播放，默认一句话，不超过 24 个中文字。"
                "请只输出要说的话，不要输出 JSON。"
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"最近对话：\n{history_block}\n\n"
                f"待处理任务：\n{pending_block}\n\n"
                f"能力目录：\n{capability_context}\n\n"
                f"当前用户说：{request.text}\n"
                f"当前意图：{request.route_decision.intent}\n"
                "请结合最近上下文自然回复。"
            )
        else:
            system = (
                "You are Chromie's conversation agent. "
                "You receive the current user message, recent conversation turns, and pending task hints. "
                "Use short-term context to answer follow-up questions like 'when will you give me the answer?' or 'what about it?'. "
                "If the user asks about a previous pending task, refer to that task and say it is still in progress unless a result is provided. "
                "Do not invent tool results. Do not pretend to remember anything outside the provided context. "
                "Before answering capability questions, inspect the supplied capability catalog. Do not claim the robot is disconnected unless the catalog says it is unavailable. "
                "Do not describe body gestures or stage directions; expressive motion is handled separately by the runtime. "
                "The reply will be spoken aloud, so keep it to one short sentence. "
                "Reply with only the spoken response text. Do not output JSON."
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"Recent conversation:\n{history_block}\n\n"
                f"Pending tasks:\n{pending_block}\n\n"
                f"Capability catalog:\n{capability_context}\n\n"
                f"Current user said: {request.text}\n"
                f"Current intent: {request.route_decision.intent}\n"
                "Reply naturally using the recent context when relevant."
            )

        raw = await self.services.ollama.generate(
            prompt,
            system=system,
            options={
                "temperature": 0.35,
                "top_p": 0.9,
                "num_predict": 96,
                "stop": ["\nUser:", "\nAssistant:", "\n用户：", "\n助手："],
            },
        )
        response = cast(str, raw)
        return self._clean_response(response, zh=zh)

    def _conversation_id(self, request: AgentRunRequest) -> str | None:
        context = request.context or {}
        cid = context.get("conversation_id")
        if cid:
            return str(cid)
        conversation = context.get("conversation")
        if isinstance(conversation, dict) and conversation.get("conversation_id"):
            return str(conversation.get("conversation_id"))
        return None

    def _history_from_request(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        if request.history:
            return [turn for turn in request.history if isinstance(turn, dict)]
        context = request.context or {}
        history = context.get("history")
        if isinstance(history, list):
            return [turn for turn in history if isinstance(turn, dict)]
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            history = conversation.get("history")
            if isinstance(history, list):
                return [turn for turn in history if isinstance(turn, dict)]
        return []

    def _pending_tasks_from_request(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        context = request.context or {}
        tasks = context.get("active_pending_tasks") or context.get("pending_tasks")
        if not isinstance(tasks, list):
            conversation = context.get("conversation")
            if isinstance(conversation, dict):
                tasks = conversation.get("active_pending_tasks") or conversation.get("pending_tasks")
        if not isinstance(tasks, list):
            return []
        return [task for task in tasks if isinstance(task, dict)]

    def _format_history(self, request: AgentRunRequest, *, zh: bool) -> str:
        history = self._history_from_request(request)
        if not history:
            return "无" if zh else "None"
        lines: list[str] = []
        for turn in history[-8:]:
            role = str(turn.get("role") or "unknown").lower()
            text = " ".join(str(turn.get("text") or "").split())
            if not text:
                continue
            if len(text) > 220:
                text = text[:220].rstrip() + "…"
            if zh:
                label = "用户" if role == "user" else "助手" if role == "assistant" else role
            else:
                label = "User" if role == "user" else "Assistant" if role == "assistant" else role.title()
            intent = turn.get("intent")
            suffix = f" ({intent})" if intent and role == "user" else ""
            lines.append(f"{label}{suffix}: {text}")
        return "\n".join(lines) if lines else ("无" if zh else "None")

    def _format_pending_tasks(self, request: AgentRunRequest, *, zh: bool) -> str:
        tasks = self._pending_tasks_from_request(request)
        if not tasks:
            return "无" if zh else "None"
        lines: list[str] = []
        for task in tasks[-4:]:
            task_type = str(task.get("type") or "task")
            status = str(task.get("status") or "pending")
            summary = " ".join(str(task.get("summary") or task_type).split())
            if zh:
                lines.append(f"- {task_type}: {status}; {summary}")
            else:
                lines.append(f"- {task_type}: {status}; {summary}")
        return "\n".join(lines) if lines else ("无" if zh else "None")

    def _capability_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        candidates = request.route_decision.candidate_capabilities
        if not candidates:
            candidates = request.context.get("capability_candidates") or []
        if not isinstance(candidates, list) or not candidates:
            return "无匹配能力" if zh else "No matching capabilities were supplied."
        lines: list[str] = []
        for item in candidates[:8]:
            if not isinstance(item, dict):
                continue
            capability_id = str(item.get("capability_id") or item.get("skill_id") or "")
            description = str(item.get("description") or "")
            executable = bool(item.get("interaction_executable"))
            label = "可执行" if zh and executable else "仅供规划" if zh else "executable" if executable else "planning only"
            lines.append(f"- {capability_id}: {description} [{label}]")
        return "\n".join(lines) if lines else ("无匹配能力" if zh else "No matching capabilities were supplied.")

    def _fallback_reply(self, request: AgentRunRequest) -> str:
        text = request.text.strip().lower()
        intent = request.route_decision.intent
        has_history = bool(self._history_from_request(request))
        has_pending = bool(self._pending_tasks_from_request(request))

        if self.is_zh(request):
            if request.route_decision.route == "clarify":
                return "你是指什么？"
            if has_pending and any(word in text for word in ["什么时候", "结果", "刚才", "那个", "它", "查到"]):
                return "我还在处理刚才的任务。"
            if has_history and any(word in text for word in ["什么时候", "结果", "刚才", "那个", "它"]):
                return "我还记得刚才的上下文。"
            if intent == "emotional_support":
                return "听起来你有点累。"
            if text in {"你好", "喂", "哈喽"}:
                return "你好，我在。"
            return "我听到了，但我现在没连上大脑。"

        if request.route_decision.route == "clarify":
            return "What do you mean?"
        if has_pending and any(phrase in text for phrase in ["when", "answer", "result", "that", "it", "what about", "done"]):
            return "I am still working on the previous task."
        if has_history and any(phrase in text for phrase in ["when", "answer", "result", "that", "it", "what about"]):
            return "I remember the previous context, but my language model is not responding."
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
            "助手：",
            "回答：",
        ]
        lowered = response.lower()
        for prefix in bad_prefixes:
            if lowered.startswith(prefix):
                response = response[len(prefix) :].strip()
                break

        max_chars = self.services.max_speak_chars
        if len(response) > max_chars:
            response = response[:max_chars].rstrip("，,。.!！?？ ")
            response += "。" if zh else "."
        return response
