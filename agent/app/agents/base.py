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
    social_attention_mode: str = ""
    social_attention_ollama: OllamaClient | None = None
    social_attention_num_ctx: int = 4096
    social_attention_num_predict: int = 160
    social_attention_max_behaviors: int = 2
    social_attention_wait_after_response_ms: int = 0
    social_attention_capability_ids: tuple[str, ...] = ()
    social_attention_fallback_target: str = "none"
    social_attention_fallback_direction: str | None = None
    social_attention_fallback_yaw_rad: float | None = None
    social_attention_fallback_confidence: float = 0.0
    require_capability_plan_review: bool = False
    legacy_capability_fallback_enabled: bool = False
    task_graph_planner: "TaskGraphPlanner | None" = None
    capability_catalog: "CapabilityCatalog | None" = None
    capability_match_limit: int = 8
    weather_client: Any | None = None
    tool_result_interpreter: Any | None = None

    def effective_social_attention_mode(self) -> str:
        raw = (self.social_attention_mode or self.expressive_body_cues or "off").strip().lower()
        if raw not in {"off", "report_only", "sim_only", "on"}:
            return "off"
        return raw


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

    def self_model_context(self, request: AgentRunRequest) -> dict[str, Any]:
        mind = self.mind_context(request)
        self_model = mind.get("self_model") if isinstance(mind, dict) else None
        if isinstance(self_model, dict):
            return self_model
        identity = mind.get("identity") if isinstance(mind, dict) else None
        if not isinstance(identity, dict):
            return {}
        entity_id = str(identity.get("entity_id") or identity.get("name") or "chromie")
        name = str(identity.get("name") or "Chromie")
        return {
            "speaker_entity": {
                "entity_id": entity_id,
                "name": name,
                "gender": identity.get("gender"),
                "pronouns": identity.get("pronouns"),
            },
            "social_presentation": {
                "self_reference": name,
                "presence": "natural, warm, person-like conversational presence",
                "foreground": ["name", "personality", "current relationship and context"],
                "background": ["system category", "embodiment category", "age label", "internal architecture"],
            },
            "perceiving_entity_id": entity_id,
            "acting_entity_id": entity_id,
            "body_owner_entity_id": entity_id,
            "internal_components": [],
            "capability_evidence_source": "runtime capability catalog and current provider state",
        }

    def format_self_model_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        self_model = self.self_model_context(request)
        if not self_model:
            return "无" if zh else "None"
        compact = json.dumps(
            self_model,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(compact) > 1800:
            compact = compact[:1800].rstrip() + "..."
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
        return self._has_effectful_robot_context(request)

    def _has_effectful_robot_context(self, request: AgentRunRequest) -> bool:
        decision = request.route_decision
        if decision.route == "robot_action":
            return True
        if any(self._is_effectful_action(item) for item in decision.actions):
            return True
        if any(
            self._is_effectful_capability(item)
            for item in decision.candidate_capabilities
        ):
            return True

        context = request.context or {}
        candidates = context.get("capability_candidates")
        if isinstance(candidates, list) and any(
            self._is_effectful_capability(item) for item in candidates
        ):
            return True

        metadata = decision.metadata or {}
        for key in ("task_list", "task_proposals", "agent_task_proposals"):
            items = metadata.get(key)
            if isinstance(items, list) and any(
                self._is_effectful_task_item(item) for item in items
            ):
                return True
        return False

    @staticmethod
    def _is_speech_skill_id(value: Any) -> bool:
        return str(value or "").strip() == "chromie.speak"

    def _is_effectful_action(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        skill_id = item.get("skill_id") or item.get("capability_id")
        if self._is_speech_skill_id(skill_id):
            return False
        return bool(skill_id or item.get("type") or item.get("target"))

    def _is_effectful_capability(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        capability_id = item.get("capability_id") or item.get("skill_id")
        if self._is_speech_skill_id(capability_id):
            return False
        effects = item.get("effects")
        if isinstance(effects, list) and any(
            str(effect or "").strip()
            not in {"", "user_interaction", "audio_output"}
            for effect in effects
        ):
            return True
        safety_class = str(item.get("safety_class") or "").strip()
        if safety_class and safety_class not in {"low_risk_action", "speech"}:
            return True
        route = str(item.get("route") or "").strip()
        return route == "robot_action"

    def _is_effectful_task_item(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        skill_id = item.get("skill_id") or item.get("capability_id")
        if self._is_speech_skill_id(skill_id):
            return False
        task_type = str(item.get("task_type") or item.get("type") or "").strip()
        if task_type in {"", "speech.answer", "chromie.speak"}:
            return False
        if task_type in {
            "task.execute_skill",
            "task.execute_robot_action",
            "robot_action",
        }:
            return True
        return str(item.get("route") or "").strip() == "robot_action"

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
        self_model = self._bounded_json(self.self_model_context(request), 1400)
        task_context = self._bounded_json(self._task_context_from_request(request), 1200)
        extracted_context = self._bounded_text(
            self._extracted_context_summary(request),
            1400,
        )
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
            f"Self model: {self_model}\n"
            f"Route context: {route_context}\n"
            f"Extracted conversation context: {extracted_context}\n"
            f"Task context: {task_context}\n"
            f"Capability context: {capabilities}\n"
            f"Original agent prompt excerpt: {original_prompt}\n"
            f"Candidate spoken response: {response}\n\n"
            "Decide whether the candidate can be spoken now. "
            "A one-word fragment such as only 'I' is not speakable and must be revised. "
            "If the current user input or extracted context asks for a joke, story, song, poem, or other creative content, "
            "including capability-style wording such as whether Chromie can, could, or would do it, the candidate must include the actual content rather than only promising readiness or ability. "
            "If Chromie already promised the content according to the extracted context and the user says they are waiting, says 'go ahead', 'continue', 'tell me', or 'I know you can', the candidate must deliver it now. "
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
            "uses the supplied context, and keeps first-person speech consistent with the supplied Self model. "
            "Revise the candidate when it is empty, only one incomplete word, visibly truncated, "
            "or too fragmentary to play as speech. "
            "Revise the candidate when it is an empty promise, fails to actually perform a harmless requested "
            "creative response, ignores available context, assigns first-person speaker or body ownership to an internal component, "
            "uses a component-style refusal where the speaking entity should answer normally, or mainly repeats, quotes, "
            "or paraphrases the user's current words instead of directly answering. "
            "Revise the candidate when it falsely says Chromie cannot perform a body/tool ability that the supplied capability context shows as available. "
            "Revise the candidate when it claims Chromie will now execute movement, body action, or a tool side effect while Route context is chat or clarify and no executable action route is present. "
            "In that case, ask for safe action routing or clarification instead of promising execution. "
            "If the user asks for a joke, story, song, poem, or follows up after Chromie promised one, even when the request is phrased as whether Chromie can, could, would, 能不能, 可不可以, or 会不会 do it, "
            "the candidate must contain the actual creative content. A candidate that only promises readiness, willingness, or ability is incomplete and must be revised. "
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

    def _extracted_context_summary(self, request: AgentRunRequest) -> str:
        lines: list[str] = []
        context = request.context or {}
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            conversation_id = str(conversation.get("conversation_id") or "").strip()
            if conversation_id:
                lines.append(f"conversation_id={conversation_id}")
        task_context = self._task_context_from_request(request)
        if isinstance(task_context, dict):
            for key in ("task_id", "status", "task_type", "goal"):
                value = " ".join(str(task_context.get(key) or "").split())
                if value:
                    lines.append(f"{key}={self._bounded_text(value, 180)}")
            for key in ("important_claims", "pending_questions"):
                values = self._compact_string_list(task_context.get(key), limit=4)
                if values:
                    lines.append(f"{key}={'; '.join(values)}")
        pending = self._pending_tasks_from_request(request)
        if pending:
            summarized: list[str] = []
            for task in pending[-4:]:
                if not isinstance(task, dict):
                    continue
                task_type = " ".join(str(task.get("type") or "task").split())
                status = " ".join(str(task.get("status") or "pending").split())
                summarized.append(f"{task_type}:{status}")
            if summarized:
                lines.append(f"pending_tasks={'; '.join(summarized)}")
        return "\n".join(lines) if lines else "None"

    def _pending_tasks_from_request(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        context = request.context or {}
        pending = context.get("pending_tasks")
        if isinstance(pending, list):
            return [task for task in pending if isinstance(task, dict)]
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            pending = conversation.get("pending_tasks")
            if isinstance(pending, list):
                return [task for task in pending if isinstance(task, dict)]
        return []

    def _compact_string_list(self, value: Any, *, limit: int) -> list[str]:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = [item for item in value if isinstance(item, str)]
        else:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            text = " ".join(item.split())
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(self._bounded_text(text, 160))
            if len(out) >= limit:
                break
        return out

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
