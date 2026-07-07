from __future__ import annotations

import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.skill_runtime import (
    RuntimeAuthorization,
    SkillRegistry,
    SkillRuntime,
)
from orchestrator.runtime.soridormi_skill_provider import SoridormiMcpSkillProvider
from shared.chromie_contracts.interaction import InteractionResponse


class _RecordingInvoker:
    def __init__(
        self,
        *,
        overrides: dict[str, ToolCallOutcome] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []
        self.overrides = overrides or {}

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append((tool_name, args, context))
        if tool_name in self.overrides:
            return self.overrides[tool_name]
        if tool_name == "soridormi.skill.create_plan":
            return ToolCallOutcome.success(
                {
                    "plan_id": "plan-1",
                    "skill_id": args["skill_id"],
                    "requires_confirmation": True,
                }
            )
        if tool_name == "soridormi.skill.execute_plan":
            return ToolCallOutcome.success(
                {
                    "completed": True,
                    "skill_id": "nod_yes",
                    "summary": "completed nod_yes",
                }
            )
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.motion.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


class SoridormiSkillProviderTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, invoker: _RecordingInvoker) -> SkillRuntime:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Nod the robot head.",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "minimum": 1, "maximum": 3},
                            "amplitude": {
                                "type": "string",
                                "enum": ["small", "medium"],
                            },
                        },
                        "additionalProperties": False,
                    },
                    "interruptible": True,
                    "execution": "scripted_keyframe",
                    "fallback": "neutral_head",
                }
            ]
        )
        runtime = SkillRuntime(registry)
        runtime.register_provider(SoridormiMcpSkillProvider(invoker))
        return runtime

    async def test_named_skill_uses_opaque_plan_execute_contract(self) -> None:
        invoker = _RecordingInvoker()
        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 2, "amplitude": "small"},
                    }
                ]
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids={"nod-1"},
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "completed")
        create_plan_args = invoker.calls[0][1]
        self.assertEqual(
            invoker.calls[0][0],
            "soridormi.skill.create_plan",
        )
        self.assertEqual(
            create_plan_args["skill_id"],
            "nod_yes",
        )
        self.assertEqual(
            create_plan_args["parameters"],
            {"count": 2, "amplitude": "small"},
        )
        self.assertEqual(
            create_plan_args["chromie_intent"]["execution_mode"],
            "proposed",
        )
        self.assertEqual(
            create_plan_args["chromie_intent"]["execution_semantics"],
            "proposal_from_chromie",
        )
        self.assertTrue(
            create_plan_args["chromie_intent"]["requires_runtime_validation"]
        )
        self.assertEqual(
            create_plan_args["chromie_intent"]["interaction_id"],
            execution.interaction_id,
        )
        self.assertEqual(create_plan_args["chromie_intent"]["request_id"], "nod-1")
        self.assertEqual(
            create_plan_args["chromie_intent"]["skill_id"],
            "soridormi.nod_yes",
        )
        self.assertEqual(
            create_plan_args["chromie_intent"]["upstream_skill_id"],
            "nod_yes",
        )
        self.assertEqual(
            create_plan_args["chromie_intent"]["source_component"],
            "interaction_response",
        )
        self.assertEqual(
            invoker.calls[1][0:2],
            (
                "soridormi.safety.monitor_motion",
                {"during_node_id": "nod-1"},
            ),
        )
        self.assertEqual(
            invoker.calls[2][0:2],
            ("soridormi.skill.execute_plan", {"plan_id": "plan-1"}),
        )
        self.assertTrue(invoker.calls[2][2].confirmed)
        self.assertTrue(invoker.calls[2][2].safety_monitor_active)

    async def test_named_skill_propagates_route_trace_metadata_to_plan(self) -> None:
        invoker = _RecordingInvoker()
        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                interaction_id="interaction-route-trace",
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 1, "amplitude": "small"},
                        "metadata": {
                            "source": "agent.capability",
                            "route_source": "llm",
                            "route_stage": "quick_intent",
                            "route_task_source_stage": "capability_catalog",
                            "route_confidence": 0.92,
                            "router_source": "router.v2",
                        },
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids={"nod-1"},
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "completed")
        chromie_intent = invoker.calls[0][1]["chromie_intent"]
        self.assertEqual(chromie_intent["source_component"], "agent.capability")
        self.assertEqual(chromie_intent["route_source"], "llm")
        self.assertEqual(chromie_intent["route_stage"], "quick_intent")
        self.assertEqual(
            chromie_intent["route_task_source_stage"],
            "capability_catalog",
        )
        self.assertEqual(chromie_intent["route_confidence"], 0.92)
        self.assertEqual(chromie_intent["router_source"], "router.v2")


    async def test_named_skill_propagates_live_perception_contract(self) -> None:
        invoker = _RecordingInvoker()
        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                interaction_id="interaction-live-perception",
                skills=[
                    {
                        "request_id": "inspect-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 1, "amplitude": "small"},
                        "metadata": {
                            "requires_live_perception": True,
                            "perception_dependency": "locate_target",
                            "perception_reason": "Need Soridormi to locate the target before motion.",
                        },
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids={"inspect-1"},
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "completed")
        chromie_intent = invoker.calls[0][1]["chromie_intent"]
        self.assertTrue(chromie_intent["requires_live_perception"])
        self.assertEqual(chromie_intent["perception_dependency"], "locate_object")
        self.assertEqual(chromie_intent["physical_state_source"], "soridormi_runtime")
        self.assertTrue(
            chromie_intent["chromie_must_not_provide_physical_coordinates"]
        )
        self.assertTrue(chromie_intent["soridormi_owns_pose_estimation"])

    async def test_catalog_preserves_unavailable_skill_reason(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "wave_hand",
                    "available": False,
                    "unavailable_reason": "not executable",
                    "parameters_schema": {"type": "object"},
                }
            ]
        )
        runtime = SkillRuntime(registry)
        runtime.register_provider(SoridormiMcpSkillProvider(_RecordingInvoker()))

        with self.assertRaisesRegex(ValueError, "not executable"):
            await runtime.execute(
                InteractionResponse(
                    skills=[{"skill_id": "soridormi.wave_hand"}]
                ),
                authorization=RuntimeAuthorization(
                    safety_monitor_active=True,
                ),
            )

    async def test_execute_requires_explicit_completed_true(self) -> None:
        invoker = _RecordingInvoker(
            overrides={
                "soridormi.skill.execute_plan": ToolCallOutcome.success(
                    {"skill_id": "nod_yes"}
                )
            }
        )

        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 1},
                    }
                ]
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids={"nod-1"},
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[0].reason_code, "execution_incomplete")

    async def test_execute_rejects_mismatched_skill_identity(self) -> None:
        invoker = _RecordingInvoker(
            overrides={
                "soridormi.skill.execute_plan": ToolCallOutcome.success(
                    {"completed": True, "skill_id": "wave_hand"}
                )
            }
        )

        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 1},
                    }
                ]
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids={"nod-1"},
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(
            execution.results[0].reason_code,
            "execution_skill_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
