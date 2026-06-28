from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..clients.ollama_client import OllamaClient
from ..schema import AgentResult, AgentRunRequest

if TYPE_CHECKING:
    from ..capabilities.catalog import CapabilityCatalog
    from ..task_graph.planner import TaskGraphPlanner


@dataclass(slots=True)
class AgentServices:
    ollama: OllamaClient | None = None
    response_reviewer: OllamaClient | None = None
    use_llm: bool = True
    max_speak_chars: int = 120
    expressive_body_cues: str = "sim_only"
    task_graph_planner: "TaskGraphPlanner | None" = None
    capability_catalog: "CapabilityCatalog | None" = None
    capability_match_limit: int = 8


logger = logging.getLogger("chromie.agent.base")


class BaseAgent(ABC):
    name: str = "base_agent"

    def __init__(self, services: AgentServices) -> None:
        self.services = services

    def can_handle(self, request: AgentRunRequest) -> bool:
        return self.name in request.route_decision.agents

    @abstractmethod
    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        """Mutate and return the cumulative AgentResult."""

    def language(self, request: AgentRunRequest) -> str:
        return request.language or request.route_decision.language or "en-US"

    def is_zh(self, request: AgentRunRequest) -> bool:
        return self.language(request).startswith("zh")

    def trace(self, result: AgentResult, message: str) -> None:
        result.handled_by.append(self.name)
        result.trace.append(f"{self.name}: {message}")

    def get_context(self, request: AgentRunRequest, key: str, default: Any = None) -> Any:
        return request.context.get(key, default)

    def mind_context(self, request: AgentRunRequest) -> dict[str, Any]:
        context = request.context or {}
        mind = context.get("mind")
        return mind if isinstance(mind, dict) else {}

    def format_mind_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        mind = self.mind_context(request)
        if not mind:
            return "无" if zh else "None"
        summary = str(mind.get("prompt_summary") or "").strip()
        if summary:
            return summary[:1600].rstrip() + ("..." if len(summary) > 1600 else "")
        compact = json.dumps(mind, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(compact) > 1600:
            compact = compact[:1600].rstrip() + "..."
        return compact

    async def review_spoken_response(
        self,
        request: AgentRunRequest,
        *,
        prompt: str,
        system: str,
        response: str,
        zh: bool,
        options: dict[str, Any],
    ) -> str:
        reviewer = self.services.response_reviewer
        if reviewer is None:
            return response
        response = " ".join((response or "").split())
        if not response:
            return response

        if zh:
            review_system = (
                "你是 Chromie 的语义回答质检器。只判断含义，不使用关键词规则。"
                "如果候选回答自然、直接、符合上下文，并且像 Chromie 机器人本人在说话，就接受。"
                "如果候选回答为空、只有一个不完整词、明显被截断，或不能作为语音完整播放，请改写。"
                "如果候选回答只是空泛承诺、没有真正完成用户请求、忽略了已给出的上下文、"
                "把 Chromie 说成后端模型，或用模型模板拒答，请改写成一条可播放的最终回答。"
                "如果用户请求笑话、故事、歌曲、诗或继续刚才的创作请求，候选回答必须给出实际内容；"
                "只说“我可以讲笑话/我会讲/当然可以”必须改写成实际笑话或创作内容。"
                "如果候选回答主要是在复述、转述或引用用户刚才的话，而不是直接回答，"
                "也要改写；只有确认、澄清或用户明确要求复述时才可以重复用户的话。"
                "只输出 JSON。"
            )
            review_prompt = self._response_review_prompt(
                request,
                agent_prompt=prompt,
                agent_system=system,
                response=response,
                zh=True,
            )
        else:
            review_system = (
                "You are Chromie's semantic spoken-response reviewer. Judge meaning, not keyword rules. "
                "Accept the candidate when it naturally answers the user, asks a necessary clarification, "
                "uses the supplied context, and speaks as Chromie the robot herself. "
                "Revise the candidate when it is empty, only one incomplete word, visibly truncated, "
                "or too fragmentary to play as speech. "
                "Revise the candidate when it is an empty promise, fails to actually perform a harmless requested "
                "creative response, ignores available context, describes Chromie as a backend/model/provider, "
                "uses a model-style refusal where Chromie should answer normally, or mainly repeats, quotes, "
                "or paraphrases the user's current words instead of directly answering. "
                "If the user asks for a joke, story, song, poem, or follows up after Chromie promised one, "
                "the candidate must contain the actual creative content. A candidate that only says "
                "'I can tell you a joke', 'I can do that', 'Sure', or 'I will' is incomplete and must be revised. "
                "Repeating the user's words is acceptable only when confirmation, clarification, or an explicit read-back is needed. "
                "Return JSON only."
            )
            review_prompt = self._response_review_prompt(
                request,
                agent_prompt=prompt,
                agent_system=system,
                response=response,
                zh=False,
            )

        try:
            raw = await reviewer.generate(
                review_prompt,
                system=review_system,
                options={
                    "temperature": 0,
                    "top_p": options.get("top_p", 0.9),
                    "num_predict": 160,
                },
                response_format="json",
            )
        except Exception as exc:
            logger.warning(
                "response_review_failed sid=%s error_type=%s error=%s",
                request.sid,
                type(exc).__name__,
                exc,
            )
            return response

        if not isinstance(raw, dict):
            logger.warning("response_review_invalid sid=%s type=%s", request.sid, type(raw).__name__)
            return response

        decision = str(raw.get("decision") or raw.get("status") or "").strip().lower()
        revised = str(
            raw.get("spoken_response")
            or raw.get("revised_response")
            or raw.get("response")
            or ""
        ).strip()
        if decision in {"revise", "rewrite", "reject"} and revised:
            logger.info(
                "response_review_revised sid=%s reason=%r",
                request.sid,
                str(raw.get("reason") or "")[:200],
            )
            return revised
        return response

    def _response_review_prompt(
        self,
        request: AgentRunRequest,
        *,
        agent_prompt: str,
        agent_system: str,
        response: str,
        zh: bool,
    ) -> str:
        del agent_prompt, agent_system
        task_context = self._bounded_json(self._task_context_from_request(request), 1200, zh=zh)
        history = self._bounded_json(self._history_from_request(request), 1400, zh=zh)
        if zh:
            return (
                f"当前用户输入：{request.text}\n"
                f"最近对话：{history}\n"
                f"任务上下文：{task_context}\n"
                f"候选回答：{response}\n\n"
                "请判断候选回答是否可直接播放。"
                "如果用户当前或最近要求笑话、故事、歌曲或诗，回答必须包含实际创作内容。"
                "示例：用户要求讲笑话，候选回答“我可以讲一个笑话。” => revise，改写为一个简短原创笑话。"
                "正常情况下不要复述用户刚才的话；只有确认、澄清或明确要求复述时才可以。"
                "输出 JSON：{\"decision\":\"accept|revise\",\"reason\":\"简短原因\","
                "\"spoken_response\":\"接受时可为空；修改时给出最终可播放回答\"}"
            )
        return (
            f"Current user input: {request.text}\n"
            f"Recent conversation: {history}\n"
            f"Task context: {task_context}\n"
            f"Candidate spoken response: {response}\n\n"
            "Decide whether the candidate can be spoken now. "
            "A one-word fragment such as only 'I' is not speakable and must be revised. "
            "If the current user input or recent conversation asks for a joke, story, song, poem, or other creative content, "
            "the candidate must include the actual content. Example: user asks for a joke and candidate says "
            "'I can tell you a joke.' => revise with a brief original joke. "
            "If Chromie already promised the content and the user says 'tell me' or 'I know you can', the candidate must deliver it now. "
            "Normally Chromie should not repeat, quote, or paraphrase the user's current words; allow that only for confirmation, clarification, or an explicit read-back request. "
            "Return JSON: {\"decision\":\"accept|revise\",\"reason\":\"short reason\","
            "\"spoken_response\":\"empty when accepted; final corrected spoken answer when revised\"}."
        )

    def is_playable_spoken_response(self, response: str, *, zh: bool) -> bool:
        text = " ".join((response or "").strip().split())
        if len(text) < 2:
            return False
        if not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in text):
            return False
        return True

    def invalid_spoken_response_fallback(self, *, zh: bool) -> str:
        if zh:
            return "我刚才组织回答时卡住了，请你再说一次。"
        return "I got stuck forming that answer. Please say it again."

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

    def _history_from_request(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        if request.history:
            return [turn for turn in request.history if isinstance(turn, dict)][-6:]
        context = request.context or {}
        history = context.get("history")
        if isinstance(history, list):
            return [turn for turn in history if isinstance(turn, dict)][-6:]
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            history = conversation.get("history")
            if isinstance(history, list):
                return [turn for turn in history if isinstance(turn, dict)][-6:]
        return []

    def _bounded_json(self, value: Any, max_chars: int, *, zh: bool) -> str:
        if value in (None, [], {}):
            return "无" if zh else "None"
        return self._bounded_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            max_chars,
        )

    @staticmethod
    def _bounded_text(value: str, max_chars: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > max_chars:
            return text[:max_chars].rstrip() + "..."
        return text
