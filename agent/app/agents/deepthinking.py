from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.deepthinking")


class DeepThinkingAgent(BaseAgent):
    name = "deepthinking_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        started = time.perf_counter()
        logger.info(
            "deepthinking_agent_start sid=%s route=%s intent=%s agents=%s text_chars=%s text=%r use_llm=%s ollama_present=%s history_turns=%s pending_tasks=%s conversation_id=%s",
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
            result.trace.append("deepthinking_agent: skipped because capability agent handled the request")
            return result

        if request.route_decision.route != "deep_thought" and self.name not in request.route_decision.agents:
            logger.info(
                "deepthinking_agent_skip sid=%s reason=route_not_handled route=%s agents=%s",
                request.sid,
                request.route_decision.route,
                request.route_decision.agents,
            )
            return result

        text = request.text.strip()
        if not text:
            result.status = "ignored"
            result.reason = "empty_text"
            self.trace(result, "ignored empty text")
            return result

        if not self.services.use_llm:
            logger.warning("deepthinking_agent_fallback sid=%s reason=llm_disabled", request.sid)
            result.trace.append("deepthinking_agent: llm disabled")
        elif self.services.ollama is None:
            logger.warning("deepthinking_agent_fallback sid=%s reason=ollama_client_missing", request.sid)
            result.trace.append("deepthinking_agent: ollama client missing")
        else:
            try:
                logger.info(
                    "deepthinking_agent_llm_start sid=%s model_call_expected=True text=%r history_turns=%s pending_tasks=%s conversation_id=%s",
                    request.sid,
                    request.text,
                    len(self._history_from_request(request)),
                    len(self._pending_tasks_from_request(request)),
                    self._conversation_id(request),
                )
                response = await self._llm_reply(request)
                logger.info(
                    "deepthinking_agent_llm_done sid=%s response_chars=%s response=%r elapsed_ms=%.1f",
                    request.sid,
                    len(response),
                    response,
                    (time.perf_counter() - started) * 1000.0,
                )
                self._add_spoken_response(result, response)
                self.trace(result, "generated deep-thinking plan with session memory")
                return result
            except Exception as exc:
                logger.exception(
                    "deepthinking_agent_llm_failed sid=%s error_type=%s error=%s elapsed_ms=%.1f",
                    request.sid,
                    type(exc).__name__,
                    exc,
                    (time.perf_counter() - started) * 1000.0,
                )
                result.trace.append(f"deepthinking_agent: llm failed: {type(exc).__name__}: {exc}")

        fallback = self._fallback_reply(request)
        result.add_speak_immediate(fallback, style="brief")
        self.trace(result, "used fallback reply")
        return result

    async def _llm_reply(self, request: AgentRunRequest) -> str:
        assert self.services.ollama is not None
        zh = self.is_zh(request)
        history_block = self._format_history(request, zh=zh)
        pending_block = self._format_pending_tasks(request, zh=zh)
        session_memory_block = self._format_session_memory(request, zh=zh)
        conversation_id = self._conversation_id(request)
        capability_context = self._capability_context(request, zh=zh)
        route_context = self._route_context(request, zh=zh)

        if zh:
            system = (
                "你是 Chromie 的 deepthinking agent，不是普通对话 agent。"
                "你的职责是把复杂请求拆成清晰任务，结合会话工作记忆做架构、排错、计划和决策。"
                "请在内部完成推理，只输出最终回答；不要输出思考过程。"
                "如果用户请求适合拆分任务，请给出有顺序的简洁任务拆分、关键风险和下一步。"
                "如果任务需要继续执行工具、代码修改或机器人动作，只能说明计划或请求确认，不能编造结果。"
                "不要假装记得上下文里没有的事情，也不要编造工具结果。"
                "能力目录只表示可用能力，不是授权；不要发明能力、低层电机命令或原始关节动作。"
                "回答要适合语音分段播放，可以比普通对话完整，但仍要简洁。"
                "请只输出要说的话，不要输出 JSON。"
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"会话工作记忆：\n{session_memory_block}\n\n"
                f"最近对话：\n{history_block}\n\n"
                f"待处理任务：\n{pending_block}\n\n"
                f"能力目录：\n{capability_context}\n\n"
                f"上游路由上下文：\n{route_context}\n\n"
                f"当前用户说：{request.text}\n"
                f"当前意图：{request.route_decision.intent}\n"
                "请结合会话工作记忆，把复杂任务拆清楚，并给出最终可播放回答。"
            )
        else:
            system = (
                "You are Chromie's deepthinking agent, not the normal conversation agent. "
                "Your job is to split complex requests into clear tasks and use session working memory for architecture, debugging, planning, and decisions. "
                "Reason privately and output only the final answer, never the hidden chain of thought. "
                "When the request benefits from task decomposition, give an ordered, concise task split, key risks, and the next step. "
                "If more tools, code changes, or robot actions are needed, describe the plan or ask for confirmation; do not invent results. "
                "Do not pretend to remember anything outside the supplied context, and do not invent tool results. "
                "The capability catalog describes available abilities, not authorization; never invent capabilities, low-level motor commands, or raw joint actions. "
                "The reply will be spoken aloud, so be complete but concise enough for chunked voice playback. "
                "Reply with only the spoken response text. Do not output JSON."
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"Session working memory:\n{session_memory_block}\n\n"
                f"Recent conversation:\n{history_block}\n\n"
                f"Pending tasks:\n{pending_block}\n\n"
                f"Capability catalog:\n{capability_context}\n\n"
                f"Upstream routing context:\n{route_context}\n\n"
                f"Current user said: {request.text}\n"
                f"Current intent: {request.route_decision.intent}\n"
                "Use the session working memory, split the complex task clearly when useful, and give the final spoken response."
            )

        raw = await self.services.ollama.generate(
            prompt,
            system=system,
            options={
                "temperature": 0.25,
                "top_p": 0.9,
                "num_predict": 384,
                "stop": ["\nUser:", "\nAssistant:", "\n用户：", "\n助手："],
            },
        )
        response = cast(str, raw)
        return self._clean_response(response, zh=zh)

    def _add_spoken_response(self, result: AgentResult, response: str) -> None:
        for chunk in self._split_spoken_response(response):
            result.add_speak_immediate(chunk, style="brief")

    def _split_spoken_response(self, response: str) -> list[str]:
        text = " ".join((response or "").strip().split())
        if not text:
            return []
        max_chars = max(1, self.services.max_speak_chars)
        max_total = max_chars * 4
        if len(text) > max_total:
            text = text[:max_total].rstrip("，,。.!！?？ ")
            text += "。" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "."
        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        current = ""
        for word in text.split(" "):
            candidate = f"{current} {word}".strip() if current else word
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current.rstrip("，,。.!！?？ "))
            if len(word) <= max_chars:
                current = word
                continue
            for offset in range(0, len(word), max_chars):
                piece = word[offset : offset + max_chars]
                if len(piece) == max_chars:
                    chunks.append(piece)
                else:
                    current = piece
        if current:
            chunks.append(current.rstrip("，,。.!！?？ "))
        return [chunk for chunk in chunks if chunk]

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

    def _session_memory_from_request(self, request: AgentRunRequest) -> dict[str, Any]:
        context = request.context or {}
        memory = context.get("session_memory")
        if isinstance(memory, dict):
            return memory
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            memory = conversation.get("session_memory")
            if isinstance(memory, dict):
                return memory
        return {}

    def _format_session_memory(self, request: AgentRunRequest, *, zh: bool) -> str:
        memory = self._session_memory_from_request(request)
        if not memory:
            return "无" if zh else "None"
        compact = json.dumps(memory, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(compact) > 1200:
            compact = compact[:1200].rstrip() + "..."
        return compact

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
                text = text[:220].rstrip() + "..."
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

    def _route_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        decision = request.route_decision
        parts = [
            f"route={decision.route}",
            f"intent={decision.intent}",
            f"confidence={decision.confidence:.2f}",
            f"source={decision.source}",
        ]
        if decision.reason:
            parts.append(f"reason={decision.reason}")
        if decision.speak_first:
            parts.append(f"speak_first={decision.speak_first}")
        return "；".join(parts) if zh else "; ".join(parts)

    def _fallback_reply(self, request: AgentRunRequest) -> str:
        if self.is_zh(request):
            return "我可以把这个复杂任务拆开，但我现在没连上深度思考模型。"
        return "I can split this into a plan, but my deep-thinking model is not responding."

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

        return response
