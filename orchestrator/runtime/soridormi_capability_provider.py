from __future__ import annotations

"""Chromie-side adapter for Soridormi dynamic named skills.

This module intentionally lives inside the Orchestrator runtime because it
implements Chromie's ``CapabilityRuntime`` provider interface. It is not the
Soridormi body controller and it does not contain per-skill hardware logic.

The adapter accepts a trusted ``CapabilityRequest`` that has already passed Chromie
preflight/confirmation gates, translates ``soridormi.<skill_id>`` into the
upstream Soridormi named-skill ID, and invokes the Soridormi MCP planning,
monitoring, execution, and cancellation tools. Soridormi still owns physical
planning, realtime safety, motion execution, refusal, and recovery.

Do not add one method per Soridormi skill here. New body skills should be
published by Soridormi through ``soridormi.skill.list`` and then imported into
Chromie's ``CapabilityRegistry`` dynamically.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from agent.app.tool_invocation import (
    AsyncToolInvoker,
    ToolCallOutcome,
    ToolInvocationContext,
)
from shared.chromie_contracts.interaction import CapabilityRequest, CapabilityResult
from shared.chromie_contracts.perception import live_perception_dependency_from_metadata
from shared.chromie_contracts.soridormi_body_contract import normalize_soridormi_body_contract

from .capability_runtime import (
    CapabilityDefinition,
    CapabilityExecutionContext,
    CapabilityRegistry,
    embodied_completion_evidence_policy,
)

logger = logging.getLogger(__name__)


SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "completed": {"type": "boolean"},
        "capability_id": {"type": "string"},
        "mode": {"type": "string"},
        "no_motion": {"type": "boolean"},
        "recommendation_only": {"type": "boolean"},
        "summary": {"type": "string"},
        "resource_outcome": {
            "type": ["object", "null"],
            "properties": {
                "responsibility_type": {
                    "type": "string",
                    "enum": ["acquire_and_deliver_resource"],
                },
                "resource_kind": {
                    "type": "string",
                    "enum": ["physical_object"],
                },
                "resource_description": {"type": "string"},
                "resource_acquired": {"type": "boolean"},
                "resource_delivered": {"type": "boolean"},
                "recipient_description": {"type": "string"},
                "mocked_simulation": {"type": "boolean"},
                "evidence_summary": {"type": "string"},
            },
            "required": [
                "responsibility_type",
                "resource_kind",
                "resource_acquired",
                "resource_delivered",
            ],
            "additionalProperties": False,
        },
    },
    "required": [
        "completed",
        "capability_id",
        "mode",
        "no_motion",
        "recommendation_only",
        "summary",
    ],
    "additionalProperties": False,
}


def import_soridormi_capability_catalog(
    registry: CapabilityRegistry,
    provider_skills: list[dict[str, Any]],
    *,
    provider_id: str = "soridormi.mcp",
    version: str = "0.1.0",
    mark_absent_unavailable: bool = True,
) -> None:
    """Translate Soridormi's wire skill catalog into canonical capabilities.

    ``skill_id`` belongs to the Soridormi provider protocol.  This adapter is
    the only layer that interprets it.  The generic CapabilityRegistry receives
    only canonical CapabilityDefinition objects and therefore remains
    provider/transport neutral.
    """

    definitions: list[CapabilityDefinition] = []
    seen: set[str] = set()
    for raw_item in provider_skills:
        if not isinstance(raw_item, dict):
            raise ValueError("Soridormi skill catalog entries must be objects")
        item = dict(raw_item)
        upstream_skill_id = str(item.get("skill_id", "")).strip()
        if not upstream_skill_id:
            raise ValueError("Soridormi skill catalog entry has no skill_id")
        capability_id = f"soridormi.{upstream_skill_id}"
        if capability_id in seen:
            raise ValueError(
                f"duplicate Soridormi wire skill_id in one catalog: {upstream_skill_id}"
            )
        seen.add(capability_id)

        execution = item.get("execution")
        execution_contract = execution if isinstance(execution, dict) else {}
        availability = item.get("availability")
        availability_contract = availability if isinstance(availability, dict) else {}
        confirmation = item.get("confirmation")
        confirmation_contract = confirmation if isinstance(confirmation, dict) else {}
        effects_raw = item.get("effects")
        if effects_raw is None:
            effects = ["physical_motion"]
        elif isinstance(effects_raw, list):
            effects = [str(value) for value in effects_raw if str(value).strip()]
        else:
            raise ValueError(
                f"Soridormi skill {upstream_skill_id!r} effects must be a list"
            )
        safety_class = str(item.get("safety_class") or "physical_motion")
        provider_requires_confirmation = bool(
            item.get(
                "requires_confirmation",
                confirmation_contract.get("required", False),
            )
        )
        timeout_s = item.get("timeout_s", execution_contract.get("timeout_s", 30.0))
        body_contract = normalize_soridormi_body_contract(item)
        upstream_metadata = item.get("metadata")
        if not isinstance(upstream_metadata, dict):
            upstream_metadata = {}
        input_schema = item.get("parameters_schema") or item.get("input_schema") or {}
        if not isinstance(input_schema, dict):
            raise ValueError(
                f"Soridormi skill {upstream_skill_id!r} input schema must be an object"
            )

        definitions.append(
            CapabilityDefinition(
                capability_id=capability_id,
                version=str(item.get("version") or version),
                provider_id=provider_id,
                description=str(item.get("description") or ""),
                input_schema=dict(input_schema),
                output_schema=SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA,
                completion_evidence_policy=embodied_completion_evidence_policy(),
                available=bool(
                    item.get(
                        "available",
                        availability_contract.get("available", True),
                    )
                ),
                unavailable_reason=(
                    item.get("unavailable_reason") or availability_contract.get("reason")
                ),
                requires_confirmation=provider_requires_confirmation,
                interruptible=bool(item.get("interruptible", False)),
                can_run_parallel=bool(body_contract["can_run_parallel"]),
                exclusive_group=body_contract["exclusive_group"],
                timeout_ms=max(1, int(float(timeout_s or 30.0) * 1000)),
                idempotent=False,
                requires_safety_monitor=False,
                cancellation_domains=(
                    ("embodied_motion",)
                    if "physical_motion" in effects
                    or body_contract["provider_local_activity_compilation"]
                    else ()
                ),
                metadata={
                    "upstream_skill_id": upstream_skill_id,
                    "effects": effects,
                    "safety_class": safety_class,
                    "cancellation_granularity": (
                        "provider_activity"
                        if body_contract["provider_local_activity_compilation"]
                        else "global_domain"
                        if "physical_motion" in effects
                        else "request"
                    ),
                    "execution": execution,
                    "fallback": item.get("fallback"),
                    "hardware_enabled": item.get("hardware_enabled"),
                    "provider_managed_safety_monitor": True,
                    "resource_claims": list(body_contract["resource_claims"]),
                    "execution_lane": "activity",
                    "body_lane": body_contract["body_lane"],
                    "ability_class": body_contract["ability_class"],
                    "control_coupling": body_contract["control_coupling"],
                    "concurrency": dict(body_contract["canonical_concurrency"]),
                    "parallel_metadata_declared": body_contract[
                        "parallel_metadata_declared"
                    ],
                    "provider_local_activity_compilation": body_contract[
                        "provider_local_activity_compilation"
                    ],
                    "execution_constraints": dict(
                        body_contract["execution_constraints"]
                    ),
                    "output_contract": "chromie_soridormi_named_capability_v1",
                    "behavior_domains": [
                        str(value)
                        for value in upstream_metadata.get("behavior_domains", [])
                        if str(value).strip()
                    ],
                    "semantic_scope": (
                        dict(upstream_metadata.get("semantic_scope"))
                        if isinstance(upstream_metadata.get("semantic_scope"), dict)
                        else {}
                    ),
                    "resource_contract": (
                        dict(upstream_metadata.get("resource_contract"))
                        if isinstance(upstream_metadata.get("resource_contract"), dict)
                        else {}
                    ),
                },
            )
        )

    registry.replace_provider_capabilities(
        definitions,
        provider_id=provider_id,
        namespace_prefix="soridormi.",
        mark_absent_unavailable=mark_absent_unavailable,
    )


class SoridormiInvoker(AsyncToolInvoker, Protocol):
    pass


class SoridormiCapabilityProvider:
    """Adapter from Chromie's CapabilityRuntime to Soridormi MCP named skills.

    The class name deliberately says "adapter" rather than "controller" or
    "hardware provider". Chromie supplies proposal-derived intent and trace
    metadata; Soridormi creates the body-owned plan, decides whether it is safe
    and feasible, monitors execution, and may refuse or reshape the request.
    """

    provider_id = "soridormi.mcp"

    def __init__(
        self,
        invoker: SoridormiInvoker,
        *,
        activity_poll_interval_s: float = 0.1,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if activity_poll_interval_s < 0:
            raise ValueError("activity_poll_interval_s must be >= 0")
        self.invoker = invoker
        self._activity_poll_interval_s = activity_poll_interval_s
        self._sleep = sleep or asyncio.sleep

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        upstream_skill_id = str(
            definition.metadata.get("upstream_skill_id")
            or request.capability_id.removeprefix("soridormi.")
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
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
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
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="refused",
                provider_id=self.provider_id,
                output=self._canonical_provider_output(monitored.output, request=request),
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
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=self._canonical_provider_output(executed.output, request=request),
                reason_code="execution_capability_mismatch",
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
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed" if completed else "failed",
            provider_id=self.provider_id,
            output=(
                self._successful_execution_output(
                    executed.output,
                    request=request,
                    upstream_skill_id=upstream_skill_id,
                )
                if completed
                else self._canonical_provider_output(executed.output, request=request)
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
            tuple[CapabilityRequest, CapabilityDefinition, CapabilityExecutionContext]
        ],
    ) -> list[CapabilityResult]:
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
                or request.capability_id.removeprefix("soridormi.")
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
        terminal_output = await self._monitor_activity_until_terminal(
            items,
            executed.output,
            activity_id=activity_id,
            coordination_id=coordination_id,
        )
        return self._member_results_from_activity(
            items,
            terminal_output,
            activity_id=activity_id,
            coordination_id=coordination_id,
        )

    async def _monitor_activity_until_terminal(
        self,
        items: list[
            tuple[CapabilityRequest, CapabilityDefinition, CapabilityExecutionContext]
        ],
        initial_output: dict[str, Any],
        *,
        activity_id: str,
        coordination_id: str,
    ) -> dict[str, Any]:
        """Map Soridormi activity status into generic Runtime progress.

        ``activity.execute`` may acknowledge a long-running provider activity
        before it is terminal.  Chromie's provider task remains alive behind the
        already-detached CapabilityRuntime submission, while status snapshots are
        published as mechanical progress events.  Soridormi remains the owner of
        physical feasibility, execution, recovery, and stop truth.
        """

        output = dict(initial_output)
        while True:
            reported_activity_id = str(
                output.get("compiled_activity_id") or output.get("plan_id") or activity_id
            ).strip()
            if reported_activity_id != activity_id:
                raise RuntimeError(
                    "Soridormi activity status identity mismatch: "
                    f"expected={activity_id!r} actual={reported_activity_id!r}"
                )
            status = str(output.get("status") or "").strip().lower()
            terminal = bool(output.get("terminal")) or status in {
                "completed",
                "completed_with_degradation",
                "cancelled",
                "failed",
            }
            if terminal:
                return output

            progress = {
                "provider_activity_id": activity_id,
                "coordination_id": coordination_id,
                "status": status or "running",
                "terminal": False,
            }
            if output.get("estimated_duration_s") is not None:
                progress["estimated_duration_s"] = output.get("estimated_duration_s")
            member_results = output.get("member_results")
            if isinstance(member_results, dict):
                progress["member_status"] = {
                    str(member_id): str(
                        member.get("status") or ""
                    )
                    for member_id, member in member_results.items()
                    if isinstance(member, dict)
                }
            for _, _, context in items:
                await context.publish_progress(
                    progress,
                    message=f"Soridormi activity {status or 'running'}",
                )

            if self._activity_poll_interval_s > 0:
                await self._sleep(self._activity_poll_interval_s)
            status_outcome = await self.invoker.invoke(
                "soridormi.activity.status",
                {"compiled_activity_id": activity_id},
            )
            failure = self._group_failure_results(
                items,
                status_outcome,
                stage="status",
            )
            if failure is not None:
                # Runtime/provider contracts require one terminal result per
                # request.  Convert the failed status observation to one
                # aggregate-shaped terminal snapshot so the existing exact-member
                # reconciler fails closed for every member.
                return {
                    "compiled_activity_id": activity_id,
                    "coordination_id": coordination_id,
                    "status": "failed",
                    "terminal": True,
                    "summary": status_outcome.error or "Soridormi activity status failed",
                    "member_results": {
                        request.request_id: {
                            "status": "failed",
                            "completed": False,
                            "reason_code": "activity_status_failed",
                            "summary": status_outcome.error
                            or "Soridormi activity status failed",
                        }
                        for request, _, _ in items
                    },
                }
            output = dict(status_outcome.output)

    @staticmethod
    def _optional_auxiliary_member(request: CapabilityRequest) -> bool:
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
            tuple[CapabilityRequest, CapabilityDefinition, CapabilityExecutionContext]
        ],
        *,
        status: str,
        reason_code: str,
        message: str,
        output: dict[str, Any] | None = None,
    ) -> list[CapabilityResult]:
        return [
            CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status=status,
                provider_id=SoridormiCapabilityProvider.provider_id,
                output=SoridormiCapabilityProvider._canonical_provider_output(
                    output or {}, request=request
                ),
                reason_code=reason_code,
                message=message,
            )
            for request, definition, _ in items
        ]

    def _group_failure_results(
        self,
        items: list[
            tuple[CapabilityRequest, CapabilityDefinition, CapabilityExecutionContext]
        ],
        outcome: ToolCallOutcome,
        *,
        stage: str,
    ) -> list[CapabilityResult] | None:
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
            tuple[CapabilityRequest, CapabilityDefinition, CapabilityExecutionContext]
        ],
        output: dict[str, Any],
        *,
        activity_id: str,
        coordination_id: str,
    ) -> list[CapabilityResult]:
        aggregate_status = str(output.get("status") or "").strip()
        member_results = output.get("member_results")
        if not isinstance(member_results, dict):
            member_results = {}
        mode = str(output.get("mode") or "")
        results: list[CapabilityResult] = []
        for request, definition, _ in items:
            raw = member_results.get(request.request_id)
            if not isinstance(raw, dict):
                results.append(
                    CapabilityResult(
                        request_id=request.request_id,
                        capability_id=request.capability_id,
                        capability_version=definition.version,
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
                or request.capability_id.removeprefix("soridormi.")
            )
            reason_code = str(raw.get("reason_code") or "").strip() or None
            summary = str(
                raw.get("summary")
                or raw.get("message")
                or output.get("summary")
                or ""
            )
            results.append(
                CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status=status,
                    provider_id=self.provider_id,
                    output={
                        "completed": completed,
                        "capability_id": request.capability_id,
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
        request: CapabilityRequest,
        definition: CapabilityDefinition,
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
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        output: dict[str, Any],
    ) -> CapabilityResult | None:
        metadata = definition.metadata if isinstance(definition.metadata, dict) else {}
        semantic_scope = metadata.get("semantic_scope")
        if not isinstance(semantic_scope, dict):
            return None
        if semantic_scope.get("responsibility_type") != "acquire_and_deliver_resource":
            return None

        resource_contract = metadata.get("resource_contract")
        resource_contract = (
            resource_contract if isinstance(resource_contract, dict) else {}
        )
        completion_requires = [
            str(value).strip()
            for value in resource_contract.get("completion_requires", [])
            if str(value).strip()
        ]
        # Legacy complete resource providers predate per-capability completion
        # declarations. Preserve their stricter acquisition+delivery requirement.
        if not completion_requires:
            completion_requires = ["resource_acquired", "resource_delivered"]

        resource_outcome = output.get("resource_outcome")
        if not isinstance(resource_outcome, dict):
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=self._canonical_provider_output(output, request=request),
                reason_code="resource_outcome_missing",
                message=(
                    "Provider reported completion without required resource evidence"
                ),
            )
        missing = [
            field
            for field in completion_requires
            if resource_outcome.get(field) is not True
        ]
        if missing:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=self._canonical_provider_output(output, request=request),
                reason_code="resource_completion_incomplete",
                message=(
                    "Provider did not prove required resource completion fields: "
                    + ",".join(missing)
                ),
            )
        return None

    @staticmethod
    def _canonical_provider_output(
        output: dict[str, Any],
        *,
        request: CapabilityRequest,
    ) -> dict[str, Any]:
        """Remove provider-local executable identity from canonical result output.

        Soridormi wire ``skill_id`` is useful for adapter consistency checks, but it
        is not Chromie's identity authority.  Preserve diagnostic/provider payload
        fields while stripping retired executable identity names before a
        CapabilityResult crosses back into the generic runtime.
        """

        def scrub(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    str(key): scrub(item)
                    for key, item in value.items()
                    if str(key) not in {"skill_id", "skill_version"}
                }
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value

        projected = scrub(dict(output))
        if not isinstance(projected, dict):  # pragma: no cover - defensive typing guard
            projected = {}
        projected["capability_id"] = request.capability_id
        return projected

    @staticmethod
    def _successful_execution_output(
        output: dict[str, Any],
        *,
        request: CapabilityRequest,
        upstream_skill_id: str,
    ) -> dict[str, Any]:
        """Project successful provider output into the declared adapter schema."""

        projected = {
            "completed": True,
            "capability_id": str(request.capability_id),
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
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
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
            "capability_id": request.capability_id,
            "upstream_skill_id": upstream_skill_id,
            "capability_version": request.capability_version or definition.version,
            "provider_id": self.provider_id,
            "trace_id": context.trace.trace_id,
            "source_component": str(
                request.metadata.get("source_component")
                or request.metadata.get("source")
                or "interaction_response"
            ),
        }
        for source_key, target_key in (
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
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
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
                "Soridormi cancellation failed request_id=%s capability_id=%s: %s",
                request.request_id,
                request.capability_id,
                message,
            )
            raise RuntimeError(message)
        if outcome.output.get("cancelled") is not True:
            message = (
                "Soridormi cancellation did not confirm cancelled=true"
            )
            logger.warning(
                "Soridormi cancellation unconfirmed request_id=%s "
                "capability_id=%s output=%s",
                request.request_id,
                request.capability_id,
                outcome.output,
            )
            raise RuntimeError(message)

    def _failure_result(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        outcome: ToolCallOutcome,
        *,
        stage: str,
    ) -> CapabilityResult | None:
        if outcome.status == "success":
            return None
        status = "timed_out" if outcome.status == "timeout" else "failed"
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status=status,
            provider_id=self.provider_id,
            output=self._canonical_provider_output(outcome.output, request=request),
            reason_code=f"{stage}_{outcome.status}",
            message=outcome.error or f"Soridormi {stage} failed",
        )
