from __future__ import annotations

"""Chromie-side adapter for Soridormi dynamic named skills.

This module intentionally lives inside the Orchestrator runtime because it
implements Chromie's ``SkillRuntime`` provider interface. It is not the
Soridormi body controller and it does not contain per-skill hardware logic.

The adapter accepts a trusted ``SkillRequest`` that has already passed Chromie
preflight/confirmation gates, translates ``soridormi.<skill_id>`` into the
upstream Soridormi named-skill ID, and invokes the Soridormi MCP planning,
monitoring, execution, and cancellation tools. Soridormi still owns physical
planning, realtime safety, motion execution, refusal, and recovery.

Do not add one method per Soridormi skill here. New body skills should be
published by Soridormi through ``soridormi.skill.list`` and then imported into
Chromie's ``SkillRegistry`` dynamically.
"""

import logging
from typing import Any, Protocol

from agent.app.tool_invocation import (
    AsyncToolInvoker,
    ToolCallOutcome,
    ToolInvocationContext,
)
from shared.chromie_contracts.interaction import SkillRequest, SkillResult
from shared.chromie_contracts.perception import live_perception_dependency_from_metadata

from .skill_runtime import SkillDefinition, SkillExecutionContext

logger = logging.getLogger(__name__)


class SoridormiInvoker(AsyncToolInvoker, Protocol):
    pass


class SoridormiNamedSkillAdapter:
    """Adapter from Chromie's SkillRuntime to Soridormi MCP named skills.

    The class name deliberately says "adapter" rather than "controller" or
    "hardware provider". Chromie supplies proposal-derived intent and trace
    metadata; Soridormi creates the body-owned plan, decides whether it is safe
    and feasible, monitors execution, and may refuse or reshape the request.
    """

    provider_id = "soridormi.mcp"

    def __init__(self, invoker: SoridormiInvoker) -> None:
        self.invoker = invoker

    async def execute(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> SkillResult:
        upstream_skill_id = str(
            definition.metadata.get("upstream_skill_id")
            or request.skill_id.removeprefix("soridormi.")
        )
        planned = await self.invoker.invoke(
            "soridormi.skill.create_plan",
            {
                "skill_id": upstream_skill_id,
                "parameters": request.args,
                "chromie_intent": self._chromie_intent_payload(
                    request,
                    definition,
                    context,
                    upstream_skill_id=upstream_skill_id,
                ),
            },
        )
        failure = self._failure_result(request, definition, planned, stage="plan")
        if failure:
            return failure
        plan_id = planned.output.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            return SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                reason_code="invalid_plan_response",
                message="Soridormi named-skill plan response has no plan_id",
            )

        monitored = await self.invoker.invoke(
            "soridormi.safety.monitor_motion",
            {"during_node_id": request.request_id},
            context=ToolInvocationContext(allow_safety_controls=True),
        )
        failure = self._failure_result(
            request,
            definition,
            monitored,
            stage="monitor",
        )
        if failure:
            return failure
        if monitored.output.get("ok") is not True:
            return SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="refused",
                provider_id=self.provider_id,
                output=monitored.output,
                reason_code="safety_monitor_refused",
                message=str(
                    monitored.output.get("event")
                    or "Soridormi safety monitor refused execution"
                ),
            )

        executed = await self.invoker.invoke(
            "soridormi.skill.execute_plan",
            {"plan_id": plan_id},
            context=ToolInvocationContext(
                allow_side_effects=True,
                confirmed=context.confirmed,
                safety_monitor_active=True,
            ),
        )
        failure = self._failure_result(request, definition, executed, stage="execute")
        if failure:
            return failure
        completed = executed.output.get("completed") is True
        executed_skill_id = executed.output.get("skill_id")
        if executed_skill_id is not None and executed_skill_id != upstream_skill_id:
            return SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=executed.output,
                reason_code="execution_skill_mismatch",
                message=(
                    "Soridormi completed a different skill than the requested "
                    f"{upstream_skill_id!r}"
                ),
            )
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed" if completed else "failed",
            provider_id=self.provider_id,
            output=(
                self._successful_execution_output(
                    executed.output,
                    upstream_skill_id=upstream_skill_id,
                )
                if completed
                else executed.output
            ),
            reason_code=None if completed else "execution_incomplete",
            message=(
                ""
                if completed
                else "Soridormi did not explicitly report skill completion"
            ),
        )

    @staticmethod
    def _successful_execution_output(
        output: dict[str, Any],
        *,
        upstream_skill_id: str,
    ) -> dict[str, Any]:
        """Project successful provider output into the declared adapter schema."""

        return {
            "completed": True,
            "skill_id": str(output.get("skill_id") or upstream_skill_id),
            "mode": str(output.get("mode") or ""),
            "no_motion": output.get("no_motion") is True,
            "recommendation_only": output.get("recommendation_only") is True,
            "summary": str(output.get("summary") or ""),
        }

    def _chromie_intent_payload(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
        *,
        upstream_skill_id: str,
    ) -> dict[str, Any]:
        """Return traceable proposal semantics for Soridormi planning.

        Chromie never sends body commands. Even for named skills, the payload
        passed to Soridormi is a proposal-derived intent that must be planned,
        validated, monitored, and possibly refused by Soridormi before any
        embodied execution occurs.
        """

        payload: dict[str, Any] = {
            "execution_mode": "proposed",
            "execution_semantics": "proposal_from_chromie",
            "requires_runtime_validation": True,
            "interaction_id": context.interaction_id,
            "request_id": request.request_id,
            "skill_id": request.skill_id,
            "upstream_skill_id": upstream_skill_id,
            "skill_version": request.skill_version or definition.version,
            "provider_id": self.provider_id,
            "trace_id": context.trace.trace_id,
            "source_component": str(
                request.metadata.get("source_component")
                or request.metadata.get("source")
                or "interaction_response"
            ),
        }
        for source_key, target_key in (
            ("route_source", "route_source"),
            ("route_stage", "route_stage"),
            ("route_task_source_stage", "route_task_source_stage"),
            ("route_confidence", "route_confidence"),
            ("router_source", "router_source"),
        ):
            value = request.metadata.get(source_key)
            if value is not None:
                payload[target_key] = value
        perception_dependency = live_perception_dependency_from_metadata(
            request.metadata,
        )
        if perception_dependency is not None:
            payload.update(perception_dependency)
        return payload

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        outcome = await self.invoker.invoke(
            "soridormi.motion.cancel",
            {},
            context=ToolInvocationContext(allow_safety_controls=True),
        )
        if outcome.status != "success":
            message = outcome.error or f"cancel returned {outcome.status}"
            logger.warning(
                "Soridormi cancellation failed request_id=%s skill_id=%s: %s",
                request.request_id,
                request.skill_id,
                message,
            )
            raise RuntimeError(message)
        if outcome.output.get("cancelled") is not True:
            message = (
                "Soridormi cancellation did not confirm cancelled=true"
            )
            logger.warning(
                "Soridormi cancellation unconfirmed request_id=%s "
                "skill_id=%s output=%s",
                request.request_id,
                request.skill_id,
                outcome.output,
            )
            raise RuntimeError(message)

    def _failure_result(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        outcome: ToolCallOutcome,
        *,
        stage: str,
    ) -> SkillResult | None:
        if outcome.status == "success":
            return None
        status = "timed_out" if outcome.status == "timeout" else "failed"
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status=status,
            provider_id=self.provider_id,
            output=outcome.output,
            reason_code=f"{stage}_{outcome.status}",
            message=outcome.error or f"Soridormi {stage} failed",
        )


# Backward-compatible name used by earlier Chromie tests and imports. Prefer
# SoridormiNamedSkillAdapter in new code because this module adapts the generic
# MCP named-skill protocol; it does not provide or control hardware skills.
SoridormiMcpSkillProvider = SoridormiNamedSkillAdapter
