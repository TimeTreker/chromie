from __future__ import annotations

import logging
from typing import Any

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


_EXPRESSIVE_ATTENTION_ARGS = {
    "style": "neutral",
    "duration_s": 2.4,
    "hold_fraction": 0.35,
}
_EXPRESSIVE_CUE_CAPABILITY_IDS = (
    "soridormi.express_attention",
)
_DEEP_THOUGHT_CAPABILITY_RECOVERY_MIN_SCORE = 0.30
_DEEP_THOUGHT_CAPABILITY_RECOVERY_MIN_CONFIDENCE = 0.72


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
        self._recover_deep_thought_capability_route(request, search)
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
        if request.route_decision.route == "chat":
            request.route_decision.agents = ["conversation_agent", "speaker_agent"]
            return
        if request.route_decision.route == "clarify":
            request.route_decision.agents = ["conversation_agent", "speaker_agent"]
            return
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
        if request.route_decision.route == "tool":
            request.route_decision.agents = list(
                dict.fromkeys([*request.route_decision.agents, "tool_agent", "speaker_agent"])
            )
            return
        if request.route_decision.route == "memory":
            request.route_decision.agents = list(
                dict.fromkeys([*request.route_decision.agents, "memory_agent", "speaker_agent"])
            )
            return

    def _recover_deep_thought_capability_route(
        self,
        request: AgentRunRequest,
        search: Any,
    ) -> bool:
        decision = request.route_decision
        if decision.route != "deep_thought":
            return False
        if not self._deep_thought_capability_recovery_allowed(decision):
            return False
        if getattr(search, "suggested_route", "") != "robot_action":
            return False
        if not bool(getattr(search, "matched", False)):
            return False
        candidates = [
            match
            for match in getattr(search, "matches", []) or []
            if getattr(match, "available", True) is not False
            and bool(getattr(match, "interaction_executable", False))
        ]
        top = self._top_scored_capability(candidates)
        if top is None:
            return False
        top_score = self._capability_score(top)
        if top_score < _DEEP_THOUGHT_CAPABILITY_RECOVERY_MIN_SCORE:
            return False
        capability_id = str(getattr(top, "capability_id", "") or "").strip()
        if not capability_id:
            return False

        original_route = decision.route
        original_intent = decision.intent
        decision.route = "robot_action"
        decision.agents = [
            "capability_agent",
            "safety_agent",
            "speaker_agent",
        ]
        decision.intent = f"capability:{capability_id}"
        decision.confidence = max(0.56, min(0.95, top_score))
        decision.source = "catalog"
        reason = (
            "Agent recovered direct robot action from deep_thought route "
            f"using catalog v{getattr(search, 'catalog_version', 0)} "
            f"score={top_score:.2f}"
        )
        decision.reason = f"{decision.reason}; {reason}" if decision.reason else reason
        decision.metadata = {
            **(decision.metadata or {}),
            "recovered_from_route": original_route,
            "recovered_from_intent": original_intent,
        }
        request.context["route_recovered_from_deep_thought"] = {
            "capability_id": capability_id,
            "score": top_score,
            "catalog_version": getattr(search, "catalog_version", 0),
        }
        return True

    def _deep_thought_capability_recovery_allowed(self, decision: Any) -> bool:
        if decision.confidence < _DEEP_THOUGHT_CAPABILITY_RECOVERY_MIN_CONFIDENCE:
            return False
        intent = str(decision.intent or "").casefold()
        reason = str(decision.reason or "").casefold()
        blocked_intent_terms = (
            "low_confidence",
            "planning",
            "debug",
            "design",
            "strategy",
            "architecture",
            "implementation",
        )
        if any(term in intent for term in blocked_intent_terms):
            return False
        blocked_reason_terms = (
            "explicit planning",
            "make a plan",
            "user asked for a plan",
            "uncertain",
            "low confidence",
        )
        return not any(term in reason for term in blocked_reason_terms)

    def _top_scored_capability(self, candidates: list[Any]) -> Any | None:
        top: Any | None = None
        top_score = 0.0
        for candidate in candidates:
            score = self._capability_score(candidate)
            if top is None or score > top_score:
                top = candidate
                top_score = score
        return top

    @staticmethod
    def _capability_score(candidate: Any) -> float:
        score = getattr(candidate, "score", 0.0)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return 0.0
        return float(score)

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
