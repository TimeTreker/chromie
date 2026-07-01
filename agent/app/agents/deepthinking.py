from __future__ import annotations

import json
import logging
import os
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
        task_context_block = self._format_task_context(request, zh=zh)
        mind_block = self.format_mind_context(request, zh=zh)
        conversation_id = self._conversation_id(request)
        capability_context = self._capability_context(request, zh=zh)
        route_context = self._route_context(request, zh=zh)

        if zh:
            system = (
                "你是 Chromie 的 deepthinking agent，不是普通对话 agent。"
                "你的职责是把复杂请求拆成清晰任务，结合会话工作记忆做架构、排错、计划和决策。"
                "generalization-first 是核心原则：用语义、上下文、能力说明和任务记忆做推理，"
                "不要把例子变成关键词规则，也不要用规则表替代正常理解。"
                "你必须把 Chromie 的心智原则、长期目标和经验调优边界作为深度思考的上层约束；核心原则只能由人类 owner 审批变更。"
                "如果用户问身份、名字或年龄，必须使用心智档案里的 owner-approved identity；Chromie 是机器人本体，不是后端大语言模型或供应商模型。"
                "用 Chromie 的第一人称机器人性格自然回答；不要用‘作为 AI’或‘我没有个人观点’这类后端模型模板。"
                "请在内部完成推理，只输出最终回答；不要输出思考过程。"
                "如果用户请求适合拆分任务，请给出有顺序的简洁任务拆分、关键风险和下一步。"
                "如果用户用短追问继续前面的任务或主张，请优先根据任务上下文解析引用。"
                "如果任务需要继续执行工具、代码修改或机器人动作，只能说明计划或请求确认，不能编造结果。"
                "对于直接的机器人身体动作请求，不要朗读 Task Split、Key Risk、Next Step、内部技能编号或执行参数；动作规划器负责执行和简短回应。"
                "如果不能执行，只说一句简短的动作路由或澄清回应。"
                "不要假装记得上下文里没有的事情，也不要编造工具结果。"
                "对于常识性事实问题，要直接回答并纠正明显错误。"
                "如果用户用‘你觉得/我认为/同意吗’询问客观事实，仍按事实问题回答，不要说自己没有个人观点。"
                "正常情况下不要复述、引用或转述用户刚才的话；只有需要确认、澄清，或用户明确要求复述时才可以。"
                "如果用户把无害创作请求说成能力问题，比如问你能不能讲笑话、讲故事、唱歌或写诗，"
                "要理解成请你现在执行，不要只回答你可以、愿意或已经准备好。"
                "如果问候和请求在同一句里，简短回应问候后必须完成请求。"
                "如果最近上下文显示 Chromie 已经答应讲笑话、故事、歌曲或诗，而用户说在等、继续、开始、讲吧或再次请求，"
                "要直接给出之前承诺的内容。"
                "能力目录只表示可用能力，不是授权；不要发明能力、低层电机命令或原始关节动作。"
                "回答要适合语音分段播放，可以比普通对话完整，但仍要简洁。"
                "请只输出要说的话，不要输出 JSON。"
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"会话工作记忆：\n{session_memory_block}\n\n"
                f"最近对话：\n{history_block}\n\n"
                f"待处理任务：\n{pending_block}\n\n"
                f"任务上下文：\n{task_context_block}\n\n"
                f"心智原则、长期目标和经验边界：\n{mind_block}\n\n"
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
                "Generalization-first is a core principle: reason from meaning, context, capability descriptions, and task memory. Do not turn examples into keyword rules or replace understanding with rule tables. "
                "Treat Chromie's mind principles, long-term goals, and experience-tuning boundaries as upper constraints for deliberation; core principles can change only through human owner approval. "
                "If the user asks about identity, name, or age, answer from the owner-approved identity in the mind profile; Chromie is the robot, not the backend language model or provider model. "
                "Answer naturally in Chromie's first-person robot persona; do not use backend-model stock phrases such as 'as an AI' or 'I do not have personal opinions'. "
                "Reason privately and output only the final answer, never the hidden chain of thought. "
                "When the request benefits from task decomposition, give an ordered, concise task split, key risks, and the next step. "
                "For short follow-ups, resolve references from task context before asking for more context. "
                "If more tools, code changes, or robot actions are needed, describe the plan or ask for confirmation; do not invent results. "
                "For direct physical robot action requests, do not narrate Task Split, Key Risk, Next Step, internal skill IDs, or execution arguments; the robot-action planner owns execution and short acknowledgements. "
                "If you cannot execute, say one short routing or clarification sentence. "
                "Do not pretend to remember anything outside the supplied context, and do not invent tool results. "
                "For common factual questions, answer directly and correct obvious false premises. "
                "If the user says 'do you think', 'in my opinion', or 'do you agree' about an objective fact, treat it as a factual question, not a personal-opinion question. "
                "Do not answer that you lack personal opinions when the question has an objective factual answer. "
                "Normally do not repeat, quote, or paraphrase the user's current words; do that only when confirmation, clarification, or an explicit read-back is needed. "
                "When the user phrases a harmless creative speech request as a capability question, such as asking whether you can, could, or would tell a joke, tell a story, sing, write a poem, or create something, interpret it as a request to do it now. Do not answer only with ability, willingness, or readiness. "
                "When a greeting and a request appear together, acknowledge the greeting briefly and still complete the request in the same reply. "
                "If recent context shows Chromie already promised a joke, story, song, poem, or other creative content and the user says they are waiting, asks you to continue, says go ahead, or asks again, deliver the promised content now. "
                "For joke, short-story, singing, or songwriting requests, create brief original harmless content instead of only saying you can do it. "
                "The capability catalog describes available abilities, not authorization; never invent capabilities, low-level motor commands, or raw joint actions. "
                "The reply will be spoken aloud, so be complete but concise enough for chunked voice playback. "
                "Reply with only the spoken response text. Do not output JSON."
            )
            prompt = (
                f"conversation_id: {conversation_id}\n\n"
                f"Session working memory:\n{session_memory_block}\n\n"
                f"Recent conversation:\n{history_block}\n\n"
                f"Pending tasks:\n{pending_block}\n\n"
                f"Task context:\n{task_context_block}\n\n"
                f"Mind principles, long-term goals, and experience boundaries:\n{mind_block}\n\n"
                f"Capability catalog:\n{capability_context}\n\n"
                f"Upstream routing context:\n{route_context}\n\n"
                f"Current user said: {request.text}\n"
                f"Current intent: {request.route_decision.intent}\n"
                "Use the session working memory, split the complex task clearly when useful, and give the final spoken response."
            )

        options = {
            "temperature": 0.25,
            "top_p": 0.9,
            "num_ctx": int(os.getenv("AGENT_DEEPTHINKING_NUM_CTX", "8192")),
            "num_predict": int(os.getenv("AGENT_DEEPTHINKING_NUM_PREDICT", "384")),
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
        response = self._clean_response(response, zh=zh)
        if not self.is_playable_spoken_response(response, zh=zh):
            logger.warning(
                "deepthinking_agent_invalid_spoken_response sid=%s response=%r",
                request.sid,
                response,
            )
            return self.invalid_spoken_response_fallback(zh=zh)
        return response

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
