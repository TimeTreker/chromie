from __future__ import annotations

import logging
from pydantic import ValidationError

from .agents import (
    AgentServices,
    BaseAgent,
    CapabilityAgent,
    ConversationAgent,
    DeepThinkingAgent,
    MemoryAgent,
    MotionPlannerAgent,
    RobotPoseControllerAgent,
    SafetyAgent,
    SpeakerAgent,
    ToolAgent,
    VisionAgent,
)
from .dispatcher import selected_agents
from .interaction import InteractionDraft, NativeInteractionOutputError
from .schema import AgentResult, AgentRunRequest

try:
    from chromie_contracts.interaction import InteractionResponse, SkillRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest

logger = logging.getLogger("chromie.agent.runtime")


_SORIDORMI_TASK_PLANNING_TOOLS = {
    "soridormi.task.get_capabilities",
    "soridormi.task.preview",
    "soridormi.task.submit",
}
_EXPRESSIVE_ATTENTION_ARGS = {
    "style": "neutral",
    "duration_s": 2.4,
    "hold_fraction": 0.35,
}
_EXPRESSIVE_CUE_CAPABILITY_IDS = (
    "soridormi.express_attention",
)
_CHAT_TO_PHYSICAL_PROMOTION_MIN_SCORE = 0.45


def _catalog_item(
    request: AgentRunRequest,
    capability_id: str,
) -> dict | None:
    candidates = request.route_decision.candidate_capabilities
    if not candidates:
        candidates = request.context.get("capability_candidates") or []
    if not isinstance(candidates, list):
        return None
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if item.get("capability_id") != capability_id:
            continue
        if item.get("available") is False:
            return None
        if item.get("interaction_executable") is not True:
            return None
        return item
    return None


def _has_interaction_executable_match(candidates: list[dict]) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("interaction_executable") is True
        and item.get("available") is not False
        for item in candidates
    )


def _has_soridormi_task_planning_match(candidates: list[dict]) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("capability_id") in _SORIDORMI_TASK_PLANNING_TOOLS
        and item.get("available") is not False
        for item in candidates
    )


def _has_capability_intent(intent: str) -> bool:
    return (intent or "").strip().startswith("capability:")


class _AgentPipeline:
    """Shared specialized-agent pipeline for legacy and native accumulators."""

    def __init__(self, services: AgentServices) -> None:
        self.services = services
        agents: list[BaseAgent] = [
            CapabilityAgent(services),
            ConversationAgent(services),
            DeepThinkingAgent(services),
            RobotPoseControllerAgent(services),
            MotionPlannerAgent(services),
            SafetyAgent(services),
            ToolAgent(services),
            MemoryAgent(services),
            VisionAgent(services),
            SpeakerAgent(services),
        ]
        self.agents: dict[str, BaseAgent] = {agent.name: agent for agent in agents}

    def available_agents(self) -> list[str]:
        return sorted(self.agents)

    async def _run_pipeline(
        self,
        request: AgentRunRequest,
        result: AgentResult | InteractionDraft,
    ) -> AgentResult | InteractionDraft:
        decision = request.route_decision

        if decision.route == "ignore":
            result.status = "ignored"
            result.reason = decision.reason or "route_ignore"
            result.trace.append("runtime: ignored by route")
            return result

        if decision.route == "interrupt":
            result.status = "ok"
            result.reason = decision.reason or "route_interrupt"
            result.add_action("system", "session.interrupt", params={}, blocking=True, timeout_ms=300)
            result.trace.append("runtime: interrupt action emitted")
            return result

        if decision.speak_first and decision.should_speak:
            result.add_speak_immediate(
                decision.speak_first,
                style="brief",
                priority=decision.priority,
            )
            result.trace.append("runtime: added router speak_first")

        for agent_name in selected_agents(request):
            agent = self.agents.get(agent_name)
            if agent is None:
                logger.warning("unknown agent requested: %s", agent_name)
                result.trace.append(f"runtime: unknown agent {agent_name}")
                continue
            # Specialized agents intentionally accept the shared helper surface
            # implemented by both AgentResult and InteractionDraft.
            result = await agent.run(request, result)  # type: ignore[arg-type,assignment]

        return result


class AgentRuntime(_AgentPipeline):
    """Established AgentResult runtime retained for `/run` compatibility."""

    async def run(self, request: AgentRunRequest) -> AgentResult:
        result = await self._run_pipeline(request, AgentResult())
        if not isinstance(result, AgentResult):  # pragma: no cover - defensive
            raise TypeError("legacy Agent runtime returned a non-AgentResult value")
        return result


class InteractionRuntime(_AgentPipeline):
    """Native InteractionResponse runtime used by `/interaction`."""

    async def run(self, request: AgentRunRequest) -> InteractionResponse:
        await self._prepare_capability_route(request)
        result = await self._run_pipeline(request, InteractionDraft())
        if not isinstance(result, InteractionDraft):  # pragma: no cover - defensive
            raise TypeError("native interaction runtime returned a non-InteractionDraft value")
        self._add_expressive_body_cue(request, result)
        try:
            return result.to_response()
        except ValidationError as exc:
            raise NativeInteractionOutputError(
                f"native InteractionResponse validation failed: {exc}"
            ) from exc

    async def _prepare_capability_route(self, request: AgentRunRequest) -> None:
        catalog = self.services.capability_catalog
        if catalog is None or request.route_decision.route in {"interrupt", "ignore"}:
            return
        search = await catalog.search(
            request.text,
            language=request.language or request.route_decision.language,
            limit=self.services.capability_match_limit,
            prefer_interaction_executable=True,
        )
        request.route_decision.candidate_capabilities = [
            match.model_dump(mode="json") for match in search.matches
        ]
        await self._ensure_expressive_body_cue_candidates(request)
        request.context["capability_catalog_version"] = search.catalog_version
        request.context["capability_candidates"] = list(
            request.route_decision.candidate_capabilities
        )
        if request.route_decision.route == "deep_thought":
            request.route_decision.agents = ["deepthinking_agent", "speaker_agent"]
            return
        if request.route_decision.actions:
            if request.route_decision.route == "robot_action":
                request.route_decision.agents = list(
                    dict.fromkeys(
                        [
                            *request.route_decision.agents,
                            "capability_agent",
                            "safety_agent",
                            "speaker_agent",
                        ]
                    )
                )
            return
        if (
            request.route_decision.route == "chat"
            and request.route_decision.confidence >= 0.55
        ):
            request.route_decision.agents = ["conversation_agent", "speaker_agent"]
            return
        if (
            request.route_decision.route == "chat"
            and search.suggested_route == "robot_action"
            and not self._strong_chat_capability_promotion(search)
        ):
            request.route_decision.agents = ["conversation_agent", "speaker_agent"]
            request.context["capability_promotion_blocked"] = {
                "suggested_route": search.suggested_route,
                "top_score": search.matches[0].score if search.matches else 0.0,
                "reason": "weak_chat_to_physical_match",
            }
            return
        embodied_task_candidate = (
            self.services.task_graph_planner is not None
            and not request.route_decision.actions
            and not _has_interaction_executable_match(
                request.route_decision.candidate_capabilities
            )
            and _has_soridormi_task_planning_match(
                request.route_decision.candidate_capabilities
            )
        )
        if not search.matched and not embodied_task_candidate:
            return
        if (
            embodied_task_candidate
            and (search.suggested_route == "robot_action" or not search.matched)
        ):
            request.route_decision.route = "tool"
            request.route_decision.agents = ["tool_agent", "speaker_agent"]
            request.route_decision.intent = "soridormi_task_planning"
            request.route_decision.confidence = max(
                request.route_decision.confidence,
                search.matches[0].score if search.matches else 0.0,
            )
            request.route_decision.source = "catalog"
            request.route_decision.reason = (
                "Matched Soridormi task-agent planning capability"
            )
            return
        if search.suggested_route == "chat":
            request.route_decision.route = "chat"
            request.route_decision.agents = ["conversation_agent", "speaker_agent"]
            request.route_decision.intent = "general_conversation"
            request.route_decision.confidence = max(
                request.route_decision.confidence,
                search.matches[0].score if search.matches else 0.0,
            )
            request.route_decision.source = "catalog"
            request.route_decision.reason = "Matched shared capability catalog"
            return
        if (
            request.route_decision.route == "robot_action"
            and search.suggested_route == "robot_action"
            and request.route_decision.source == "llm"
            and not request.route_decision.actions
            and not _has_capability_intent(request.route_decision.intent)
        ):
            request.route_decision.agents = list(
                dict.fromkeys([*request.route_decision.agents, *search.suggested_agents])
            )
            request.route_decision.confidence = max(
                request.route_decision.confidence,
                search.matches[0].score if search.matches else 0.0,
            )
            return
        request.route_decision.route = search.suggested_route
        request.route_decision.agents = list(search.suggested_agents)
        request.route_decision.intent = (
            f"capability:{search.matches[0].capability_id}"
            if search.matches
            else "capability_match"
        )
        request.route_decision.confidence = max(
            request.route_decision.confidence,
            search.matches[0].score if search.matches else 0.0,
        )
        request.route_decision.source = "catalog"
        request.route_decision.reason = "Matched shared capability catalog"

    @staticmethod
    def _strong_chat_capability_promotion(search: Any) -> bool:
        if not getattr(search, "matched", False):
            return False
        matches = list(getattr(search, "matches", []) or [])
        if not matches:
            return False
        top = matches[0]
        score = getattr(top, "score", 0.0)
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            return False
        if float(score) < _CHAT_TO_PHYSICAL_PROMOTION_MIN_SCORE:
            return False
        return any(
            getattr(match, "interaction_executable", False) is True
            and getattr(match, "route", "") == getattr(search, "suggested_route", "")
            and (
                getattr(match, "safety_class", "") in {"physical_motion", "safety_critical"}
                or "physical_motion" in list(getattr(match, "effects", []) or [])
            )
            for match in matches[:3]
        )

    async def _ensure_expressive_body_cue_candidates(
        self,
        request: AgentRunRequest,
    ) -> None:
        if self.services.expressive_body_cues == "off":
            return
        catalog = self.services.capability_catalog
        if catalog is None:
            return
        candidates = request.route_decision.candidate_capabilities
        existing = {
            item.get("capability_id")
            for item in candidates
            if isinstance(item, dict)
        }
        missing = [
            capability_id
            for capability_id in _EXPRESSIVE_CUE_CAPABILITY_IDS
            if capability_id not in existing
        ]
        if not missing:
            return
        try:
            cue_search = await catalog.search(
                "express attention nod yes",
                language=request.language or request.route_decision.language,
                limit=max(self.services.capability_match_limit, 16),
                min_score=0.0,
                prefer_interaction_executable=True,
            )
        except Exception as exc:  # pragma: no cover - defensive service boundary
            logger.warning("expressive cue catalog lookup failed: %s", exc)
            return
        for match in cue_search.matches:
            payload = match.model_dump(mode="json")
            capability_id = payload.get("capability_id")
            if capability_id in missing and capability_id not in existing:
                candidates.append(payload)
                existing.add(capability_id)

    def _add_expressive_body_cue(
        self,
        request: AgentRunRequest,
        result: InteractionDraft,
    ) -> None:
        if self.services.expressive_body_cues == "off":
            return
        if request.route_decision.route != "chat":
            return
        if result.status != "ok":
            return
        if getattr(result, "_skills", []):
            return

        speech_text = " ".join(item.text for item in result.speak_immediate)
        if not speech_text.strip():
            return

        match = self._expressive_cue_catalog_item(
            request,
            "soridormi.express_attention",
        )
        if match is None:
            return
        self._add_expressive_skill(
            request,
            result,
            match,
            skill_id="soridormi.express_attention",
            args=dict(_EXPRESSIVE_ATTENTION_ARGS),
            reason="chat_attention",
        )

    def _expressive_cue_catalog_item(
        self,
        request: AgentRunRequest,
        capability_id: str,
    ) -> dict | None:
        match = _catalog_item(request, capability_id)
        if match is None:
            return None
        cue_mode = self.services.expressive_body_cues
        capability_mode = str((match.get("metadata") or {}).get("mode") or "")
        if cue_mode == "sim_only" and capability_mode != "sim":
            return None
        return match

    def _add_expressive_skill(
        self,
        request: AgentRunRequest,
        result: InteractionDraft,
        match: dict,
        *,
        skill_id: str,
        args: dict,
        reason: str,
    ) -> None:
        result.add_skill(
            SkillRequest(
                skill_id=skill_id,
                args=args,
                timing="parallel",
                requires_confirmation=bool(match.get("requires_confirmation")),
                metadata={
                    "source": "expressive_body_cue",
                    "reason": reason,
                    "catalog_version": request.context.get("capability_catalog_version"),
                    "catalog_score": match.get("score"),
                },
            )
        )
        result.metadata["expressive_body_cue"] = skill_id
        result.trace.append(f"runtime: added expressive {skill_id} cue")
