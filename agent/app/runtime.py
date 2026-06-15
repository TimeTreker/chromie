from __future__ import annotations

import logging
from pydantic import ValidationError

from .agents import (
    AgentServices,
    BaseAgent,
    CapabilityAgent,
    ConversationAgent,
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
    from chromie_contracts.interaction import InteractionResponse
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import InteractionResponse

logger = logging.getLogger("chromie.agent.runtime")


class _AgentPipeline:
    """Shared specialized-agent pipeline for legacy and native accumulators."""

    def __init__(self, services: AgentServices) -> None:
        self.services = services
        agents: list[BaseAgent] = [
            CapabilityAgent(services),
            ConversationAgent(services),
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
            result.add_speak_immediate(decision.speak_first, style="brief", priority=decision.priority)
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
        request.context["capability_catalog_version"] = search.catalog_version
        request.context["capability_candidates"] = list(
            request.route_decision.candidate_capabilities
        )
        if not search.matched:
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
