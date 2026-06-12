from __future__ import annotations

from typing import Protocol

from agent.app.tool_invocation import (
    AsyncToolInvoker,
    ToolCallOutcome,
    ToolInvocationContext,
)
from shared.chromie_contracts.interaction import SkillRequest, SkillResult

from .skill_runtime import SkillDefinition, SkillExecutionContext


class SoridormiInvoker(AsyncToolInvoker, Protocol):
    pass


class SoridormiMcpSkillProvider:
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
            {"skill_id": upstream_skill_id, "parameters": request.args},
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
        completed = executed.output.get("completed")
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed" if completed is not False else "failed",
            provider_id=self.provider_id,
            output=executed.output,
            reason_code=None if completed is not False else "execution_incomplete",
        )

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        await self.invoker.invoke(
            "soridormi.motion.cancel",
            {},
            context=ToolInvocationContext(allow_safety_controls=True),
        )

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
