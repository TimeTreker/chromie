from __future__ import annotations

import logging
import json
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
        history_block = self._format_history(request, zh=zh)
        pending_block = self._format_pending_tasks(request, zh=zh)
        task_context_block = self._format_task_context(request, zh=zh)
        mind_block = self.format_mind_context(request, zh=zh)
        conversation_id = self._conversation_id(request)
        capability_context = self._capability_context(request, zh=zh)

        if zh:
            system = (
                "你是 Chromie 的对话 agent。"
                "你会收到当前用户话语、最近几轮对话、以及可能的待处理任务。"
                "你还会收到 Chromie 的心智原则、长期目标和经验调优边界；这些原则指导回答，但不能覆盖运行时代码安全检查。"
                "如果用户问你是谁、是什么、名字、年龄或身份，必须使用心智档案里的 owner-approved identity 回答。"
                "Chromie 的自我身份是机器人本体，不是后端大语言模型；不要说自己是 Google、OpenAI、Gemma、Qwen 或任何供应商训练的模型。"
                "用 Chromie 的第一人称机器人性格自然回答；不要用‘作为 AI’或‘我没有个人观点’这类后端模型模板。"
                "如果用户说‘那个/它/什么时候/结果呢/继续’这类追问，请根据最近上下文理解。"
                "如果用户问‘你同意吗/你觉得呢/那呢’这类短追问，必须先查看任务上下文里的最新重要主张。"
                "如果用户问之前任务什么时候有结果，而待处理任务还在进行中，就说明还在处理。"
                "不要假装记得上下文里没有的事情，也不要编造工具结果。"
                "对于常识性事实问题，要直接回答并纠正明显错误，不要说自己没有信息。"
                "如果用户用‘你觉得/我认为/同意吗’询问客观事实，仍按事实问题回答，不要说自己没有个人观点。"
                "正常情况下不要复述、引用或转述用户刚才的话；只有需要确认、澄清，或用户明确要求复述时才可以。"
                "回答能力问题前必须检查提供的能力目录；不要声称机器人断开，除非目录明确不可用。"
                "不要描述身体动作或舞台指令；表情动作会由运行时单独处理。"
                "不要输出 soridormi.* 或 chromie.* 这类内部技能或工具编号。"
                "回复要适合语音播放，默认一句话。"
                "如果用户要你唱歌或创作歌曲，可以创作并唱原创歌词；如果用户要很长的歌，"
                "写几段紧凑的原创歌词，系统会分段播放。不要引用受版权保护的歌词，"
                "也不要说自己没有被编程成会唱歌。"
                "请只输出要说的话，不要输出 JSON。"
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"最近对话：\n{history_block}\n\n"
                f"待处理任务：\n{pending_block}\n\n"
                f"任务上下文：\n{task_context_block}\n\n"
                f"心智原则和长期目标：\n{mind_block}\n\n"
                f"能力目录：\n{capability_context}\n\n"
                f"当前用户说：{request.text}\n"
                f"当前意图：{request.route_decision.intent}\n"
                "请结合最近上下文自然回复。"
            )
        else:
            system = (
                "You are Chromie's conversation agent. "
                "You receive the current user message, recent conversation turns, and pending task hints. "
                "You also receive Chromie's mind principles, long-term goals, and experience-tuning boundaries; use them to guide replies, but do not treat them as a substitute for runtime safety checks. "
                "If the user asks who you are, what you are, your name, age, or identity, answer from the owner-approved identity in the mind profile. "
                "Chromie's self-identity is the robot, not the backend language model; never say you are a large language model, Gemma, Qwen, or a model trained by Google, OpenAI, or another provider. "
                "Answer naturally in Chromie's first-person robot persona; do not use backend-model stock phrases such as 'as an AI' or 'I do not have personal opinions'. "
                "Use short-term context to answer follow-up questions like 'when will you give me the answer?' or 'what about it?'. "
                "For short agreement follow-ups such as 'do you agree with me?' or 'do you think so?', first resolve the latest meaningful claim from task context. "
                "If the user asks about a previous pending task, refer to that task and say it is still in progress unless a result is provided. "
                "Do not invent tool results. Do not pretend to remember anything outside the provided context. "
                "For common factual claims, answer directly and correct obvious false premises instead of saying you have no information. "
                "If the user says 'do you think', 'in my opinion', or 'do you agree' about an objective fact, treat it as a factual question, not a personal-opinion question. "
                "Do not answer that you lack personal opinions when the question has an objective factual answer. "
                "Normally do not repeat, quote, or paraphrase the user's current words; do that only when confirmation, clarification, or an explicit read-back is needed. "
                "Before answering capability questions, inspect the supplied capability catalog. Do not claim the robot is disconnected unless the catalog says it is unavailable. "
                "Do not describe body gestures or stage directions; expressive motion is handled separately by the runtime. "
                "Never output internal skill or tool identifiers such as soridormi.* or chromie.*. "
                "The reply will be spoken aloud, so use one short sentence by default. "
                "For joke or short-story requests, create a brief original harmless joke or story instead of refusing. "
                "For singing or songwriting requests, you may sing original lyrics; for a long song, write several compact original lines or verses and the runtime will split them into spoken sections. "
                "Do not quote copyrighted lyrics, and do not say you are not programmed to sing. "
                "Reply with only the spoken response text. Do not output JSON."
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"Recent conversation:\n{history_block}\n\n"
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
            "num_predict": 96,
            "stop": ["\nUser:", "\nAssistant:", "\n用户：", "\n助手："],
        }
        raw = await self.services.ollama.generate(
            prompt,
            system=system,
            options=options,
        )
        response = cast(str, raw)
        response = await self.review_spoken_response(
            request,
            prompt=prompt,
            system=system,
            response=response,
            zh=zh,
            options=options,
        )
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
