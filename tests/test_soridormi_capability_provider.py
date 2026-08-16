from __future__ import annotations

import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.capability_runtime import (
    RuntimeAuthorization,
    CapabilityExecutionContext,
    CapabilityRegistry,
    CapabilityRuntime,
)
from orchestrator.runtime.soridormi_capability_provider import (
    SoridormiCapabilityProvider,
    import_soridormi_capability_catalog,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    CapabilityRequest,
    CapabilityTrace,
)


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


class SoridormiCapabilityProviderTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, invoker: _RecordingInvoker) -> CapabilityRuntime:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
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
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))
        return runtime

    def test_imported_embodied_skill_has_host_owned_completion_evidence_policy(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Nod the robot head.",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            ]
        )

        policy = registry.get("soridormi.nod_yes").completion_evidence_policy
        self.assertIsNotNone(policy)
        assert policy is not None
        requirements = policy.requirement_groups[0].requirements
        self.assertEqual(
            [item.source for item in requirements],
            ["execution_observation", "provider_postcondition"],
        )
        self.assertEqual(
            requirements[1].condition,
            "post_execution_robot_status",
        )
        self.assertEqual(
            requirements[1].field_assertions,
            {"safe_idle": True, "active_task_present": False},
        )

    async def test_named_skill_uses_opaque_plan_execute_contract(self) -> None:
        invoker = _RecordingInvoker()
        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
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
        self.assertEqual(
            execution.results[0].output,
            {
                "completed": True,
                "capability_id": "soridormi.nod_yes",
                "mode": "",
                "no_motion": False,
                "recommendation_only": False,
                "summary": "completed nod_yes",
            },
        )
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
            create_plan_args["chromie_intent"]["capability_id"],
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

    async def test_reviewed_low_risk_social_attention_uses_trusted_preflight(self) -> None:
        invoker = _RecordingInvoker(
            overrides={
                "soridormi.skill.create_plan": ToolCallOutcome.success(
                    {
                        "plan_id": "social-plan",
                        "skill_id": "blink_eyes",
                        "requires_confirmation": False,
                    }
                ),
                "soridormi.skill.execute_plan": ToolCallOutcome.success(
                    {
                        "completed": True,
                        "skill_id": "blink_eyes",
                        "summary": "completed blink_eyes",
                    }
                ),
            }
        )
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "blink_eyes",
                    "description": "Blink as subtle social expression.",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 3,
                            }
                        },
                        "additionalProperties": False,
                    },
                    "requires_confirmation": False,
                    "safety_class": "low_risk_action",
                    "effects": ["social_expression"],
                    "interruptible": True,
                }
            ]
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))

        execution = await runtime.execute(
            InteractionResponse(
                interaction_id="social-interaction",
                capabilities=[
                    {
                        "request_id": "social-blink",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "parallel",
                        "requires_confirmation": False,
                        "metadata": {
                            "source": "social_attention_plan",
                            "auxiliary_social_attention": True,
                        },
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids=set(),
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "completed")
        execute_context = next(
            context
            for tool, _, context in invoker.calls
            if tool == "soridormi.skill.execute_plan"
        )
        self.assertIsNotNone(execute_context)
        self.assertFalse(execute_context.confirmed)
        self.assertTrue(execute_context.trusted_preflight_authorized)
        self.assertTrue(execute_context.safety_monitor_active)

    async def test_social_preflight_does_not_override_provider_confirmation(self) -> None:
        invoker = _RecordingInvoker()
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "blink_eyes",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "requires_confirmation": False,
                    "safety_class": "low_risk_action",
                    "effects": ["social_expression"],
                }
            ]
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))

        await runtime.execute(
            InteractionResponse(
                interaction_id="provider-confirmation",
                capabilities=[
                    {
                        "request_id": "provider-confirmed-blink",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {},
                        "requires_confirmation": False,
                        "metadata": {
                            "source": "social_attention_plan",
                            "auxiliary_social_attention": True,
                        },
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids=set(),
                safety_monitor_active=True,
            ),
        )

        execute_context = next(
            context
            for tool, _, context in invoker.calls
            if tool == "soridormi.skill.execute_plan"
        )
        self.assertIsNotNone(execute_context)
        self.assertFalse(execute_context.confirmed)
        self.assertFalse(execute_context.trusted_preflight_authorized)

    async def test_untrusted_noncanonical_action_cannot_claim_trusted_preflight(self) -> None:
        invoker = _RecordingInvoker(
            overrides={
                "soridormi.skill.create_plan": ToolCallOutcome.success(
                    {
                        "plan_id": "ordinary-plan",
                        "skill_id": "blink_eyes",
                        "requires_confirmation": False,
                    }
                )
            }
        )
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "blink_eyes",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "requires_confirmation": False,
                    "safety_class": "low_risk_action",
                    "effects": ["social_expression"],
                }
            ]
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))

        await runtime.execute(
            InteractionResponse(
                interaction_id="ordinary-interaction",
                capabilities=[
                    {
                        "request_id": "ordinary-blink",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {},
                        "requires_confirmation": False,
                        "metadata": {"source": "canonical_plan"},
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids=set(),
                safety_monitor_active=True,
            ),
        )

        execute_context = next(
            context
            for tool, _, context in invoker.calls
            if tool == "soridormi.skill.execute_plan"
        )
        self.assertIsNotNone(execute_context)
        self.assertFalse(execute_context.confirmed)
        self.assertFalse(execute_context.trusted_preflight_authorized)


    async def test_goal_grounded_named_motion_uses_trusted_preflight(self) -> None:
        invoker = _RecordingInvoker(
            overrides={
                "soridormi.skill.create_plan": ToolCallOutcome.success(
                    {
                        "plan_id": "walk-plan",
                        "skill_id": "walk_forward",
                        "requires_confirmation": False,
                    }
                ),
                "soridormi.skill.execute_plan": ToolCallOutcome.success(
                    {
                        "completed": True,
                        "skill_id": "walk_forward",
                        "summary": "completed walk_forward",
                    }
                ),
            }
        )
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "walk_forward",
                    "description": "Walk forward for a bounded duration.",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "duration_s": {
                                "type": "number",
                                "minimum": 0.1,
                                "maximum": 20.0,
                            }
                        },
                        "required": ["duration_s"],
                        "additionalProperties": False,
                    },
                    "requires_confirmation": False,
                    "safety_class": "physical_motion",
                    "effects": ["physical_motion"],
                    "interruptible": True,
                }
            ]
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))

        execution = await runtime.execute(
            InteractionResponse(
                interaction_id="goal-grounded-motion",
                capabilities=[
                    {
                        "request_id": "walk-request",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15.0},
                        "requires_confirmation": False,
                        "metadata": {
                            "source": "goal_driven_canonical_plan",
                            "canonical_plan_id": "plan-walk",
                            "step_id": "step-walk",
                            "source_goal_ids": ["goal-walk"],
                        },
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids=set(),
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "completed")
        execute_context = next(
            context
            for tool, _, context in invoker.calls
            if tool == "soridormi.skill.execute_plan"
        )
        self.assertIsNotNone(execute_context)
        self.assertFalse(execute_context.confirmed)
        self.assertTrue(execute_context.trusted_preflight_authorized)
        self.assertTrue(execute_context.safety_monitor_active)

    async def test_goal_grounded_preflight_does_not_override_provider_confirmation(self) -> None:
        invoker = _RecordingInvoker()
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "walk_forward",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "requires_confirmation": False,
                    "safety_class": "physical_motion",
                    "effects": ["physical_motion"],
                }
            ]
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))

        await runtime.execute(
            InteractionResponse(
                interaction_id="provider-confirmed-motion",
                capabilities=[
                    {
                        "request_id": "walk-request",
                        "capability_id": "soridormi.walk_forward",
                        "args": {},
                        "requires_confirmation": False,
                        "metadata": {
                            "source": "goal_driven_canonical_plan",
                            "canonical_plan_id": "plan-walk",
                            "step_id": "step-walk",
                            "source_goal_ids": ["goal-walk"],
                        },
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids=set(),
                safety_monitor_active=True,
            ),
        )

        execute_context = next(
            context
            for tool, _, context in invoker.calls
            if tool == "soridormi.skill.execute_plan"
        )
        self.assertIsNotNone(execute_context)
        self.assertFalse(execute_context.confirmed)
        self.assertFalse(execute_context.trusted_preflight_authorized)

    async def test_named_skill_propagates_route_trace_metadata_to_plan(self) -> None:
        invoker = _RecordingInvoker()
        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                interaction_id="interaction-route-trace",
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
                        "args": {"count": 1, "amplitude": "small"},
                        "metadata": {
                            "source": "agent.capability",
                            "route_source": "llm",
                            "route_stage": "quick_intent",
                            "route_task_source_stage": "capability_catalog",
                            "route_confidence": 0.92,
                            "goal_interpretation_source": "goal_interpreter.v1",
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
        self.assertEqual(chromie_intent["goal_interpretation_source"], "goal_interpreter.v1")


    async def test_named_skill_propagates_live_perception_contract(self) -> None:
        invoker = _RecordingInvoker()
        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                interaction_id="interaction-live-perception",
                capabilities=[
                    {
                        "request_id": "inspect-1",
                        "capability_id": "soridormi.nod_yes",
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
        self.assertEqual(chromie_intent["perception_dependency"], "locate_target")
        self.assertEqual(chromie_intent["physical_state_source"], "soridormi_runtime")
        self.assertTrue(
            chromie_intent["chromie_must_not_provide_physical_coordinates"]
        )
        self.assertTrue(chromie_intent["soridormi_owns_pose_estimation"])

    async def test_catalog_preserves_unavailable_capability_reason(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "wave_hand",
                    "available": False,
                    "unavailable_reason": "not executable",
                    "parameters_schema": {"type": "object"},
                }
            ]
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(_RecordingInvoker()))

        with self.assertRaisesRegex(ValueError, "not executable"):
            await runtime.execute(
                InteractionResponse(
                    capabilities=[{"capability_id": "soridormi.wave_hand"}]
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
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
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
        self.assertEqual(execution.results[0].output["capability_id"], "soridormi.nod_yes")
        self.assertNotIn("skill_id", execution.results[0].output)

    async def test_execute_rejects_mismatched_provider_identity(self) -> None:
        invoker = _RecordingInvoker(
            overrides={
                "soridormi.skill.execute_plan": ToolCallOutcome.success(
                    {"completed": True, "skill_id": "wave_hand"}
                )
            }
        )

        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
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
            "execution_capability_mismatch",
        )
        self.assertEqual(execution.results[0].output["capability_id"], "soridormi.nod_yes")
        self.assertNotIn("skill_id", execution.results[0].output)

    async def test_cancel_requires_explicit_cancelled_true(self) -> None:
        request = CapabilityRequest(
            request_id="nod-cancel",
            capability_id="soridormi.nod_yes",
        )
        context = CapabilityExecutionContext(
            interaction_id="interaction-cancel",
            trace=CapabilityTrace(
                interaction_id="interaction-cancel",
                request_id=request.request_id,
                capability_id=request.capability_id,
                provider_id="soridormi.mcp",
            ),
        )
        definition = self._runtime(_RecordingInvoker()).registry.get(
            request.capability_id
        )

        for output in ({"cancelled": False}, {}):
            with self.subTest(output=output):
                provider = SoridormiCapabilityProvider(
                    _RecordingInvoker(
                        overrides={
                            "soridormi.motion.cancel": (
                                ToolCallOutcome.success(output)
                            )
                        }
                    )
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "did not confirm cancelled=true",
                ):
                    await provider.cancel(
                        request,
                        definition,
                        context,
                    )


    def test_resource_capability_rejects_completed_without_full_delivery_evidence(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "acquire_and_deliver_resource",
                    "description": "Acquire and deliver a physical object.",
                    "available": True,
                    "parameters_schema": {"type": "object"},
                    "metadata": {
                        "semantic_scope": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kinds": ["physical_object"],
                        }
                    },
                }
            ]
        )
        provider = SoridormiCapabilityProvider(_RecordingInvoker())
        request = CapabilityRequest(
            request_id="resource-incomplete",
            capability_id="soridormi.acquire_and_deliver_resource",
        )
        definition = registry.get(request.capability_id)

        missing = provider._resource_completion_failure(
            request,
            definition,
            {"completed": True, "skill_id": "acquire_and_deliver_resource"},
        )
        self.assertIsNotNone(missing)
        assert missing is not None
        self.assertEqual(missing.reason_code, "resource_outcome_missing")
        self.assertNotIn("skill_id", missing.output)
        self.assertEqual(
            missing.output["capability_id"],
            "soridormi.acquire_and_deliver_resource",
        )

        incomplete = provider._resource_completion_failure(
            request,
            definition,
            {
                "completed": True,
                "skill_id": "acquire_and_deliver_resource",
                "resource_outcome": {
                    "resource_acquired": True,
                    "resource_delivered": False,
                },
            },
        )
        self.assertIsNotNone(incomplete)
        assert incomplete is not None
        self.assertEqual(incomplete.reason_code, "resource_completion_incomplete")
        self.assertNotIn("skill_id", incomplete.output)
        self.assertEqual(
            incomplete.output["capability_id"],
            "soridormi.acquire_and_deliver_resource",
        )

    def test_granular_resource_capability_uses_its_own_completion_contract(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "acquire_resource",
                    "description": "Acquire a physical object and retain it.",
                    "available": True,
                    "parameters_schema": {"type": "object"},
                    "metadata": {
                        "semantic_scope": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kinds": ["physical_object"],
                        },
                        "resource_contract": {
                            "result_field": "resource_outcome",
                            "plan_requires": [],
                            "plan_provides": ["resource_acquired"],
                            "completion_requires": ["resource_acquired"],
                        },
                    },
                }
            ]
        )
        provider = SoridormiCapabilityProvider(_RecordingInvoker())
        request = CapabilityRequest(
            request_id="resource-acquire",
            capability_id="soridormi.acquire_resource",
        )
        definition = registry.get(request.capability_id)

        failure = provider._resource_completion_failure(
            request,
            definition,
            {
                "completed": True,
                "skill_id": "acquire_resource",
                "resource_outcome": {
                    "resource_acquired": True,
                    "resource_delivered": False,
                },
            },
        )
        self.assertIsNone(failure)

    async def test_fetch_and_deliver_preserves_scope_and_complete_resource_evidence(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "acquire_and_deliver_resource",
                    "description": (
                        "Acquire a described physical object and deliver it to the "
                        "intended recipient."
                    ),
                    "available": True,
                    "requires_confirmation": True,
                    "effects": [
                        "physical_motion",
                        "object_manipulation",
                        "resource_delivery",
                    ],
                    "safety_class": "physical_motion",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "resource": {"type": "object"},
                            "source": {"type": "object"},
                            "recipient": {"type": "object"},
                        },
                        "required": ["resource", "source", "recipient"],
                        "additionalProperties": False,
                    },
                    "metadata": {
                        "semantic_scope": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kinds": ["physical_object"],
                            "delivery_modes": ["physical_handover"],
                        },
                        "resource_contract": {
                            "result_field": "resource_outcome",
                        },
                    },
                }
            ]
        )
        definition = registry.get("soridormi.acquire_and_deliver_resource")
        self.assertEqual(
            definition.metadata["semantic_scope"]["responsibility_type"],
            "acquire_and_deliver_resource",
        )
        self.assertEqual(
            definition.metadata["resource_contract"]["result_field"],
            "resource_outcome",
        )

        invoker = _RecordingInvoker(
            overrides={
                "soridormi.skill.execute_plan": ToolCallOutcome.success(
                    {
                        "completed": True,
                        "skill_id": "acquire_and_deliver_resource",
                        "summary": "The requested bottle was delivered.",
                        "resource_outcome": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kind": "physical_object",
                            "resource_description": "a bottle of water",
                            "resource_acquired": True,
                            "resource_delivered": True,
                            "recipient_description": "requester",
                            "evidence_summary": "Acquisition and delivery state verified.",
                        },
                    }
                )
            }
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))
        execution = await runtime.execute(
            InteractionResponse(
                interaction_id="fetch-resource",
                capabilities=[
                    {
                        "request_id": "fetch-resource-1",
                        "capability_id": "soridormi.acquire_and_deliver_resource",
                        "args": {
                            "resource": {
                                "kind": "physical_object",
                                "description": "a bottle of water",
                            },
                            "source": {
                                "status": "known",
                                "description": "100 meters ahead",
                            },
                            "recipient": {"description": "requester"},
                        },
                        "requires_confirmation": True,
                    }
                ],
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids={"fetch-resource-1"},
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "completed")
        outcome = execution.results[0].output["resource_outcome"]
        self.assertTrue(outcome["resource_acquired"])
        self.assertTrue(outcome["resource_delivered"])


if __name__ == "__main__":
    unittest.main()
