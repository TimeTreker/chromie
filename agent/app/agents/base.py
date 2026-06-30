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
    response_review_mode: str = "always"
    use_llm: bool = True
    max_speak_chars: int = 120
    expressive_body_cues: str = "off"
    require_capability_plan_review: bool = False
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
        mode = (self.services.response_review_mode or "always").strip().lower()
        if mode in {"0", "false", "no", "off", "disabled"}:
            return response
        if mode == "auto" and not self._needs_spoken_response_review(
            request,
            response=response,
            zh=zh,
        ):
            logger.info(
                "response_review_skipped sid=%s mode=auto route=%s intent=%s",
                request.sid,
                request.route_decision.route,
                request.route_decision.intent,
            )
            return response

        review_system = self._spoken_review_system()
        review_prompt = self._response_review_prompt(
            request,
            agent_prompt=prompt,
            agent_system=system,
            response=response,
            target_language=self.language(request),
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

    def _needs_spoken_response_review(
        self,
        request: AgentRunRequest,
        *,
        response: str,
        zh: bool,
    ) -> bool:
        if not self.is_playable_spoken_response(response, zh=zh):
            return True
        route = request.route_decision.route
        if route not in {"chat", "clarify"}:
            return True
        if request.route_decision.actions:
            return True
        if request.route_decision.candidate_capabilities:
            return True
        context = request.context or {}
        if context.get("capability_candidates"):
            return True
        if self._task_context_from_request(request):
            return True
        if self._history_from_request(request):
            return True

        response_key = self._review_signal_text(response)
        request_key = self._review_signal_text(request.text)
        if len(response_key) < 12:
            return True
        if request_key and request_key in response_key:
            return True

        reviewer_signal_needles = (
            "as an ai",
            "large language model",
            "language model",
            "trained by",
            "i do not have personal",
            "i don't have personal",
            "i cannot",
            "i can't",
            "i do not have the ability",
            "i don't have the ability",
            "i have no ability",
            "i can tell you",
            "i can do that",
            "i am ready",
            "i will now",
            "i'll now",
            "i am going to",
            "i'm going to",
            "i will execute",
            "i will perform",
            "i will move",
            "i will walk",
            "let me move",
            "let me walk",
            "我不能",
            "我无法",
            "我没有",
            "没有能力",
            "我可以讲",
            "我可以做",
            "我准备好了",
            "这就",
            "马上",
            "立即",
            "开始执行",
            "执行这个动作",
            "往前走",
            "向前走",
        )
        if any(needle in response_key for needle in reviewer_signal_needles):
            return True

        creative_request_needles = (
            "joke",
            "story",
            "poem",
            "song",
            "sing",
            "tell me",
            "讲笑话",
            "笑话",
            "故事",
            "诗",
            "唱歌",
        )
        empty_promise_needles = (
            "i can",
            "sure",
            "of course",
            "当然",
            "可以",
            "我会",
        )
        if any(needle in request_key for needle in creative_request_needles) and any(
            needle in response_key for needle in empty_promise_needles
        ):
            return True

        return False

    @staticmethod
    def _review_signal_text(value: str) -> str:
        return " ".join((value or "").casefold().split())

    def _response_review_prompt(
        self,
        request: AgentRunRequest,
        *,
        agent_prompt: str,
        agent_system: str,
        response: str,
        target_language: str,
    ) -> str:
        del agent_system
        task_context = self._bounded_json(self._task_context_from_request(request), 1200)
        history = self._bounded_json(self._history_from_request(request), 1400)
        capabilities = self._bounded_json(
            {
                "candidate_capabilities": request.route_decision.candidate_capabilities,
                "capability_candidates": request.context.get("capability_candidates"),
            },
            1600,
        )
        route_context = self._bounded_json(
            {
                "route": request.route_decision.route,
                "intent": request.route_decision.intent,
                "source": request.route_decision.source,
                "agents": request.route_decision.agents,
                "actions": request.route_decision.actions,
            },
            1000,
        )
        original_prompt = agent_prompt[:1800]
        return (
            f"Target spoken language: {target_language}\n"
            "Use an explicit user-requested output language when the current input or context asks for one; otherwise use the target spoken language.\n"
            f"Current user input: {request.text}\n"
            f"Route context: {route_context}\n"
            f"Recent conversation: {history}\n"
            f"Task context: {task_context}\n"
            f"Capability context: {capabilities}\n"
            f"Original agent prompt excerpt: {original_prompt}\n"
            f"Candidate spoken response: {response}\n\n"
            "Decide whether the candidate can be spoken now. "
            "A one-word fragment such as only 'I' is not speakable and must be revised. "
            "If the current user input or recent conversation asks for a joke, story, song, poem, or other creative content, "
            "including capability-style wording such as whether Chromie can, could, or would do it, the candidate must include the actual content. Example: user asks for a joke and candidate says "
            "'I can tell you a joke.' => revise with a brief original joke. "
            "If Chromie already promised the content and the user says they are waiting, says 'go ahead', 'continue', 'tell me', or 'I know you can', the candidate must deliver it now. "
            "If the candidate says Chromie lacks a body/tool ability that appears available in Capability context or the original prompt excerpt, revise it to acknowledge the available ability instead of falsely refusing. "
            "If Route context is chat or clarify and the candidate promises, confirms, or implies that Chromie will now execute a physical body action, movement, or tool side effect, revise it to a safe clarification that the action must be routed through the robot action planner before execution. "
            "Do not let a speech-only response claim that a movement or tool action is being performed when no robot_action route or skill request is present. "
            "Normally Chromie should not repeat, quote, or paraphrase the user's current words; allow that only for confirmation, clarification, or an explicit read-back request. "
            "Return JSON: {\"decision\":\"accept|revise\",\"reason\":\"short reason\","
            "\"spoken_response\":\"empty when accepted; final corrected spoken answer when revised\"}."
        )

    @staticmethod
    def _spoken_review_system() -> str:
        return (
            "You are Chromie's semantic spoken-response reviewer. Judge meaning, not keyword rules. "
            "This single reviewer prompt is multilingual; understand Chinese and English input, but return JSON only. "
            "Preserve the generalization-first principle: judge normal response quality from semantics, context, and capability boundaries, not from phrase-rule tables. "
            "Accept the candidate when it naturally answers the user, asks a necessary clarification, "
            "uses the supplied context, and speaks as Chromie the robot herself. "
            "Revise the candidate when it is empty, only one incomplete word, visibly truncated, "
            "or too fragmentary to play as speech. "
            "Revise the candidate when it is an empty promise, fails to actually perform a harmless requested "
            "creative response, ignores available context, describes Chromie as a backend/model/provider, "
            "uses a model-style refusal where Chromie should answer normally, or mainly repeats, quotes, "
            "or paraphrases the user's current words instead of directly answering. "
            "Revise the candidate when it falsely says Chromie cannot perform a body/tool ability that the supplied capability context shows as available. "
            "Revise the candidate when it claims Chromie will now execute movement, body action, or a tool side effect while Route context is chat or clarify and no executable action route is present. "
            "In that case, ask for safe action routing or clarification instead of promising execution. "
            "If the user asks for a joke, story, song, poem, or follows up after Chromie promised one, even when the request is phrased as whether Chromie can, could, would, 能不能, 可不可以, or 会不会 do it, "
            "the candidate must contain the actual creative content. A candidate that only says "
            "'I can tell you a joke', 'I can do that', 'Sure', 'I am ready', 'I will', '我可以讲笑话', '当然可以', or '我准备好了' is incomplete and must be revised. "
            "If the context shows Chromie already promised creative content and the user says they are waiting, asks to continue, says go ahead, or asks again, the candidate must deliver the content now. "
            "Repeating the user's words is acceptable only when confirmation, clarification, or an explicit read-back is needed. "
            "When revising, write spoken_response in the requested output language from the prompt. "
            "Return JSON only."
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

    def _bounded_json(self, value: Any, max_chars: int) -> str:
        if value in (None, [], {}):
            return "None"
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
