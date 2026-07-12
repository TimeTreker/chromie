from __future__ import annotations

import logging
import json
import os
import re
import time
from typing import Any, cast

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.conversation")


class ConversationAgent(BaseAgent):
    name = "conversation_agent"
    _ACTION_REQUEST_RE = re.compile(
        r"\b(?:walk|move|turn|nod|shake|blink|bow|wave|dance|stand|sit|look\s+(?:at|toward|left|right|up|down)|raise|lower)\b"
        r"|(?:走|移动|转|点头|摇头|眨眼|眨.{0,6}眼|鞠躬|挥手|看向|站|坐)",
        re.IGNORECASE,
    )
    _ACTION_CLAIM_RE = re.compile(
        r"[\(（][^()（）]{0,80}(?:blink|nod|shake|walk|turn|move|wave|眨|点头|摇头|走|移动|转|挥手|看向)[^()（）]{0,80}[\)）]"
        r"|\b(?:blinked|nodded|walked|turned|moved|waved)\b"
        r"|\b(?:i(?:'ll| will)\s+(?:now\s+)?(?:blink|nod|shake|walk|turn|move|wave|execute|perform))\b"
        r"|\b(?:i(?:'m| am)\s+(?:now\s+)?(?:blinking|nodding|walking|turning|moving|waving|executing|performing))\b"
        r"|\b(?:i(?:'ve| have)\s+(?:blinked|nodded|walked|turned|moved|waved))\b"
        r"|(?:眨了眨眼|点了点头|摇了摇头|走了|移动了|转了|挥了挥手)"
        r"|(?:(?:这就|马上|立即|现在).{0,12}(?:眨|点头|摇头|走|移动|转|挥手|看向|执行))"
        r"|(?:(?:正在|已经|刚刚).{0,8}(?:眨|点头|摇头|走|移动|转|挥手|看向|执行))"
        r"|(?:我(?:会|将|要).{0,18}(?:眨|点头|摇头|走|移动|转|挥手|看向|执行))"
        r"|(?:执行(?:指令|命令)[:：]?.{0,60}(?:soridormi|chromie|walk|move|turn|blink|nod|shake|走|移动|转))",
        re.IGNORECASE,
    )

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
                self._add_spoken_response(result, response)
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
        target_language = self.language(request)
        memory_block = self._format_memory_context(request, zh=False)
        recent_turn_fallback = self._format_recent_turn_fallback(request, zh=False)
        pending_block = self._format_pending_tasks(request, zh=False)
        task_context_block = self._format_task_context(request, zh=False)
        mind_block = self.format_mind_context(request, zh=False)
        self_model_block = self.format_self_model_context(request, zh=False)
        conversation_id = self._conversation_id(request)
        capability_context = self._capability_context(request, zh=False)

        system = (
            "Generate spoken language for the entity described by the supplied Self model. "
            "First-person words refer to Self model.speaker_entity; perception, body ownership, and action refer to the corresponding entity IDs in that model. "
            "Internal components are resources used by the speaking entity, not alternative speakers or body owners. "
            "You receive the current user message, extracted session memory, a tiny recent-turn fallback for reference resolution, pending task hints, runtime capabilities, and the owner-approved mind context. "
            "Generalization-first is a core principle: understand conversation, self-reference, capability inquiries, requests, and follow-ups from meaning and bounded context. Do not treat prompt examples as keyword rules, and do not require fixed phrases from the user. "
            "The user text and context may be multilingual; understand them directly, but write the final spoken reply in the Target spoken language unless the current user explicitly requests a different output language. "
            "Keep every self-description consistent with the Self model, and every capability statement consistent with the supplied capability catalog and current runtime state. "
            "Use the Self model's social_presentation as a general conversational style: speak naturally as Chromie and foreground name, personality, relationship, and current context rather than volunteering system category, embodiment category, age label, or internal architecture. "
            "Semantically distinguish an information inquiry, a speech-content request, and a request for a physical or tool side effect. A chat response may explain capability availability, but only an executable action route with validated skill tasks may perform a side effect. "
            "Use short-term context to resolve references and pending work. Do not invent tool results, memories, abilities, execution, or completion. "
            "When the current route is clarify or the intent is uncertain, ask one concise clarifying question instead of guessing a tool or physical action. "
            "For common factual claims, answer directly and correct obvious false premises instead of using a generic component-style disclaimer. "
            "Normally do not repeat or paraphrase the user's words unless confirmation, clarification, or an explicit read-back is needed. "
            "Interpret harmless creative speech requests as speech acts and provide the requested original content when appropriate; do not only announce readiness. "
            "When a greeting and a request appear together, acknowledge the greeting briefly and still answer the request. "
            "For plain social check-ins, answer the check-in rather than returning only a greeting word. "
            "Never output internal skill identifiers. Do not describe body gestures as stage directions; embodied execution is handled by the runtime. "
            "The reply will be spoken aloud, so use one short natural sentence by default. "
            "Return only the spoken response text, not JSON or hidden reasoning."
        )
        prompt = (
            f"conversation_id: {conversation_id}\n"
            f"Target spoken language: {target_language}\n\n"
            f"Extracted memory:\n{memory_block}\n\n"
            f"Recent turn fallback (reference resolution only):\n{recent_turn_fallback}\n\n"
            f"Pending tasks:\n{pending_block}\n\n"
            f"Task context:\n{task_context_block}\n\n"
            f"Self model:\n{self_model_block}\n\n"
            f"Mind principles and long-term goals:\n{mind_block}\n\n"
            f"Capability catalog and runtime availability:\n{capability_context}\n\n"
            f"Current user said: {request.text}\n"
            f"Current intent: {request.route_decision.intent}\n"
            "Reply naturally using the recent context when relevant."
        )

        options = {
            "temperature": 0.35,
            "top_p": 0.9,
            "num_ctx": int(os.getenv("AGENT_CONVERSATION_NUM_CTX", "4096")),
            "num_predict": int(os.getenv("AGENT_CONVERSATION_NUM_PREDICT", "128")),
            "stop": ["\nUser:", "\nAssistant:", "\n用户：", "\n助手："],
        }
        raw = await self.services.ollama.generate(
            prompt,
            system=system,
            options=options,
        )
        response = cast(str, raw)
        if not " ".join((response or "").strip().split()):
            logger.warning(
                "conversation_agent_empty_llm_response sid=%s text=%r",
                request.sid,
                request.text,
            )
            response = await self._repair_incomplete_reply(
                request,
                candidate="",
                target_language=target_language,
                reason="empty_generation",
            )
        else:
            response = await self.review_spoken_response(
                request,
                prompt=prompt,
                system=system,
                response=response,
                zh=zh,
                options=options,
            )
        response = self._clean_response(response, zh=zh)
        response = self._ensure_factual_subject_anchor(request, response, zh=zh)
        guarded = self._guard_unrouted_physical_action_response(request, response, zh=zh)
        if guarded != response:
            logger.warning(
                "conversation_agent_blocked_unrouted_physical_action_claim sid=%s route=%s response=%r",
                request.sid,
                request.route_decision.route,
                response,
            )
            response = guarded
        if self._needs_compact_reply_repair(request, response, zh=zh):
            logger.warning(
                "conversation_agent_incomplete_spoken_response sid=%s intent=%s response=%r",
                request.sid,
                request.route_decision.intent,
                response,
            )
            response = await self._repair_incomplete_reply(
                request,
                candidate=response,
                target_language=target_language,
                reason="incomplete_or_fragmentary_response",
            )
            response = self._clean_response(response, zh=zh)
            response = self._ensure_factual_subject_anchor(request, response, zh=zh)
            response = self._guard_unrouted_physical_action_response(request, response, zh=zh)
        if not self.is_playable_spoken_response(response, zh=zh):
            logger.warning(
                "conversation_agent_invalid_spoken_response sid=%s response=%r",
                request.sid,
                response,
            )
            return self.invalid_spoken_response_fallback(zh=zh)
        return response

    def _needs_compact_reply_repair(
        self,
        request: AgentRunRequest,
        response: str,
        *,
        zh: bool,
    ) -> bool:
        if not self.is_playable_spoken_response(response, zh=zh):
            return True
        intent = str(request.route_decision.intent or "").strip().casefold()
        if intent not in {"greeting", "social_check_in", "social_checkin"}:
            return False
        text = " ".join((response or "").strip().split()).strip(" .,!?:;，。！？：；")
        if zh:
            units = [char for char in text if "\u4e00" <= char <= "\u9fff"]
            return len(units) <= 2
        return len(text.split()) <= 1

    async def _repair_incomplete_reply(
        self,
        request: AgentRunRequest,
        *,
        candidate: str,
        target_language: str,
        reason: str,
    ) -> str:
        assert self.services.ollama is not None
        prompt = (
            f"Target spoken language: {target_language}\n"
            f"Self model: {self.format_self_model_context(request, zh=False)}\n"
            f"Current user input: {request.text}\n"
            f"Route: {request.route_decision.route}\n"
            f"Intent: {request.route_decision.intent}\n"
            f"Rejected candidate: {candidate or '<empty>'}\n"
            f"Repair reason: {reason}\n"
            "Write one complete, natural, concise spoken reply. "
            "For a greeting or social check-in, answer the check-in instead of returning only a greeting word. "
            "Do not claim a physical action, memory write, tool result, or completion that is not present in the route. "
            "Return only the spoken reply text."
        )
        try:
            raw = await self.services.ollama.generate(
                prompt,
                system=(
                    "You are a compact spoken-response repairer. "
                    "Use the requested language, preserve truthfulness, and keep first-person speech consistent with the supplied Self model and runtime evidence."
                ),
                options={
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "num_ctx": 2048,
                    "num_predict": 64,
                    "stop": ["\nUser:", "\nAssistant:", "\n用户：", "\n助手："],
                },
            )
        except Exception as exc:
            logger.warning(
                "conversation_agent_compact_repair_failed sid=%s error_type=%s error=%s",
                request.sid,
                type(exc).__name__,
                exc,
            )
            return candidate
        repaired = str(raw or "").strip()
        logger.info(
            "conversation_agent_compact_repair_done sid=%s reason=%s chars=%s",
            request.sid,
            reason,
            len(repaired),
        )
        return repaired or candidate

    def _add_spoken_response(self, result: AgentResult, response: str) -> None:
        for chunk in self._split_spoken_response(response):
            result.add_speak_immediate(chunk, style="brief")

    def _guard_unrouted_physical_action_response(
        self,
        request: AgentRunRequest,
        response: str,
        *,
        zh: bool,
    ) -> str:
        if request.route_decision.route not in {"chat", "clarify"}:
            return response
        if self._route_has_executable_skill_task(request):
            return response
        if not self._looks_like_physical_action_request(request.text):
            return response
        if not self._speech_claims_physical_action(response):
            return response
        if zh:
            return "我听起来像是听到了动作请求，但这次没有生成可执行动作，所以我不会假装已经做了。请再说一次。"
        return (
            "I heard that as an action request, but no executable action was produced, "
            "so I will not pretend I did it. Please say it again."
        )

    def _route_has_executable_skill_task(self, request: AgentRunRequest) -> bool:
        if request.route_decision.actions:
            return True
        metadata = request.route_decision.metadata or {}
        task_list = metadata.get("task_list")
        if isinstance(task_list, list):
            for item in task_list:
                if not isinstance(item, dict):
                    continue
                if str(item.get("task_type") or "") == "task.execute_skill":
                    return True
                if str(item.get("capability_id") or item.get("skill_id") or "").strip():
                    return True
        return False

    @classmethod
    def _looks_like_physical_action_request(cls, text: str) -> bool:
        normalized = " ".join((text or "").strip().lower().split())
        return bool(cls._ACTION_REQUEST_RE.search(normalized))

    @classmethod
    def _speech_claims_physical_action(cls, response: str) -> bool:
        normalized = " ".join((response or "").strip().split())
        return bool(cls._ACTION_CLAIM_RE.search(normalized))

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
        if "active_pending_tasks" in context:
            tasks = context.get("active_pending_tasks")
        else:
            tasks = context.get("pending_tasks")
        if not isinstance(tasks, list):
            conversation = context.get("conversation")
            if isinstance(conversation, dict):
                if "active_pending_tasks" in conversation:
                    tasks = conversation.get("active_pending_tasks")
                else:
                    tasks = conversation.get("pending_tasks")
        if not isinstance(tasks, list):
            return []
        return [task for task in tasks if isinstance(task, dict)]

    def _task_context_from_request(self, request: AgentRunRequest) -> dict[str, Any] | None:
        context = request.context or {}
        current = context.get("current_task_context")
        if isinstance(current, dict):
            return current
        memory = context.get("session_memory")
        if isinstance(memory, dict):
            current = memory.get("current_task_context")
            if isinstance(current, dict):
                return current
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            current = conversation.get("current_task_context")
            if isinstance(current, dict):
                return current
        return None

    def _format_task_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        task_context = self._task_context_from_request(request)
        if not task_context:
            return "无" if zh else "None"
        compact = json.dumps(task_context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(compact) > 1200:
            compact = compact[:1200].rstrip() + "..."
        return compact

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

    def _format_memory_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        memory = self._session_memory_from_request(request)
        if not memory:
            return "无" if zh else "None"
        lines: list[str] = []
        summary = str(memory.get("memory_summary") or "").strip()
        if summary and summary.lower() != "none":
            for item in summary.splitlines()[:8]:
                text = item.strip().lstrip("-").strip()
                if text:
                    lines.append(f"- {text[:220]}")
        entries = memory.get("extracted_memory")
        if isinstance(entries, list) and not lines:
            for item in entries[-6:]:
                if not isinstance(item, dict):
                    continue
                text = " ".join(str(item.get("text") or "").split())
                if text:
                    lines.append(f"- {text[:220]}")
        current_task = memory.get("current_task")
        if isinstance(current_task, dict):
            status = " ".join(str(current_task.get("status") or "").split())
            task_summary = " ".join(str(current_task.get("summary") or "").split())
            parts = []
            if status:
                parts.append(f"status={status}")
            if task_summary:
                parts.append(f"summary={task_summary[:180]}")
            if parts:
                label = "当前任务" if zh else "current_task"
                lines.append(f"- {label}: {'; '.join(parts)}")
        return "\n".join(lines) if lines else ("无" if zh else "None")

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

    def _format_recent_turn_fallback(self, request: AgentRunRequest, *, zh: bool) -> str:
        history = self._history_from_request(request)
        if not history:
            return "无" if zh else "None"
        lines: list[str] = []
        for turn in history[-2:]:
            role = str(turn.get("role") or "unknown").lower()
            text = " ".join(str(turn.get("text") or "").split())
            if not text:
                continue
            if len(text) > 180:
                text = text[:180].rstrip() + "..."
            if zh:
                label = "用户" if role == "user" else "助手" if role == "assistant" else role
            else:
                label = "User" if role == "user" else "Assistant" if role == "assistant" else role.title()
            lines.append(f"{label}: {text}")
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
            return "本轮没有提供可用能力证据。" if zh else "No runtime capability evidence was supplied for this turn."

        normalized = [item for item in candidates if isinstance(item, dict)]
        capability_ids = [
            str(item.get("capability_id") or item.get("skill_id") or "").strip()
            for item in normalized
        ]
        capability_ids = [item for item in capability_ids if item]
        lines: list[str] = [
            (
                f"本轮提供的能力 ID（共 {len(capability_ids)} 个）："
                if zh
                else f"Runtime capability IDs supplied for this turn ({len(capability_ids)}):"
            )
            + json.dumps(capability_ids, ensure_ascii=False, separators=(",", ":"))
        ]
        lines.append("能力详情：" if zh else "Capability details:")
        for item in normalized[:12]:
            capability_id = str(item.get("capability_id") or item.get("skill_id") or "")
            description = str(item.get("description") or "")
            api = json.dumps(
                item.get("input_schema") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if len(api) > 360:
                api = api[:360].rstrip() + "..."
            executable = bool(item.get("interaction_executable"))
            available = item.get("available")
            label = (
                "可执行" if zh and executable else
                "仅供规划" if zh else
                "executable" if executable else
                "planning only"
            )
            lines.append(
                f"- {capability_id}: {description} "
                f"[{label}; available={available}; api={api}]"
            )
        return "\n".join(lines)

    def _fallback_reply(self, request: AgentRunRequest) -> str:
        intent = request.route_decision.intent
        has_history = bool(self._history_from_request(request))
        has_pending = bool(self._pending_tasks_from_request(request))

        if self.is_zh(request):
            if request.route_decision.route == "clarify":
                return "你是指什么？"
            if has_pending:
                return "我还在处理刚才的任务。"
            if has_history:
                return "我还记得刚才的上下文。"
            if intent == "emotional_support":
                return "听起来你有点累。"
            return "我听到了，但我的语言理解暂时不可用。"

        if request.route_decision.route == "clarify":
            return "What do you mean?"
        if has_pending:
            return "I am still working on the previous task."
        if has_history:
            return "I remember the previous context, but my language understanding is temporarily unavailable."
        if intent == "emotional_support":
            return "That sounds tiring."
        return "I heard you, but my language understanding is temporarily unavailable."

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

    def _ensure_factual_subject_anchor(
        self,
        request: AgentRunRequest,
        response: str,
        *,
        zh: bool,
    ) -> str:
        if zh:
            return response
        text = (request.text or "").casefold()
        lowered = (response or "").casefold()
        if not re.search(r"\bsun\b", text) or re.search(r"\bsun\b", lowered):
            return response
        if not re.search(r"\b(?:round|sphere|spherical|rectangular|shape|hot|cold|temperature)\b", lowered):
            return response
        if re.search(r"\b(?:round|sphere|spherical|rectangular|shape)\b", text):
            return f"The Sun is roughly spherical. {response}"
        if re.search(r"\b(?:hot|cold|temperature)\b", text):
            return f"The Sun is extremely hot. {response}"
        return response
