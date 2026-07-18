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
    MotionPlannerAgent,
    RobotPoseControllerAgent,
    SafetyAgent,
    SpeakerAgent,
    ToolAgent,
    VisionAgent,
)
from .clients.ollama_client import llm_failure_metadata
from .dispatcher import selected_agents
from .interaction import InteractionDraft, NativeInteractionOutputError
from .social_attention import SocialAttentionPlanner
from .schema import AgentResult, AgentRunRequest, RouteDecision

try:
    from chromie_contracts.interaction import InteractionResponse, SkillRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest

logger = logging.getLogger("chromie.agent.runtime")


def _is_missing_ability_clarify(decision: RouteDecision) -> bool:
    return (
        decision.route == "clarify"
        and str(decision.intent or "") == "missing_or_unsupported_ability"
    )


def _safe_missing_ability_text(request: AgentRunRequest) -> str:
    text = " ".join((request.route_decision.speak_first or "").strip().split())
    if text:
        return text
    language = (request.language or request.route_decision.language or "").lower()
    zh = language.startswith("zh") or any("\u4e00" <= ch <= "\u9fff" for ch in request.text)
    if zh:
        return "我没有找到能安全执行这个动作的对应技能，所以不会猜一个相似动作来做。"
    return "I do not have a matching skill for that action, so I will not guess a similar movement."


def _router_fast_first_already_scheduled(decision: RouteDecision) -> bool:
    metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
    if metadata.get("fast_first_response_scheduled") is True:
        return True
    fast_first = metadata.get("fast_first_response")
    return isinstance(fast_first, dict) and fast_first.get("scheduled") is True


def _is_terminal_router_acknowledgement(decision: RouteDecision) -> bool:
    return (
        decision.route == "chat"
        and str(decision.intent or "").strip() in {"greeting", "gratitude_acknowledgement"}
        and decision.should_speak
        and (bool(decision.speak_first) or _router_fast_first_already_scheduled(decision))
    )




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
        self.social_attention_planner = SocialAttentionPlanner(services)

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

        if _is_terminal_router_acknowledgement(decision):
            result.status = "ok"
            intent = str(decision.intent or "").strip()
            is_greeting = intent == "greeting"
            result.reason = decision.reason or f"terminal_router_{intent or 'acknowledgement'}"
            if decision.speak_first:
                result.add_speak_immediate(
                    decision.speak_first,
                    style="brief",
                    priority=decision.priority,
                )
                result.trace.append(
                    "runtime: terminal router greeting emitted speak_first"
                    if is_greeting
                    else "runtime: terminal router acknowledgement emitted speak_first"
                )
            else:
                result.trace.append(
                    "runtime: terminal router greeting already spoken by fast-first"
                    if is_greeting
                    else "runtime: terminal router acknowledgement already spoken by fast-first"
                )
            result.trace.append(
                "runtime: terminal router greeting fast-first; skipped agent rewrite"
                if is_greeting
                else "runtime: terminal router acknowledgement; skipped agent rewrite"
            )
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
        await self._ensure_social_attention_candidates(request)
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

    async def _ensure_social_attention_candidates(
        self,
        request: AgentRunRequest,
        *,
        allow_when_off: bool = False,
    ) -> None:
        mode = self.services.effective_social_attention_mode()
        if mode == "off" and not allow_when_off:
            return
        catalog = self.services.capability_catalog
        if catalog is None:
            return

        # Social attention is a behavior domain, not a fixed action list. Refresh
        # the live catalog first, then discover every capability that declares
        # the domain. Explicit IDs remain an operator override for providers that
        # have not yet published domain metadata.
        if hasattr(catalog, "refresh_live_named_skills"):
            try:
                await catalog.refresh_live_named_skills()
            except Exception as exc:  # pragma: no cover - defensive service boundary
                logger.warning("social attention catalog refresh failed error=%s", exc)

        configured_ids = {
            capability_id
            for capability_id in self.services.social_attention_capability_ids
            if capability_id
        }
        candidate_ids: list[str] = []
        seen_ids: set[str] = set()

        entries = catalog.entries() if hasattr(catalog, "entries") else []
        for entry in entries:
            capability_id = str(getattr(entry, "capability_id", "") or "").strip()
            domains = {
                str(value).strip().lower()
                for value in (getattr(entry, "behavior_domains", None) or [])
                if str(value).strip()
            }
            if capability_id and (
                "social_attention" in domains or capability_id in configured_ids
            ):
                if capability_id not in seen_ids:
                    seen_ids.add(capability_id)
                    candidate_ids.append(capability_id)

        for capability_id in sorted(configured_ids):
            if capability_id not in seen_ids:
                seen_ids.add(capability_id)
                candidate_ids.append(capability_id)

        candidates: list[dict[str, Any]] = []
        for capability_id in candidate_ids:
            item = None
            if hasattr(catalog, "get_capability"):
                try:
                    item = await catalog.get_capability(capability_id)
                except Exception as exc:  # pragma: no cover - defensive service boundary
                    logger.warning(
                        "social attention capability lookup failed id=%s error=%s",
                        capability_id,
                        exc,
                    )
                    continue
            if item is None:
                item = next(
                    (
                        entry
                        for entry in entries
                        if str(getattr(entry, "capability_id", "")) == capability_id
                    ),
                    None,
                )
            if item is None:
                continue
            payload = (
                item.model_dump(mode="json")
                if hasattr(item, "model_dump")
                else dict(item)
                if isinstance(item, dict)
                else None
            )
            if not isinstance(payload, dict):
                continue
            if payload.get("available") is False:
                continue
            if payload.get("interaction_executable") is not True:
                continue
            if (
                not allow_when_off
                and mode == "sim_only"
                and str((payload.get("metadata") or {}).get("mode") or "") != "sim"
            ):
                continue
            domains = {
                str(value).strip().lower()
                for value in payload.get("behavior_domains") or []
                if str(value).strip()
            }
            if capability_id not in configured_ids and "social_attention" not in domains:
                continue
            candidates.append(payload)

        if candidates:
            request.context["social_attention_candidates"] = candidates
            request.context["social_attention_candidate_source"] = (
                "behavior_domain_catalog"
            )
            request.context["social_attention_target_evidence"] = (
                self._social_attention_target_evidence(request)
            )

    async def prepare_response_composition_context(
        self,
        request: AgentRunRequest,
    ) -> None:
        """Attach advisory social candidates and target evidence for PR6 composition."""
        await self._ensure_social_attention_candidates(request, allow_when_off=True)

    def _social_attention_target_evidence(self, request: AgentRunRequest) -> dict[str, Any]:
        for key in ("social_attention_target", "active_user_target", "perceived_user_target"):
            value = request.context.get(key)
            if isinstance(value, dict) and value:
                explicit_source = str(value.get("source") or "").strip()
                source = (
                    explicit_source
                    if explicit_source in {"live_perception", "conversation_context"}
                    else "live_perception"
                    if "perception" in key or "perceived" in key
                    else "conversation_context"
                )
                target = value.get("target")
                if not isinstance(target, dict):
                    target = dict(value)
                    target.pop("source", None)
                    target.pop("available", None)
                return {
                    "available": True,
                    "source": source,
                    "target": target,
                }

        target_ref = (self.services.social_attention_fallback_target or "none").strip()
        if target_ref.lower() in {"", "none", "off", "disabled"}:
            return {"available": False}
        target: dict[str, Any] = {
            "target_ref": target_ref,
            "source": "installation_calibration",
            "confidence": max(0.0, min(1.0, float(self.services.social_attention_fallback_confidence))),
        }
        direction = (self.services.social_attention_fallback_direction or "").strip()
        if direction:
            target["relative_direction"] = direction
        yaw = self.services.social_attention_fallback_yaw_rad
        if isinstance(yaw, (int, float)):
            target["suggested_args"] = {"target_yaw_rad": float(yaw)}
        return {"available": True, "source": "installation_calibration", "target": target}

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

        # Give the concurrently-started auxiliary task one event-loop turn.
        # This admits already-ready plans without adding a wall-clock wait to the
        # primary response path. Any plan still pending after that yield is
        # cancelled and recorded as optional evidence only.
        if not task.done():
            await asyncio.sleep(0)

        plan = None
        if task.done():
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
        else:
            configured_wait_ms = max(
                0, int(self.services.social_attention_wait_after_response_ms)
            )
            task.cancel()
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
        skills, reasons = self.social_attention_planner.validate_and_materialize(
            request,
            result,
            plan,
        )
        if reasons:
            result.metadata["social_attention_validation_reasons"] = reasons
        if not skills:
            result.metadata["social_attention_status"] = (
                "not_selected" if plan.decision == "none" else "not_applied"
            )
            return
        for skill in skills:
            result.add_skill(skill)
        result.metadata["social_attention_status"] = "applied"
        result.metadata["social_attention_skills"] = [skill.skill_id for skill in skills]
        result.trace.append(
            "runtime: applied model-authored social attention "
            + ",".join(skill.skill_id for skill in skills)
        )
