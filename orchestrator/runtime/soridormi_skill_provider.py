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

        trusted_preflight_authorized = self._trusted_named_skill_preflight(
            request,
            definition,
            planned.output,
        )
        executed = await self.invoker.invoke(
            "soridormi.skill.execute_plan",
            {"plan_id": plan_id},
            context=ToolInvocationContext(
                allow_side_effects=True,
                confirmed=context.confirmed,
                trusted_preflight_authorized=trusted_preflight_authorized,
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
        if completed:
            resource_failure = self._resource_completion_failure(
                request,
                definition,
                executed.output,
            )
            if resource_failure is not None:
                return resource_failure
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

    async def execute_group(
        self,
        items: list[
            tuple[SkillRequest, SkillDefinition, SkillExecutionContext]
        ],
    ) -> list[SkillResult]:
        """Compile and execute exact same-provider body members as one activity.

        Chromie's Cognitive Planner has already selected every semantic
        capability. This adapter performs no planning: it assembles the exact
        requests under one ``coordination_id`` and asks Soridormi's deterministic
        embodied compiler to validate resources, controller coupling, and safety.
        """

        if len(items) < 2:
            raise ValueError("Soridormi body activity requires at least two members")
        coordination_ids = {
            str(request.metadata.get("coordination_id") or "").strip()
            for request, _, _ in items
            if str(request.metadata.get("coordination_id") or "").strip()
        }
        if len(coordination_ids) > 1:
            raise ValueError(
                "Soridormi body activity members have different coordination_id values"
            )
        coordination_id = (
            next(iter(coordination_ids))
            if coordination_ids
            else f"{items[0][2].interaction_id}:body"
        )

        members: list[dict[str, Any]] = []
        for request, definition, _ in items:
            upstream_skill_id = str(
                definition.metadata.get("upstream_skill_id")
                or request.skill_id.removeprefix("soridormi.")
            )
            members.append(
                {
                    "member_id": request.request_id,
                    "skill_id": upstream_skill_id,
                    "parameters": dict(request.args),
                    "optional": self._optional_auxiliary_member(request),
                }
            )

        first_request, first_definition, first_context = items[0]
        compiled = await self._invoke_activity_tool(
            "soridormi.activity.compile",
            "soridormi.activity.create_plan",
            {
                "coordination_id": coordination_id,
                "members": members,
                "chromie_intent": {
                    **self._chromie_intent_payload(
                        first_request,
                        first_definition,
                        first_context,
                        upstream_skill_id="body_activity",
                    ),
                    "request_ids": [
                        request.request_id for request, _, _ in items
                    ],
                    "source_component": "chromie_runtime_coordinator",
                },
            },
        )
        compile_failure = self._group_failure_results(
            items,
            compiled,
            stage="compile",
        )
        if compile_failure is not None:
            return compile_failure

        activity_id = str(
            compiled.output.get("compiled_activity_id")
            or compiled.output.get("plan_id")
            or ""
        ).strip()
        if not activity_id:
            return self._group_terminal_results(
                items,
                status="failed",
                reason_code="invalid_compiler_response",
                message="Soridormi compiler response has no compiled_activity_id",
            )
        shared_state = first_context.provider_state
        shared_state.update(
            {
                "provider_activity_id": activity_id,
                "coordination_id": coordination_id,
            }
        )
        for _, _, context in items[1:]:
            context.provider_state = shared_state

        monitored = await self.invoker.invoke(
            "soridormi.safety.monitor_motion",
            {
                "coordination_id": coordination_id,
                "compiled_activity_id": activity_id,
            },
            context=ToolInvocationContext(allow_safety_controls=True),
        )
        monitor_failure = self._group_failure_results(
            items,
            monitored,
            stage="monitor",
        )
        if monitor_failure is not None:
            return monitor_failure
        if monitored.output.get("ok") is not True:
            return self._group_terminal_results(
                items,
                status="refused",
                reason_code="safety_monitor_refused",
                message=str(
                    monitored.output.get("event")
                    or "Soridormi safety monitor refused body activity"
                ),
                output=monitored.output,
            )

        group_confirmed = all(
            not (request.requires_confirmation or definition.requires_confirmation)
            or context.confirmed
            for request, definition, context in items
        )
        executed = await self._invoke_activity_tool(
            "soridormi.activity.execute",
            "soridormi.activity.execute_plan",
            {"compiled_activity_id": activity_id, "plan_id": activity_id},
            context=ToolInvocationContext(
                allow_side_effects=True,
                confirmed=group_confirmed,
                trusted_preflight_authorized=group_confirmed,
                safety_monitor_active=True,
            ),
        )
        execute_failure = self._group_failure_results(
            items,
            executed,
            stage="execute",
        )
        if execute_failure is not None:
            return execute_failure
        return self._member_results_from_activity(
            items,
            executed.output,
            activity_id=activity_id,
            coordination_id=coordination_id,
        )

    @staticmethod
    def _optional_auxiliary_member(request: SkillRequest) -> bool:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        source_goal_ids = metadata.get("source_goal_ids") or []
        return bool(
            metadata.get("source") == "social_attention_plan"
            and metadata.get("auxiliary_social_attention") is True
            and not any(str(value).strip() for value in source_goal_ids)
        )

    async def _invoke_activity_tool(
        self,
        canonical_tool: str,
        compatibility_tool: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        outcome = await self.invoker.invoke(
            canonical_tool,
            args,
            context=context,
        )
        if outcome.status == "success" or not self._tool_is_unavailable(outcome):
            return outcome
        compatibility_args = dict(args)
        if canonical_tool.endswith(".execute"):
            compatibility_args = {
                "plan_id": str(
                    args.get("compiled_activity_id")
                    or args.get("plan_id")
                    or ""
                )
            }
        return await self.invoker.invoke(
            compatibility_tool,
            compatibility_args,
            context=context,
        )

    @staticmethod
    def _tool_is_unavailable(outcome: ToolCallOutcome) -> bool:
        text = " ".join(
            str(value or "")
            for value in (
                outcome.error,
                outcome.output.get("error") if isinstance(outcome.output, dict) else "",
                outcome.output.get("message") if isinstance(outcome.output, dict) else "",
            )
        ).casefold()
        return outcome.status != "success" and any(
            marker in text
            for marker in (
                "unknown tool",
                "tool not found",
                "unsupported tool",
                "method not found",
            )
        )

    @staticmethod
    def _group_terminal_results(
        items: list[
            tuple[SkillRequest, SkillDefinition, SkillExecutionContext]
        ],
        *,
        status: str,
        reason_code: str,
        message: str,
        output: dict[str, Any] | None = None,
    ) -> list[SkillResult]:
        return [
            SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status=status,
                provider_id=SoridormiNamedSkillAdapter.provider_id,
                output=dict(output or {}),
                reason_code=reason_code,
                message=message,
            )
            for request, definition, _ in items
        ]

    def _group_failure_results(
        self,
        items: list[
            tuple[SkillRequest, SkillDefinition, SkillExecutionContext]
        ],
        outcome: ToolCallOutcome,
        *,
        stage: str,
    ) -> list[SkillResult] | None:
        if outcome.status == "success":
            return None
        status = "timed_out" if outcome.status == "timeout" else "failed"
        return self._group_terminal_results(
            items,
            status=status,
            reason_code=f"activity_{stage}_{outcome.status}",
            message=outcome.error or f"Soridormi activity {stage} failed",
            output=outcome.output,
        )

    def _member_results_from_activity(
        self,
        items: list[
            tuple[SkillRequest, SkillDefinition, SkillExecutionContext]
        ],
        output: dict[str, Any],
        *,
        activity_id: str,
        coordination_id: str,
    ) -> list[SkillResult]:
        aggregate_status = str(output.get("status") or "").strip()
        member_results = output.get("member_results")
        if not isinstance(member_results, dict):
            member_results = {}
        mode = str(output.get("mode") or "")
        results: list[SkillResult] = []
        for request, definition, _ in items:
            raw = member_results.get(request.request_id)
            if not isinstance(raw, dict):
                results.append(
                    SkillResult(
                        request_id=request.request_id,
                        skill_id=request.skill_id,
                        skill_version=definition.version,
                        status="failed",
                        provider_id=self.provider_id,
                        reason_code="activity_member_result_missing",
                        message=(
                            "Soridormi activity omitted evidence for this exact member"
                        ),
                        metadata={
                            "provider_activity_id": activity_id,
                            "coordination_id": coordination_id,
                            "aggregate_status": aggregate_status,
                        },
                    )
                )
                continue
            raw_status = str(raw.get("status") or "").strip()
            completed = raw.get("completed") is True or raw_status == "completed"
            cancelled = raw.get("cancelled") is True or raw_status == "cancelled"
            status = "completed" if completed else "cancelled" if cancelled else "failed"
            upstream_skill_id = str(
                definition.metadata.get("upstream_skill_id")
                or request.skill_id.removeprefix("soridormi.")
            )
            reason_code = str(raw.get("reason_code") or "").strip() or None
            summary = str(
                raw.get("summary")
                or raw.get("message")
                or output.get("summary")
                or ""
            )
            results.append(
                SkillResult(
                    request_id=request.request_id,
                    skill_id=request.skill_id,
                    skill_version=definition.version,
                    status=status,
                    provider_id=self.provider_id,
                    output={
                        "completed": completed,
                        "skill_id": str(raw.get("skill_id") or upstream_skill_id),
                        "mode": mode,
                        "no_motion": raw.get("no_motion") is True,
                        "recommendation_only": raw.get("recommendation_only") is True,
                        "summary": summary,
                    },
                    metadata={
                        "provider_activity_id": activity_id,
                        "coordination_id": coordination_id,
                        "aggregate_status": aggregate_status,
                        "member_status": raw_status or status,
                        "optional": raw.get("optional") is True,
                        "degraded": aggregate_status == "completed_with_degradation",
                    },
                    reason_code=reason_code if status != "completed" else None,
                    message="" if status == "completed" else summary,
                )
            )
        return results

    @staticmethod
    def _trusted_named_skill_preflight(
        request: SkillRequest,
        definition: SkillDefinition,
        planned_output: dict[str, Any],
    ) -> bool:
        """Bridge Soridormi's coarse execute-plan confirmation gate safely.

        ``soridormi.skill.execute_plan`` is confirmation-guarded because one MCP
        transport serves many motion classes.  The body-owned plan, however, may
        explicitly state that no additional confirmation is required.  Chromie may
        waive only that transport-level gate when all of the following are true:

        * Soridormi's freshly created plan says ``requires_confirmation=false``;
        * the live named-skill definition and committed request agree;
        * the request came from either a goal-grounded canonical plan or reviewed
          auxiliary Social Attention; and
        * Soridormi's safety monitor has already accepted the motion.

        This is not a fabricated ``confirmed=true`` claim.  The execution context
        keeps ``confirmed=false`` and records a trusted preflight authorization.
        Soridormi still owns planning, feasibility, monitoring, refusal, execution,
        and recovery.
        """

        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        definition_metadata = (
            definition.metadata if isinstance(definition.metadata, dict) else {}
        )
        source = str(metadata.get("source") or "").strip()
        safety_class = str(definition_metadata.get("safety_class") or "").strip()
        effects = {
            str(value).strip()
            for value in definition_metadata.get("effects", [])
            if str(value).strip()
        }

        reviewed_social = bool(
            source == "social_attention_plan"
            and metadata.get("auxiliary_social_attention") is True
            and safety_class == "low_risk_action"
            and "physical_motion" not in effects
        )
        canonical_goal_action = bool(
            source == "goal_driven_canonical_plan"
            and str(metadata.get("canonical_plan_id") or "").strip()
            and str(metadata.get("step_id") or "").strip()
            and any(
                str(value).strip()
                for value in metadata.get("source_goal_ids", [])
                if str(value).strip()
            )
            and safety_class in {"low_risk_action", "physical_motion"}
        )
        return bool(
            planned_output.get("requires_confirmation") is False
            and request.requires_confirmation is False
            and definition.requires_confirmation is False
            and (reviewed_social or canonical_goal_action)
        )

    def _resource_completion_failure(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        output: dict[str, Any],
    ) -> SkillResult | None:
        metadata = definition.metadata if isinstance(definition.metadata, dict) else {}
        semantic_scope = metadata.get("semantic_scope")
        if not isinstance(semantic_scope, dict):
            return None
        if semantic_scope.get("responsibility_type") != "acquire_and_deliver_resource":
            return None

        resource_outcome = output.get("resource_outcome")
        if not isinstance(resource_outcome, dict):
            return SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=output,
                reason_code="resource_outcome_missing",
                message=(
                    "Provider reported completion without acquisition-and-delivery evidence"
                ),
            )
        if (
            resource_outcome.get("resource_acquired") is not True
            or resource_outcome.get("resource_delivered") is not True
        ):
            return SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=output,
                reason_code="resource_delivery_incomplete",
                message=(
                    "Provider did not prove both resource acquisition and delivery"
                ),
            )
        return None

    @staticmethod
    def _successful_execution_output(
        output: dict[str, Any],
        *,
        upstream_skill_id: str,
    ) -> dict[str, Any]:
        """Project successful provider output into the declared adapter schema."""

        projected = {
            "completed": True,
            "skill_id": str(output.get("skill_id") or upstream_skill_id),
            "mode": str(output.get("mode") or ""),
            "no_motion": output.get("no_motion") is True,
            "recommendation_only": output.get("recommendation_only") is True,
            "summary": str(output.get("summary") or ""),
        }
        resource_outcome = output.get("resource_outcome")
        if isinstance(resource_outcome, dict):
            projected["resource_outcome"] = dict(resource_outcome)
        return projected

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
            ("goal_interpretation_source", "goal_interpretation_source"),
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
        activity_id = str(
            context.provider_state.get("provider_activity_id") or ""
        ).strip()
        if activity_id:
            outcome = await self.invoker.invoke(
                "soridormi.activity.cancel",
                {
                    "compiled_activity_id": activity_id,
                    "plan_id": activity_id,
                    "reason": context.cancellation_reason_code,
                },
                context=ToolInvocationContext(allow_safety_controls=True),
            )
        else:
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
