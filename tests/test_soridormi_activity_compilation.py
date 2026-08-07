from __future__ import annotations

import unittest
from typing import Any

from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.loader import build_chromie_registry
from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.skill_runtime import (
    RuntimeAuthorization,
    SkillExecutionContext,
    SkillRegistry,
    SkillRuntime,
)
from orchestrator.runtime.soridormi_skill_provider import SoridormiNamedSkillAdapter
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    SkillRequest,
    SkillTrace,
)


_WALK_CONCURRENCY = {
    "ability_class": "locomotion_whole_body",
    "control_coupling": "primary_body_controller",
    "write_resources": ["body.primary_motion"],
    "safety_preemption": "safe_hold",
}
_BLINK_CONCURRENCY = {
    "ability_class": "subtle_expression",
    "control_coupling": "independent_output",
    "write_resources": ["visual.eyes"],
    "parallel_safe_with": ["locomotion_whole_body"],
    "safety_preemption": "drop_optional_expression",
}


def _skill(
    skill_id: str,
    concurrency: dict[str, Any],
    *,
    effects: list[str],
    safety_class: str,
) -> dict[str, Any]:
    return {
        "skill_id": skill_id,
        "available": True,
        "description": skill_id,
        "parameters_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "effects": effects,
        "safety_class": safety_class,
        "interruptible": True,
        "requires_confirmation": False,
        "concurrency": concurrency,
    }


class _ActivityInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append((tool_name, args, context))
        if tool_name == "soridormi.activity.compile":
            return ToolCallOutcome.success(
                {
                    "compiled_activity_id": "activity-1",
                    "status": "compiled",
                }
            )
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.activity.execute":
            return ToolCallOutcome.success(
                {
                    "compiled_activity_id": "activity-1",
                    "status": "completed",
                    "mode": "sim",
                    "summary": "body activity completed",
                    "member_results": {
                        "walk-request": {
                            "status": "completed",
                            "completed": True,
                            "skill_id": "walk_forward",
                            "summary": "walk completed",
                        },
                        "blink-request": {
                            "status": "completed",
                            "completed": True,
                            "skill_id": "blink_eyes",
                            "summary": "blink completed",
                            "optional": True,
                        },
                    },
                }
            )
        if tool_name == "soridormi.activity.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        return ToolCallOutcome.failed(f"unknown tool: {tool_name}")


class _CatalogInvoker:
    async def invoke(self, tool_name: str, args: dict[str, Any]) -> ToolCallOutcome:
        if tool_name != "soridormi.skill.list":
            return ToolCallOutcome.failed(f"unexpected tool: {tool_name}")
        return ToolCallOutcome.success(
            {
                "mode": "sim",
                "skills": [
                    _skill(
                        "walk_forward",
                        _WALK_CONCURRENCY,
                        effects=["physical_motion"],
                        safety_class="physical_motion",
                    ),
                    _skill(
                        "blink_eyes",
                        _BLINK_CONCURRENCY,
                        effects=["visual_expression"],
                        safety_class="low_risk_action",
                    ),
                ],
            }
        )


class SoridormiActivityCompilationTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, invoker: _ActivityInvoker) -> SkillRuntime:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                _skill(
                    "walk_forward",
                    _WALK_CONCURRENCY,
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                ),
                _skill(
                    "blink_eyes",
                    _BLINK_CONCURRENCY,
                    effects=["visual_expression"],
                    safety_class="low_risk_action",
                ),
            ]
        )
        runtime = SkillRuntime(registry, max_concurrency=3)
        runtime.register_provider(SoridormiNamedSkillAdapter(invoker))
        return runtime

    async def test_registry_preserves_nested_provider_contract_exactly(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                _skill(
                    "walk_forward",
                    _WALK_CONCURRENCY,
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                ),
                _skill(
                    "blink_eyes",
                    _BLINK_CONCURRENCY,
                    effects=["visual_expression"],
                    safety_class="low_risk_action",
                ),
            ]
        )

        walk = registry.get("soridormi.walk_forward")
        blink = registry.get("soridormi.blink_eyes")
        self.assertEqual(walk.metadata["concurrency"], _WALK_CONCURRENCY)
        self.assertEqual(blink.metadata["concurrency"], _BLINK_CONCURRENCY)
        self.assertEqual(walk.metadata["resource_claims"], ["body.primary_motion"])
        self.assertEqual(blink.metadata["resource_claims"], ["visual.eyes"])
        self.assertEqual(walk.metadata["control_coupling"], "primary_body_controller")
        self.assertEqual(blink.metadata["control_coupling"], "independent_output")
        self.assertTrue(walk.metadata["provider_local_activity_compilation"])
        self.assertTrue(blink.metadata["provider_local_activity_compilation"])

    async def test_catalog_projects_nested_contract_without_name_inference(self) -> None:
        catalog = CapabilityCatalog(
            build_chromie_registry(),
            live_invoker=_CatalogInvoker(),
            min_score=0.0,
        )

        walk = await catalog.get_capability("soridormi.walk_forward", refresh=True)
        blink = await catalog.get_capability("soridormi.blink_eyes", refresh=False)

        self.assertIsNotNone(walk)
        self.assertIsNotNone(blink)
        assert walk is not None and blink is not None
        self.assertEqual(walk.metadata["concurrency"], _WALK_CONCURRENCY)
        self.assertEqual(blink.metadata["concurrency"], _BLINK_CONCURRENCY)
        self.assertEqual(walk.resource_claims, ["body.primary_motion"])
        self.assertEqual(blink.resource_claims, ["visual.eyes"])

    async def test_runtime_compiles_same_provider_members_once(self) -> None:
        invoker = _ActivityInvoker()
        runtime = self._runtime(invoker)
        response = InteractionResponse(
            interaction_id="activity-interaction",
            skills=[
                SkillRequest(
                    request_id="walk-request",
                    skill_id="soridormi.walk_forward",
                    args={},
                    timing="parallel",
                    metadata={
                        "coordination_id": "together-1",
                        "source": "goal_driven_canonical_plan",
                        "source_goal_ids": ["goal-walk"],
                    },
                ),
                SkillRequest(
                    request_id="blink-request",
                    skill_id="soridormi.blink_eyes",
                    args={},
                    timing="parallel",
                    metadata={
                        "coordination_id": "together-1",
                        "source": "social_attention_plan",
                        "auxiliary_social_attention": True,
                    },
                ),
            ],
        )

        result = await runtime.execute(
            response,
            authorization=RuntimeAuthorization(safety_monitor_active=True),
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual([item.request_id for item in result.results], [
            "walk-request",
            "blink-request",
        ])
        self.assertEqual([item.status for item in result.results], [
            "completed",
            "completed",
        ])
        self.assertEqual(
            [tool for tool, _, _ in invoker.calls],
            [
                "soridormi.activity.compile",
                "soridormi.safety.monitor_motion",
                "soridormi.activity.execute",
            ],
        )
        compile_args = invoker.calls[0][1]
        self.assertEqual(compile_args["coordination_id"], "together-1")
        self.assertEqual(
            [item["member_id"] for item in compile_args["members"]],
            ["walk-request", "blink-request"],
        )
        self.assertFalse(compile_args["members"][0]["optional"])
        self.assertTrue(compile_args["members"][1]["optional"])
        self.assertEqual(
            result.results[0].metadata["provider_activity_id"],
            "activity-1",
        )
        self.assertEqual(
            result.results[0].metadata["source_goal_ids"],
            ["goal-walk"],
        )
        self.assertEqual(
            result.traces[0].events[-1].data["provider_activity_id"],
            "activity-1",
        )
        self.assertEqual(
            result.traces[1].events[-1].data["provider_activity_id"],
            "activity-1",
        )

    async def test_activity_cancel_uses_compiled_activity_identity(self) -> None:
        invoker = _ActivityInvoker()
        adapter = SoridormiNamedSkillAdapter(invoker)
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                _skill(
                    "walk_forward",
                    _WALK_CONCURRENCY,
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                )
            ]
        )
        definition = registry.get("soridormi.walk_forward")
        request = SkillRequest(
            request_id="walk-request",
            skill_id="soridormi.walk_forward",
        )
        context = SkillExecutionContext(
            interaction_id="activity-interaction",
            provider_state={"provider_activity_id": "activity-1"},
            trace=SkillTrace(
                interaction_id="activity-interaction",
                request_id="walk-request",
                skill_id="soridormi.walk_forward",
                provider_id=adapter.provider_id,
            ),
        )

        await adapter.cancel(request, definition, context)

        tool, args, _ = invoker.calls[-1]
        self.assertEqual(tool, "soridormi.activity.cancel")
        self.assertEqual(args["compiled_activity_id"], "activity-1")


if __name__ == "__main__":
    unittest.main()
