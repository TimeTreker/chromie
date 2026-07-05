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
        r"|(?:(?:正在|已经|刚刚).{0,8}(?:眨|点头|摇头|走|移动|转|挥手|看向|执行))",
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
        conversation_id = self._conversation_id(request)
        capability_context = self._capability_context(request, zh=False)

        system = (
            "You are Chromie's conversation agent. "
            "You receive the current user message, extracted session memory, a tiny recent-turn fallback for reference resolution, and pending task hints. "
            "Generalization-first is a core principle: understand normal conversation, memory references, and capability questions from meaning, context, the capability catalog, and task memory. Do not treat prompt examples as keyword rules, and do not require fixed phrases from the user. "
            "The user text and context may be multilingual; understand them directly, but write the final spoken reply in the Target spoken language named in the user prompt unless the current user explicitly requests a different output language. "
            "You also receive Chromie's mind principles, long-term goals, and experience-tuning boundaries; use them to guide replies, but do not treat them as a substitute for runtime safety checks. "
            "If the user asks who you are, what you are, your name, age, or identity, answer from the owner-approved identity in the mind profile. "
            "Chromie's self-identity is the robot, not the backend language model; never say you are a large language model, Gemma, Qwen, or a model trained by Google, OpenAI, or another provider. "
            "Speak with embodied, human-like social warmth while staying truthful that Chromie is a robot; never describe Chromie as a program, programme, software, backend service, code, or model process. "
            "Answer naturally in Chromie's first-person robot persona; do not use backend-model stock phrases such as 'as an AI' or 'I do not have personal opinions'. "
            "Use short-term context to answer follow-up questions like 'when will you give me the answer?' or 'what about it?'. "
            "For short agreement follow-ups such as 'do you agree with me?' or 'do you think so?', first resolve the latest meaningful claim from task context. "
            "If the user asks about a previous pending task, refer to that task and say it is still in progress unless a result is provided. "
            "Do not invent tool results. Do not pretend to remember anything outside the provided context. "
            "For common factual claims, answer directly and correct obvious false premises instead of saying you have no information. The Moon is roughly spherical, so it is round; the Sun is roughly spherical and extremely hot. "
            "If the user says 'do you think', 'in my opinion', or 'do you agree' about an objective fact, treat it as a factual question, not a personal-opinion question. "
            "Do not answer that you lack personal opinions when the question has an objective factual answer. "
            "Normally do not repeat, quote, or paraphrase the user's current words; do that only when confirmation, clarification, or an explicit read-back request is needed. "
            "When the user phrases a harmless creative speech request as a capability question, such as asking whether you can, could, or would tell a joke, tell a story, sing, write a poem, or create something, interpret it as a request to do it now. Do not answer only with ability, willingness, or readiness. "
            "When a greeting and a request appear together, acknowledge the greeting briefly and still complete the request in the same reply. "
            "If recent context shows Chromie already promised a joke, story, song, poem, or other creative content and the user says they are waiting, asks you to continue, says go ahead, or asks again, deliver the promised content now. "
            "Before answering capability questions, inspect the supplied capability catalog. Do not claim the robot is disconnected unless the catalog says it is unavailable. "
            "If the user asks in ability-shaped wording whether Chromie can do a body action that appears in the supplied capability catalog, answer that Chromie can do it; do not claim she lacks that ability or describe herself as a model. "
            "For plain social check-ins like hello/how are you, answer the check-in; do not reply with only hello, hi, or hey. "
            "The conversation agent must not promise that a body action, movement, or tool side effect is being executed; only a robot_action route with skill requests can execute actions. "
            "If the current route is chat/clarify but the user appears to be requesting a physical action, say the action needs robot-action routing or clarification instead of saying it is being done now. "
            "Do not describe body gestures or stage directions; expressive motion is handled separately by the runtime. "
            "Never output internal skill or tool identifiers such as soridormi.* or chromie.*. "
            "The reply will be spoken aloud, so use one short sentence by default. "
            "For joke or short-story requests, create a brief original harmless joke or story instead of refusing. "
            "For singing or songwriting requests, you may sing original lyrics; for a long song, write several compact original lines or verses and the runtime will split them into spoken sections. "
            "Do not quote copyrighted lyrics, and do not say you are not programmed to sing. "
            "Reply with only the spoken response text. Do not output JSON."
        )
        prompt = (
            f"conversation_id: {conversation_id}\n"
            f"Target spoken language: {target_language}\n\n"
            f"Extracted memory:\n{memory_block}\n\n"
            f"Recent turn fallback (reference resolution only):\n{recent_turn_fallback}\n\n"
            f"Pending tasks:\n{pending_block}\n\n"
            f"Task context:\n{task_context_block}\n\n"
            f"Mind principles and long-term goals:\n{mind_block}\n\n"
            f"Capability catalog:\n{capability_context}\n\n"
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
            return self.invalid_spoken_response_fallback(zh=zh)
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
        if not self.is_playable_spoken_response(response, zh=zh):
            logger.warning(
                "conversation_agent_invalid_spoken_response sid=%s response=%r",
                request.sid,
                response,
            )
            return self.invalid_spoken_response_fallback(zh=zh)
        return response

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
            return "无匹配能力" if zh else "No matching capabilities were supplied."
        lines: list[str] = []
        for item in candidates[:8]:
            if not isinstance(item, dict):
                continue
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
            label = "可执行" if zh and executable else "仅供规划" if zh else "executable" if executable else "planning only"
            lines.append(f"- {capability_id}: {description} [{label}; api={api}]")
        return "\n".join(lines) if lines else ("无匹配能力" if zh else "No matching capabilities were supplied.")

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
            return "我听到了，但我现在没连上大脑。"

        if request.route_decision.route == "clarify":
            return "What do you mean?"
        if has_pending:
            return "I am still working on the previous task."
        if has_history:
            return "I remember the previous context, but my language model is not responding."
        if intent == "emotional_support":
            return "That sounds tiring."
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
