from __future__ import annotations

import asyncio
import contextlib
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
    SafetyAgent,
    SpeakerAgent,
    ToolAgent,
    VisionAgent,
)
from .clients.ollama_client import llm_failure_metadata
from .dispatcher import selected_agents
from .interaction import InteractionDraft, NativeInteractionOutputError
from .social_attention import SocialAttentionContextBuilder, SocialAttentionPlanner
from .schema import AgentResult, AgentRunRequest, RouteDecision

try:
    from chromie_contracts.interaction import InteractionResponse, CapabilityRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import InteractionResponse, CapabilityRequest

logger = logging.getLogger("chromie.agent.runtime")


def _is_missing_ability_clarify(decision: RouteDecision) -> bool:
    return (
        decision.route == "clarify"
        and str(decision.intent or "") == "missing_or_unsupported_ability"
    )


def _safe_missing_ability_text(request: AgentRunRequest) -> str:
    return " ".join((request.route_decision.speak_first or "").strip().split())


def _goal_interpretation_fast_first_already_scheduled(decision: RouteDecision) -> bool:
    metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
    if metadata.get("fast_first_response_scheduled") is True:
        return True
    fast_first = metadata.get("fast_first_response")
    return isinstance(fast_first, dict) and fast_first.get("scheduled") is True


def _is_terminal_goal_interpretation_acknowledgement(decision: RouteDecision) -> bool:
    return (
        decision.route == "chat"
        and str(decision.intent or "").strip() in {"greeting", "gratitude_acknowledgement"}
        and decision.should_speak
        and (bool(decision.speak_first) or _goal_interpretation_fast_first_already_scheduled(decision))
    )




class _AgentPipeline:
    """Shared specialized-agent pipeline for legacy and native accumulators."""

    def __init__(self, services: AgentServices) -> None:
        self.services = services
        agents: list[BaseAgent] = [
            CapabilityAgent(services),
            ConversationAgent(services),
            DeepThinkingAgent(services),
            SafetyAgent(services),
            ToolAgent(services),
            MemoryAgent(services),
            VisionAgent(services),
            SpeakerAgent(services),
        ]
        self.agents: dict[str, BaseAgent] = {agent.name: agent for agent in agents}
        self.social_attention_planner = SocialAttentionPlanner(services)
        self.social_attention_context_builder = SocialAttentionContextBuilder(services)

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

        if _is_missing_ability_clarify(decision):
            result.status = "clarify"
            result.reason = decision.reason or "missing_or_unsupported_ability"
            if decision.should_speak and decision.speak_first:
                result.add_speak_immediate(
                    _safe_missing_ability_text(request),
                    style="brief",
                    priority=decision.priority,
                )
            result.requires_confirmation = False
            result.trace.append("runtime: terminal missing-ability clarify; skipped agent rewrite")
            return result

        if _is_terminal_goal_interpretation_acknowledgement(decision):
            result.status = "ok"
            intent = str(decision.intent or "").strip()
            is_greeting = intent == "greeting"
            result.reason = decision.reason or f"terminal_goal_interpretation_{intent or 'acknowledgement'}"
            if decision.speak_first:
                result.add_speak_immediate(
                    decision.speak_first,
                    style="brief",
                    priority=decision.priority,
                )
                result.trace.append(
                    "runtime: terminal goal interpretation greeting emitted speak_first"
                    if is_greeting
                    else "runtime: terminal goal interpretation acknowledgement emitted speak_first"
                )
            else:
                result.trace.append(
                    "runtime: terminal goal interpretation greeting already spoken by fast-first"
                    if is_greeting
                    else "runtime: terminal goal interpretation acknowledgement already spoken by fast-first"
                )
            result.trace.append(
                "runtime: terminal goal interpretation greeting fast-first; skipped agent rewrite"
                if is_greeting
                else "runtime: terminal goal interpretation acknowledgement; skipped agent rewrite"
            )
            return result

        if decision.speak_first and decision.should_speak:
            result.add_speak_immediate(
                decision.speak_first,
                style="brief",
                priority=decision.priority,
            )
            result.trace.append("runtime: added goal interpretation speak_first")

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
        attention_task = self._start_social_attention_plan(request)
        try:
            result = await self._run_pipeline(request, InteractionDraft())
        except Exception:
            if attention_task is not None and not attention_task.done():
                attention_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await attention_task
            raise
        if not isinstance(result, InteractionDraft):  # pragma: no cover - defensive
            raise TypeError("native interaction runtime returned a non-InteractionDraft value")
        await self._finish_social_attention_plan(request, result, attention_task)
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
        await self.social_attention_context_builder._ensure_candidates(request)
        request.context["capability_catalog_version"] = search.catalog_version
        request.context["capability_candidates"] = list(
            request.route_decision.candidate_capabilities
        )
        if request.route_decision.route == "deep_thought":
            await self._attach_deep_thought_catalog(request)
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
            request.route_decision.agents = (
                ["speaker_agent"]
                if _is_missing_ability_clarify(request.route_decision)
                else ["conversation_agent", "speaker_agent"]
            )
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

    async def _attach_deep_thought_catalog(self, request: AgentRunRequest) -> None:
        catalog = self.services.capability_catalog
        if catalog is None or not hasattr(catalog, "prompt_entries"):
            return
        entries = await catalog.prompt_entries(scope="all")
        payload = [entry.model_dump(mode="json") for entry in entries]
        if not payload:
            return
        request.route_decision.candidate_capabilities = payload
        request.context["capability_candidates"] = list(payload)
        request.context["capability_catalog_scope"] = "all"

    async def prepare_social_attention_context(self, request: Any) -> None:
        """Legacy runtime delegate; current API owns Social Attention directly."""
        await self.social_attention_context_builder.prepare(request)

    def _start_social_attention_plan(
        self,
        request: AgentRunRequest,
    ) -> asyncio.Task | None:
        if self.services.effective_social_attention_mode() == "off":
            return None
        if request.route_decision.route in {"ignore", "interrupt"}:
            return None
        if not request.route_decision.should_speak:
            return None
        if not request.context.get("social_attention_candidates"):
            return None
        if self.services.social_attention_ollama is None:
            return None
        return asyncio.create_task(
            self.social_attention_planner.plan(request),
            name=f"social-attention:{request.sid or 'turn'}",
        )

    async def _finish_social_attention_plan(
        self,
        request: AgentRunRequest,
        result: InteractionDraft,
        task: asyncio.Task | None,
    ) -> None:
        if task is None:
            return

        def record_failure(values: dict[str, Any]) -> None:
            failure = dict(values)
            failure.setdefault("stage", "social_attention")
            failure.setdefault("failure_class", "unclassified_model_failure")
            failure.setdefault("failure_domain", "model_or_runtime")
            failure.setdefault("architecture_attribution", "not_evaluated")
            failure.setdefault("retryable", False)
            result.metadata["social_attention_failure"] = failure
            result.metadata["social_attention_failure_class"] = failure["failure_class"]
            result.metadata["social_attention_failure_domain"] = failure["failure_domain"]
            result.metadata["social_attention_architecture_attribution"] = failure[
                "architecture_attribution"
            ]

        # Give the concurrently-started auxiliary task one event-loop turn first.
        # Compatibility deployments may then opt into a small bounded join budget.
        # A zero budget preserves the non-blocking primary-response behavior.
        if not task.done():
            await asyncio.sleep(0)

        plan = None
        configured_wait_ms = max(
            0, int(self.services.social_attention_wait_after_response_ms)
        )
        if not task.done() and configured_wait_ms > 0:
            try:
                plan = await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=configured_wait_ms / 1000.0,
                )
            except TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                failure = {
                    "stage": "social_attention",
                    "failure_class": "latency_budget_exhausted",
                    "failure_domain": "auxiliary_latency",
                    "architecture_attribution": "not_evaluated",
                    "retryable": True,
                    "configured_wait_after_response_ms": configured_wait_ms,
                    "effective_wait_after_response_ms": configured_wait_ms,
                }
                record_failure(failure)
                result.metadata["social_attention_status"] = "skipped_latency_budget"
                result.trace.append(
                    "runtime: social attention exceeded its configured bounded "
                    "post-response join budget"
                )
                return
            except Exception as exc:  # pragma: no cover - defensive
                failure = {
                    **llm_failure_metadata(exc),
                    "stage": "social_attention",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                }
                record_failure(failure)
                logger.warning(
                    "social_attention_task_failed sid=%s failure_class=%s failure_domain=%s "
                    "architecture_attribution=%s retryable=%s error_type=%s error=%s",
                    request.sid,
                    failure.get("failure_class"),
                    failure.get("failure_domain"),
                    failure.get("architecture_attribution"),
                    str(bool(failure.get("retryable"))).lower(),
                    type(exc).__name__,
                    exc,
                )
                result.metadata["social_attention_status"] = "model_unavailable"
                return
        elif not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            failure = {
                "stage": "social_attention",
                "failure_class": "latency_budget_exhausted",
                "failure_domain": "auxiliary_latency",
                "architecture_attribution": "not_evaluated",
                "retryable": True,
                "configured_wait_after_response_ms": configured_wait_ms,
                "effective_wait_after_response_ms": 0,
            }
            record_failure(failure)
            result.metadata["social_attention_status"] = "skipped_latency_budget"
            result.trace.append(
                "runtime: social attention was not ready at response finalization; "
                "primary response was not delayed"
            )
            return

        if plan is None:
            try:
                plan = task.result()
            except Exception as exc:  # pragma: no cover - defensive
                failure = {
                    **llm_failure_metadata(exc),
                    "stage": "social_attention",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                }
                record_failure(failure)
                logger.warning(
                    "social_attention_task_failed sid=%s failure_class=%s failure_domain=%s "
                    "architecture_attribution=%s retryable=%s error_type=%s error=%s",
                    request.sid,
                    failure.get("failure_class"),
                    failure.get("failure_domain"),
                    failure.get("architecture_attribution"),
                    str(bool(failure.get("retryable"))).lower(),
                    type(exc).__name__,
                    exc,
                )
                result.metadata["social_attention_status"] = "model_unavailable"
                return
        if plan is None:
            failure = request.context.get("social_attention_failure")
            if isinstance(failure, dict):
                record_failure(failure)
                result.metadata["social_attention_status"] = str(
                    failure.get("failure_class") or "model_unavailable"
                )
            else:
                result.metadata["social_attention_status"] = "model_unavailable"
                result.metadata["social_attention_architecture_attribution"] = "not_evaluated"
            return

        result.metadata["social_attention_architecture_attribution"] = "not_evaluated"
        result.metadata["social_attention_plan"] = plan.model_dump(mode="json", exclude_none=True)
        mode = self.services.effective_social_attention_mode()
        if mode == "report_only":
            result.metadata["social_attention_status"] = "report_only"
            return
        capabilities, reasons = self.social_attention_planner.validate_and_materialize(
            request,
            result,
            plan,
        )
        if reasons:
            result.metadata["social_attention_validation_reasons"] = reasons
        if not capabilities:
            result.metadata["social_attention_status"] = (
                "not_selected" if plan.decision == "none" else "not_applied"
            )
            return
        for skill in capabilities:
            result.add_capability(skill)
        result.metadata["social_attention_status"] = "applied"
        result.metadata["social_attention_capability_ids"] = [skill.capability_id for skill in capabilities]
        result.trace.append(
            "runtime: applied model-authored social attention "
            + ",".join(skill.capability_id for skill in capabilities)
        )
