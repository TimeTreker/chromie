from __future__ import annotations

import asyncio
import time
import unittest

from shared.chromie_contracts.agent import AgentResult, SpeechItem
from shared.chromie_contracts.action import ActionCommand
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.reflex import CancellationDirective

from orchestrator.runtime.skill_adapters import AgentResultInteractionAdapter
from orchestrator.runtime.skill_runtime import (
    LocalSpeechSkillProvider,
    MockSkillProvider,
    RuntimeAuthorization,
    SkillDefinition,
    SkillRegistry,
    SkillRuntime,
    local_speech_definition,
)


def _body_definition(
    *,
    skill_id: str = "soridormi.nod_yes",
    provider_id: str = "mock.body",
    timeout_ms: int = 1000,
    requires_confirmation: bool = False,
    interruptible: bool = True,
    can_run_parallel: bool = True,
    exclusive_group: str | None = "soridormi.robot_motion",
) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        version="1.0.0",
        provider_id=provider_id,
        input_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 3},
                "amplitude": {"type": "string", "enum": ["small", "medium"]},
            },
            "additionalProperties": False,
        },
        timeout_ms=timeout_ms,
        requires_confirmation=requires_confirmation,
        interruptible=interruptible,
        can_run_parallel=can_run_parallel,
        exclusive_group=exclusive_group,
        cancellation_domains=("embodied_motion",),
        metadata={
            "effects": ["physical_motion"],
            "safety_class": "physical_motion",
            "cancellation_granularity": "request",
        },
    )


def _tool_definition(
    *,
    skill_id: str,
    provider_id: str = "mock.tool",
    interruptible: bool = True,
) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        version="1.0.0",
        provider_id=provider_id,
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"args": {"type": "object"}},
            "additionalProperties": True,
        },
        interruptible=interruptible,
        can_run_parallel=True,
    )


class SkillRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_rejects_execution_id_collision_after_model_copy(
        self,
    ) -> None:
        response = InteractionResponse(
            interaction_id="collision-turn",
            speech=[{"id": "same-id", "text": "Hello."}],
            skills=[
                {
                    "request_id": "different-id",
                    "skill_id": "chromie.test",
                }
            ],
        )
        unsafe = response.model_copy(
            update={
                "skills": [
                    response.skills[0].model_copy(
                        update={"request_id": "same-id"}
                    )
                ]
            }
        )
        runtime = SkillRuntime(SkillRegistry())

        with self.assertRaisesRegex(ValueError, "must be unique"):
            await runtime.execute(unsafe)

    async def test_soridormi_import_keeps_physical_confirmation_when_host_requires_it(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Visible head nod.",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "available": True,
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "requires_confirmation": False,
                }
            ],
            requires_confirmation=True,
        )

        self.assertTrue(registry.get("soridormi.nod_yes").requires_confirmation)

    async def test_soridormi_import_allows_declared_sim_exemption_when_host_allows_it(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Visible head nod.",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "available": True,
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "requires_confirmation": False,
                }
            ],
            requires_confirmation=False,
        )

        self.assertFalse(registry.get("soridormi.nod_yes").requires_confirmation)

    async def test_soridormi_import_upserts_catalog_entries(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Old nod.",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "available": True,
                    "timeout_s": 1.0,
                }
            ],
            requires_confirmation=False,
        )
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Updated nod.",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {"count": {"type": "integer"}},
                    },
                    "available": False,
                    "unavailable_reason": "calibrating",
                    "timeout_s": 2.0,
                    "can_run_parallel": True,
                    "exclusive_group": "soridormi.face_expression",
                    "resource_claims": ["eyelids"],
                    "execution_constraints": {"requires_stationary_head": False},
                }
            ],
            requires_confirmation=False,
        )

        definition = registry.get("soridormi.nod_yes")
        self.assertEqual(definition.description, "Updated nod.")
        self.assertFalse(definition.available)
        self.assertEqual(definition.unavailable_reason, "calibrating")
        self.assertEqual(definition.timeout_ms, 2000)
        self.assertIn("count", definition.input_schema["properties"])
        self.assertTrue(definition.can_run_parallel)
        self.assertEqual(definition.exclusive_group, "soridormi.face_expression")
        self.assertEqual(definition.metadata["resource_claims"], ["eyelids"])
        self.assertEqual(
            definition.metadata["execution_constraints"],
            {"requires_stationary_head": False},
        )
        self.assertEqual(
            definition.metadata["effects"],
            ["physical_motion"],
        )
        self.assertEqual(
            definition.metadata["safety_class"],
            "physical_motion",
        )
        self.assertEqual(
            definition.cancellation_domains,
            ("embodied_motion",),
        )

    async def test_soridormi_import_marks_absent_live_skills_unavailable(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {"skill_id": "nod_yes", "available": True},
                {"skill_id": "wave_hand", "available": True},
            ],
            requires_confirmation=False,
        )
        registry.import_soridormi_catalog(
            [{"skill_id": "wave_hand", "available": True}],
            requires_confirmation=False,
        )

        removed = registry.get("soridormi.nod_yes")
        self.assertFalse(removed.available)
        self.assertEqual(
            removed.unavailable_reason,
            "not present in latest Soridormi catalog",
        )
        self.assertTrue(removed.metadata["catalog_absent"])
        self.assertTrue(registry.get("soridormi.wave_hand").available)

    async def test_speech_only_request_completes(self) -> None:
        spoken: list[str] = []
        registry = SkillRegistry()
        registry.register(local_speech_definition())
        runtime = SkillRuntime(registry)
        runtime.register_provider(
            LocalSpeechSkillProvider(
                lambda args: spoken.append(args["text"]) or {"spoken": True}
            )
        )

        execution = await runtime.execute(
            InteractionResponse(speech=[{"text": "Hello."}])
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(spoken, ["Hello."])
        self.assertEqual(execution.results[0].skill_id, "chromie.speak")

    async def test_failed_playback_start_barrier_prevents_following_body_effect(self) -> None:
        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        body = MockSkillProvider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(
            LocalSpeechSkillProvider(
                lambda _args: {
                    "scheduled": True,
                    "playback_started": False,
                }
            )
        )
        runtime.register_provider(body)

        execution = await runtime.execute(
            InteractionResponse(
                speech=[
                    {
                        "text": "I heard you.",
                        "timing": "immediate",
                        "metadata": {"wait_for_playback_start": True},
                    }
                ],
                skills=[
                    {
                        "request_id": "nod-after-cue",
                        "skill_id": "soridormi.nod_yes",
                        "timing": "sequential",
                    }
                ],
            )
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[0].reason_code, "playback_not_started")
        self.assertEqual(body.calls, [])

    async def test_started_playback_barrier_releases_following_body_effect(self) -> None:
        events: list[str] = []

        async def speak(_args: dict[str, object]) -> dict[str, object]:
            events.append("playback_start")
            return {"scheduled": True, "playback_started": True}

        class OrderedBodyProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                events.append("body_start")
                return await super().execute(request, definition, context)

        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        body = OrderedBodyProvider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(LocalSpeechSkillProvider(speak))
        runtime.register_provider(body)

        execution = await runtime.execute(
            InteractionResponse(
                speech=[
                    {
                        "text": "I heard you.",
                        "timing": "immediate",
                        "metadata": {"wait_for_playback_start": True},
                    }
                ],
                skills=[
                    {
                        "request_id": "nod-after-cue",
                        "skill_id": "soridormi.nod_yes",
                        "timing": "parallel",
                    }
                ],
            )
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(events, ["playback_start", "body_start"])

    async def test_action_only_request_reaches_mock_provider(self) -> None:
        registry = SkillRegistry()
        registry.register(_body_definition())
        provider = MockSkillProvider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)

        execution = await runtime.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "skill_version": "1.0.0",
                        "args": {"count": 2, "amplitude": "small"},
                    }
                ]
            )
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(provider.calls[0].request_id, "nod-1")

    async def test_parallel_speech_and_body_overlap(self) -> None:
        events: list[tuple[str, float]] = []

        async def speak(args: dict[str, object]) -> dict[str, object]:
            events.append(("speech_start", time.monotonic()))
            await asyncio.sleep(0.05)
            events.append(("speech_end", time.monotonic()))
            return {"spoken": True}

        class TimedProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                events.append(("body_start", time.monotonic()))
                result = await super().execute(request, definition, context)
                events.append(("body_end", time.monotonic()))
                return result

        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        runtime = SkillRuntime(registry)
        runtime.register_provider(LocalSpeechSkillProvider(speak))
        runtime.register_provider(TimedProvider("mock.body", delay_s=0.05))

        await runtime.execute(
            InteractionResponse(
                speech=[{"text": "Hello.", "timing": "parallel"}],
                skills=[
                    {
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                        "timing": "parallel",
                    }
                ],
            )
        )

        timestamps = dict(events)
        self.assertLess(timestamps["body_start"], timestamps["speech_end"])
        self.assertLess(timestamps["speech_start"], timestamps["body_end"])

    async def test_parallel_batch_is_bounded_and_results_stay_ordered(self) -> None:
        active = 0
        peak = 0

        class VariableProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(float(request.args["delay_s"]))
                active -= 1
                return await super().execute(request, definition, context)

        registry = SkillRegistry()
        for index in range(3):
            registry.register(
                SkillDefinition(
                    skill_id=f"test.skill_{index}",
                    provider_id="mock.body",
                    input_schema={
                        "type": "object",
                        "properties": {"delay_s": {"type": "number"}},
                        "required": ["delay_s"],
                        "additionalProperties": False,
                    },
                    exclusive_group=None,
                )
            )
        provider = VariableProvider("mock.body")
        runtime = SkillRuntime(registry, max_concurrency=2)

        runtime.register_provider(provider)
        execution = await runtime.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": f"request-{index}",
                        "skill_id": f"test.skill_{index}",
                        "args": {"delay_s": delay},
                        "timing": "parallel",
                    }
                    for index, delay in enumerate((0.04, 0.01, 0.02))
                ]
            )
        )

        self.assertEqual(peak, 2)
        self.assertEqual(
            [result.request_id for result in execution.results],
            ["request-0", "request-1", "request-2"],
        )

    async def test_exclusive_group_spans_concurrent_interactions(self) -> None:
        active = 0
        peak = 0

        class ExclusiveProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.02)
                active -= 1
                return await super().execute(request, definition, context)

        registry = SkillRegistry()
        registry.register(_body_definition())
        provider = ExclusiveProvider("mock.body")
        runtime = SkillRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)

        await asyncio.gather(
            runtime.execute(
                InteractionResponse(
                    interaction_id="interaction-a",
                    skills=[
                        {
                            "request_id": "same-request",
                            "skill_id": "soridormi.nod_yes",
                        }
                    ],
                )
            ),
            runtime.execute(
                InteractionResponse(
                    interaction_id="interaction-b",
                    skills=[
                        {
                            "request_id": "same-request",
                            "skill_id": "soridormi.nod_yes",
                        }
                    ],
                )
            ),
        )

        self.assertEqual(peak, 1)

    async def test_duplicate_request_ids_do_not_collide_across_interactions(self) -> None:
        cancelled_interactions: list[str] = []

        class CollisionProvider(MockSkillProvider):
            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                cancelled_interactions.append(context.interaction_id)
                raise RuntimeError(
                    f"cancel failed for {context.interaction_id}"
                )

        provider = CollisionProvider("mock.body", delay_s=5)
        registry = SkillRegistry()
        registry.register(
            _body_definition(
                exclusive_group=None,
            )
        )
        runtime = SkillRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)

        executions = [
            asyncio.create_task(
                runtime.execute(
                    InteractionResponse(
                        interaction_id=interaction_id,
                        skills=[
                            {
                                "request_id": "shared-request",
                                "skill_id": "soridormi.nod_yes",
                            }
                        ],
                    )
                )
            )
            for interaction_id in ("interaction-a", "interaction-b")
        ]
        while len(provider.calls) < 2:
            await asyncio.sleep(0)

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-qualified-duplicate-ids",
                requested_scope="global_emergency",
            )
        )
        results = await asyncio.gather(*executions)

        self.assertEqual(set(cancelled_interactions), {"interaction-a", "interaction-b"})
        self.assertEqual([result.status for result in results], ["failed", "failed"])
        self.assertEqual(
            {
                (
                    binding.interaction_id,
                    binding.request_id,
                )
                for binding in receipt.selected_request_bindings
            },
            {
                ("interaction-a", "shared-request"),
                ("interaction-b", "shared-request"),
            },
        )
        self.assertEqual(
            len(receipt.cancel_requested_request_bindings),
            2,
        )
        self.assertEqual(
            {
                (
                    failure.interaction_id,
                    failure.request_id,
                    failure.error,
                )
                for failure in receipt.provider_cancel_failure_evidence
            },
            {
                (
                    "interaction-a",
                    "shared-request",
                    "cancel failed for interaction-a",
                ),
                (
                    "interaction-b",
                    "shared-request",
                    "cancel failed for interaction-b",
                ),
            },
        )

    async def test_cancelling_one_execution_does_not_cancel_another_interaction(self) -> None:
        release_keep = asyncio.Event()

        class IsolatedProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                if context.interaction_id == "keep":
                    await release_keep.wait()
                else:
                    await asyncio.Event().wait()
                return await super().execute(request, definition, context)

        provider = IsolatedProvider("mock.body")
        registry = SkillRegistry()
        registry.register(_body_definition(exclusive_group=None))
        runtime = SkillRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)

        cancel_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="cancel",
                    skills=[
                        {
                            "request_id": "cancel-request",
                            "skill_id": "soridormi.nod_yes",
                        }
                    ],
                )
            )
        )
        keep_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="keep",
                    skills=[
                        {
                            "request_id": "keep-request",
                            "skill_id": "soridormi.nod_yes",
                        }
                    ],
                )
            )
        )
        while len(provider.calls) < 2:
            await asyncio.sleep(0)

        cancel_task.cancel()
        cancelled = await cancel_task
        status = runtime.scheduler_status()
        release_keep.set()
        kept = await keep_task

        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in cancelled.results
            ],
            [("cancel-request", "cancelled", "cancelled")],
        )
        self.assertEqual(
            [
                (trace.request_id, trace.status)
                for trace in cancelled.traces
            ],
            [("cancel-request", "cancelled")],
        )
        self.assertIn("keep", status.active_interaction_ids)
        self.assertNotIn("cancel", status.active_interaction_ids)
        self.assertEqual(kept.status, "completed")

    async def test_output_only_cancels_speech_but_keeps_parallel_motion(self) -> None:
        speech_started = asyncio.Event()
        body_started = asyncio.Event()
        release_body = asyncio.Event()

        async def speak(_args: dict[str, object]) -> dict[str, object]:
            speech_started.set()
            await asyncio.Event().wait()
            return {"spoken": True}

        class BodyProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                body_started.set()
                await release_body.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        speech_provider = LocalSpeechSkillProvider(speak)
        body_provider = BodyProvider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)
        interaction_id = "scoped-output"
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id=interaction_id,
                    speech=[
                        {
                            "id": "speech-output",
                            "text": "Still speaking.",
                            "timing": "parallel",
                        }
                    ],
                    skills=[
                        {
                            "request_id": "motion-keep",
                            "skill_id": "soridormi.nod_yes",
                            "timing": "parallel",
                        }
                    ],
                )
            )
        )
        await asyncio.gather(
            speech_started.wait(),
            body_started.wait(),
        )

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-output",
                requested_scope="output_only",
                foreground_interaction_id=interaction_id,
            )
        )
        release_body.set()
        execution = await execution_task

        self.assertEqual(receipt.selected_request_ids, ("speech-output",))
        self.assertEqual(
            receipt.cancel_requested_request_ids,
            ("speech-output",),
        )
        self.assertEqual(body_provider.cancelled_request_ids, [])
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                (
                    "speech-output",
                    "cancelled",
                    "cancelled_output_only",
                ),
                ("motion-keep", "completed", None),
            ],
        )

    async def test_motion_scope_cancels_motion_but_keeps_parallel_tool(self) -> None:
        motion_started = asyncio.Event()
        tool_started = asyncio.Event()
        release_tool = asyncio.Event()

        class MotionProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                motion_started.set()
                await asyncio.Event().wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        class ToolProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                tool_started.set()
                await release_tool.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(_body_definition())
        registry.register(_tool_definition(skill_id="chromie.weather"))
        motion_provider = MotionProvider("mock.body")
        tool_provider = ToolProvider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(motion_provider)
        runtime.register_provider(tool_provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="scoped-motion",
                    skills=[
                        {
                            "request_id": "motion-cancel",
                            "skill_id": "soridormi.nod_yes",
                            "timing": "parallel",
                        },
                        {
                            "request_id": "weather-keep",
                            "skill_id": "chromie.weather",
                            "timing": "parallel",
                        },
                    ],
                )
            )
        )
        await asyncio.gather(motion_started.wait(), tool_started.wait())

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-motion",
                requested_scope="embodied_motion",
            )
        )
        release_tool.set()
        execution = await execution_task

        self.assertEqual(receipt.selected_request_ids, ("motion-cancel",))
        self.assertEqual(tool_provider.cancelled_request_ids, [])
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                (
                    "motion-cancel",
                    "cancelled",
                    "cancelled_embodied_motion",
                ),
                ("weather-keep", "completed", None),
            ],
        )

    async def test_specific_goal_cancels_queued_request_before_start(self) -> None:
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        class SequentialProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "keep-first":
                    first_started.set()
                    await release_first.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.keep",
                provider_id="mock.tool",
            )
        )
        registry.register(
            _tool_definition(
                skill_id="chromie.cancel",
                provider_id="mock.tool",
            )
        )
        provider = SequentialProvider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        plan_metadata = {
            "canonical_plan_id": "plan-scoped",
            "canonical_plan_fingerprint": "fingerprint-scoped",
        }
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="specific-queued",
                    skills=[
                        {
                            "request_id": "keep-first",
                            "skill_id": "chromie.keep",
                            "timing": "sequential",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-keep"],
                            },
                        },
                        {
                            "request_id": "cancel-before-start",
                            "skill_id": "chromie.cancel",
                            "timing": "sequential",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-cancel"],
                            },
                        },
                    ],
                )
            )
        )
        await first_started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-specific",
                requested_scope="specific_goal",
                foreground_interaction_id="specific-queued",
                target_goal_ids=("goal-cancel",),
                expected_plan_id="plan-scoped",
                expected_plan_fingerprint="fingerprint-scoped",
            )
        )
        release_first.set()
        execution = await execution_task

        self.assertEqual(
            receipt.queued_request_ids,
            ("cancel-before-start",),
        )
        self.assertEqual(
            [request.request_id for request in provider.calls],
            ["keep-first"],
        )
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                ("keep-first", "completed", None),
                (
                    "cancel-before-start",
                    "cancelled",
                    "cancelled_before_start",
                ),
            ],
        )

    async def test_specific_goal_rule_survives_open_preflight_window(
        self,
    ) -> None:
        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.future_bound_task",
                provider_id="mock.tool",
            )
        )
        provider = MockSkillProvider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        interaction_id = "specific-preflight"
        self.assertTrue(runtime.begin_interaction(interaction_id))

        try:
            receipt = await runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-specific-preflight",
                    requested_scope="specific_goal",
                    foreground_interaction_id=interaction_id,
                    target_goal_ids=("goal-future",),
                    expected_plan_id="plan-future",
                    expected_plan_fingerprint="fingerprint-future",
                )
            )
            execution = await runtime.execute(
                InteractionResponse(
                    interaction_id=interaction_id,
                    skills=[
                        {
                            "request_id": "future-bound-request",
                            "skill_id": "chromie.future_bound_task",
                            "metadata": {
                                "canonical_plan_id": "plan-future",
                                "canonical_plan_fingerprint": (
                                    "fingerprint-future"
                                ),
                                "source_goal_ids": ["goal-future"],
                            },
                        }
                    ],
                )
            )
        finally:
            runtime.end_interaction(interaction_id)

        self.assertEqual(receipt.interaction_ids, (interaction_id,))
        self.assertEqual(receipt.selected_request_ids, ())
        self.assertEqual(provider.calls, [])
        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            execution.results[0].reason_code,
            "cancelled_before_start",
        )

    async def test_specific_goal_rule_survives_unrelated_scheduled_work(
        self,
    ) -> None:
        unrelated_started = asyncio.Event()
        release_unrelated = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "unrelated-active":
                    unrelated_started.set()
                    await release_unrelated.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.unrelated_active",
                provider_id="mock.tool",
            )
        )
        registry.register(
            _tool_definition(
                skill_id="chromie.later_exact_target",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        interaction_id = "specific-unrelated-scheduled"
        self.assertTrue(runtime.begin_interaction(interaction_id))
        plan_metadata = {
            "canonical_plan_id": "plan-later-exact",
            "canonical_plan_fingerprint": "fingerprint-later-exact",
        }

        try:
            unrelated_execution_task = asyncio.create_task(
                runtime.execute(
                    InteractionResponse(
                        interaction_id=interaction_id,
                        skills=[
                            {
                                "request_id": "unrelated-active",
                                "skill_id": "chromie.unrelated_active",
                                "metadata": {
                                    **plan_metadata,
                                    "source_goal_ids": ["goal-unrelated"],
                                },
                            }
                        ],
                    )
                )
            )
            await unrelated_started.wait()

            receipt = await runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-specific-while-unrelated",
                    requested_scope="specific_goal",
                    foreground_interaction_id=interaction_id,
                    target_goal_ids=("goal-later",),
                    expected_plan_id="plan-later-exact",
                    expected_plan_fingerprint="fingerprint-later-exact",
                )
            )
            release_unrelated.set()
            unrelated_execution = await unrelated_execution_task
            target_execution = await runtime.execute(
                InteractionResponse(
                    interaction_id=interaction_id,
                    skills=[
                        {
                            "request_id": "later-exact-target",
                            "skill_id": "chromie.later_exact_target",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-later"],
                            },
                        }
                    ],
                )
            )
        finally:
            release_unrelated.set()
            runtime.end_interaction(interaction_id)

        self.assertEqual(receipt.interaction_ids, (interaction_id,))
        self.assertEqual(receipt.selected_request_ids, ())
        self.assertEqual(unrelated_execution.status, "completed")
        self.assertEqual(
            [request.request_id for request in provider.calls],
            ["unrelated-active"],
        )
        self.assertEqual(target_execution.status, "cancelled")
        self.assertEqual(
            target_execution.results[0].reason_code,
            "cancelled_before_start",
        )

    async def test_broader_rule_dominates_earlier_output_rule(
        self,
    ) -> None:
        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        speech_provider = LocalSpeechSkillProvider(
            lambda _args: {
                "scheduled": True,
                "playback_started": True,
                "spoken": True,
            }
        )
        body_provider = MockSkillProvider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)
        interaction_id = "scope-monotonic"
        self.assertTrue(runtime.begin_interaction(interaction_id))

        try:
            await runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-stop-output-first",
                    requested_scope="output_only",
                    foreground_interaction_id=interaction_id,
                )
            )
            await runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-stop-current-second",
                    requested_scope="current_interaction",
                    foreground_interaction_id=interaction_id,
                )
            )
            execution = await runtime.execute(
                InteractionResponse(
                    interaction_id=interaction_id,
                    speech=[
                        {
                            "id": "future-required-speech",
                            "text": "Starting.",
                            "timing": "sequential",
                            "metadata": {
                                "wait_for_playback_start": True,
                            },
                        }
                    ],
                    skills=[
                        {
                            "request_id": "future-motion",
                            "skill_id": "soridormi.nod_yes",
                            "timing": "sequential",
                        }
                    ],
                )
            )
        finally:
            runtime.end_interaction(interaction_id)

        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            [
                (result.request_id, result.reason_code)
                for result in execution.results
            ],
            [
                ("future-required-speech", "cancelled_before_start"),
                ("future-motion", "cancelled_before_start"),
            ],
        )
        self.assertEqual(body_provider.calls, [])

    async def test_specific_goal_cancels_active_request_and_keeps_sibling(
        self,
    ) -> None:
        target_started = asyncio.Event()

        class SequentialProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "cancel-active":
                    target_started.set()
                    await asyncio.Event().wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.cancel",
                provider_id="mock.tool",
            )
        )
        registry.register(
            _tool_definition(
                skill_id="chromie.keep",
                provider_id="mock.tool",
            )
        )
        provider = SequentialProvider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        plan_metadata = {
            "canonical_plan_id": "plan-active",
            "canonical_plan_fingerprint": "fingerprint-active",
        }
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="specific-active",
                    skills=[
                        {
                            "request_id": "cancel-active",
                            "skill_id": "chromie.cancel",
                            "timing": "sequential",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-cancel"],
                            },
                        },
                        {
                            "request_id": "keep-after",
                            "skill_id": "chromie.keep",
                            "timing": "sequential",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-keep"],
                            },
                        },
                    ],
                )
            )
        )
        await target_started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-specific-active",
                requested_scope="specific_goal",
                foreground_interaction_id="specific-active",
                target_goal_ids=("goal-cancel",),
                expected_plan_id="plan-active",
                expected_plan_fingerprint="fingerprint-active",
            )
        )
        execution = await execution_task

        self.assertEqual(receipt.active_request_ids, ("cancel-active",))
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                (
                    "cancel-active",
                    "cancelled",
                    "cancelled_specific_goal",
                ),
                ("keep-after", "completed", None),
            ],
        )

    async def test_specific_goal_shared_owner_conflict_does_not_cancel(
        self,
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class SharedProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.shared",
                provider_id="mock.tool",
            )
        )
        provider = SharedProvider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="specific-shared",
                    skills=[
                        {
                            "request_id": "shared-request",
                            "skill_id": "chromie.shared",
                            "metadata": {
                                "canonical_plan_id": "plan-shared",
                                "canonical_plan_fingerprint": "fingerprint-shared",
                                "source_goal_ids": [
                                    "goal-cancel",
                                    "goal-keep",
                                ],
                            },
                        }
                    ],
                )
            )
        )
        await started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-specific-shared",
                requested_scope="specific_goal",
                foreground_interaction_id="specific-shared",
                target_goal_ids=("goal-cancel",),
                expected_plan_id="plan-shared",
                expected_plan_fingerprint="fingerprint-shared",
            )
        )
        release.set()
        execution = await execution_task

        self.assertEqual(receipt.selected_request_ids, ())
        self.assertEqual(
            receipt.shared_owner_conflict_request_ids,
            ("shared-request",),
        )
        self.assertEqual(provider.cancelled_request_ids, [])
        self.assertEqual(execution.status, "completed")

    async def test_specific_goal_stale_plan_binding_is_a_noop(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.bound_task",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="specific-stale",
                    skills=[
                        {
                            "request_id": "stale-request",
                            "skill_id": "chromie.bound_task",
                            "metadata": {
                                "canonical_plan_id": "plan-current",
                                "canonical_plan_fingerprint": (
                                    "fingerprint-current"
                                ),
                                "source_goal_ids": ["goal-current"],
                            },
                        }
                    ],
                )
            )
        )
        await started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-specific-stale",
                requested_scope="specific_goal",
                foreground_interaction_id="specific-stale",
                target_goal_ids=("goal-current",),
                expected_plan_id="plan-current",
                expected_plan_fingerprint="fingerprint-obsolete",
            )
        )
        release.set()
        execution = await execution_task

        self.assertEqual(receipt.selected_request_ids, ())
        self.assertEqual(
            receipt.stale_binding_request_ids,
            ("stale-request",),
        )
        self.assertEqual(provider.cancelled_request_ids, [])
        self.assertEqual(execution.status, "completed")

    async def test_specific_physical_goal_reports_provider_scope_widening(
        self,
    ) -> None:
        both_started = asyncio.Event()
        started_count = 0

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                nonlocal started_count
                started_count += 1
                if started_count == 2:
                    both_started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled motion resumed")

        definition_a = _body_definition(
            skill_id="soridormi.motion_a",
            can_run_parallel=True,
            exclusive_group=None,
        ).model_copy(
            update={
                "metadata": {
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "cancellation_granularity": "global_domain",
                }
            }
        )
        definition_b = definition_a.model_copy(
            update={"skill_id": "soridormi.motion_b"}
        )
        registry = SkillRegistry()
        registry.register(definition_a)
        registry.register(definition_b)
        provider = Provider("mock.body")
        runtime = SkillRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)
        plan_metadata = {
            "canonical_plan_id": "plan-physical",
            "canonical_plan_fingerprint": "fingerprint-physical",
        }
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="specific-physical",
                    skills=[
                        {
                            "request_id": "motion-a",
                            "skill_id": definition_a.skill_id,
                            "timing": "parallel",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-a"],
                            },
                        },
                        {
                            "request_id": "motion-b",
                            "skill_id": definition_b.skill_id,
                            "timing": "parallel",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-b"],
                            },
                        },
                    ],
                )
            )
        )
        await both_started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-specific-physical",
                requested_scope="specific_goal",
                foreground_interaction_id="specific-physical",
                target_goal_ids=("goal-a",),
                expected_plan_id="plan-physical",
                expected_plan_fingerprint="fingerprint-physical",
            )
        )
        execution = await execution_task

        self.assertTrue(receipt.widened)
        self.assertEqual(receipt.effective_scope, "embodied_motion")
        self.assertEqual(
            receipt.widening_reason,
            "provider_supports_only_global_embodied_motion_cancel",
        )
        self.assertEqual(
            receipt.selected_request_ids,
            ("motion-a", "motion-b"),
        )
        self.assertEqual(
            receipt.affected_goal_ids,
            ("goal-a", "goal-b"),
        )
        self.assertEqual(execution.status, "cancelled")

    async def test_current_interaction_scope_does_not_cancel_another_interaction(
        self,
    ) -> None:
        started: dict[str, asyncio.Event] = {
            "cancel": asyncio.Event(),
            "keep": asyncio.Event(),
        }
        release_keep = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started[context.interaction_id].set()
                if context.interaction_id == "keep":
                    await release_keep.wait()
                    return await MockSkillProvider.execute(
                        self,
                        request,
                        definition,
                        context,
                    )
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.long_task",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = SkillRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)
        cancel_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="cancel",
                    skills=[
                        {
                            "request_id": "cancel-request",
                            "skill_id": "chromie.long_task",
                        }
                    ],
                )
            )
        )
        keep_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="keep",
                    skills=[
                        {
                            "request_id": "keep-request",
                            "skill_id": "chromie.long_task",
                        }
                    ],
                )
            )
        )
        await asyncio.gather(
            started["cancel"].wait(),
            started["keep"].wait(),
        )

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-current",
                requested_scope="current_interaction",
                foreground_interaction_id="cancel",
            )
        )
        cancelled = await cancel_task
        release_keep.set()
        kept = await keep_task

        self.assertEqual(receipt.interaction_ids, ("cancel",))
        self.assertEqual(
            receipt.selected_request_ids,
            ("cancel-request",),
        )
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(kept.status, "completed")

    async def test_concurrent_execute_rejects_reused_interaction_id(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        registry.register(
            _tool_definition(
                skill_id="chromie.long_task",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        first = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="reused-interaction",
                    skills=[
                        {
                            "request_id": "first-request",
                            "skill_id": "chromie.long_task",
                        }
                    ],
                )
            )
        )
        await started.wait()

        with self.assertRaisesRegex(
            ValueError,
            "cannot reuse interaction_id",
        ):
            await runtime.execute(
                InteractionResponse(
                    interaction_id="reused-interaction",
                    skills=[
                        {
                            "request_id": "second-request",
                            "skill_id": "chromie.long_task",
                        }
                    ],
                )
            )

        release.set()
        execution = await first
        self.assertEqual(execution.status, "completed")

    async def test_non_interruptible_request_does_not_block_scope_dispatch(
        self,
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        definition = _body_definition(interruptible=False)
        registry = SkillRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="non-interruptible",
                    skills=[
                        {
                            "request_id": "cannot-interrupt",
                            "skill_id": definition.skill_id,
                            "cancellable": True,
                        }
                    ],
                )
            )
        )
        await started.wait()

        receipt = await asyncio.wait_for(
            runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-stop-motion",
                    requested_scope="embodied_motion",
                )
            ),
            timeout=0.1,
        )

        self.assertEqual(
            receipt.non_interruptible_request_ids,
            ("cannot-interrupt",),
        )
        self.assertEqual(receipt.cancel_requested_request_ids, ())
        release.set()
        execution = await execution_task
        self.assertEqual(execution.status, "completed")

    async def test_current_scope_terminalizes_every_queued_sequential_request(
        self,
    ) -> None:
        started = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "active-barrier":
                    started.set()
                    await asyncio.Event().wait()
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = SkillRegistry()
        barrier_definition = _tool_definition(
            skill_id="chromie.barrier",
            provider_id="mock.tool",
        ).model_copy(
            update={
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "metadata": {"type": "object"},
                    },
                    "additionalProperties": False,
                }
            }
        )
        registry.register(barrier_definition)
        registry.register(local_speech_definition())
        registry.register(
            _tool_definition(
                skill_id="chromie.queued",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(
            LocalSpeechSkillProvider(
                lambda _args: {
                    "scheduled": True,
                    "playback_started": True,
                    "spoken": True,
                }
            )
        )
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="current-sequential",
                    speech=[
                        {
                            "id": "completed-pre-action",
                            "text": "Starting.",
                            "timing": "sequential",
                        }
                    ],
                    skills=[
                        {
                            "request_id": "active-barrier",
                            "skill_id": "chromie.barrier",
                            "timing": "sequential",
                            "args": {
                                "metadata": {
                                    "abort_remaining_on_failure": True,
                                }
                            },
                        },
                        {
                            "request_id": "queued-after-barrier",
                            "skill_id": "chromie.queued",
                            "timing": "sequential",
                        },
                    ],
                )
            )
        )
        await started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-current-sequential",
                requested_scope="current_interaction",
                foreground_interaction_id="current-sequential",
            )
        )
        execution = await execution_task

        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            receipt.queued_request_ids,
            ("queued-after-barrier",),
        )
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                (
                    "completed-pre-action",
                    "completed",
                    None,
                ),
                (
                    "active-barrier",
                    "cancelled",
                    "cancelled_current_interaction",
                ),
                (
                    "queued-after-barrier",
                    "cancelled",
                    "cancelled_before_start",
                ),
            ],
        )
        self.assertEqual(
            [request.request_id for request in provider.calls],
            [],
        )

    async def test_output_only_cancel_preserves_pre_action_delivery_barrier(
        self,
    ) -> None:
        speech_started = asyncio.Event()

        async def speak(_args: dict[str, object]) -> dict[str, object]:
            speech_started.set()
            await asyncio.Event().wait()
            raise AssertionError("cancelled speech resumed")

        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        speech_provider = LocalSpeechSkillProvider(speak)
        body_provider = MockSkillProvider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="output-barrier",
                    speech=[
                        {
                            "id": "required-pre-action",
                            "text": "I am starting.",
                            "timing": "sequential",
                            "metadata": {
                                "wait_for_playback_start": True,
                            },
                        }
                    ],
                    skills=[
                        {
                            "request_id": "motion-after-speech",
                            "skill_id": "soridormi.nod_yes",
                            "timing": "sequential",
                        }
                    ],
                )
            )
        )
        await speech_started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-output-barrier",
                requested_scope="output_only",
                foreground_interaction_id="output-barrier",
            )
        )
        execution = await execution_task

        self.assertEqual(
            receipt.selected_request_ids,
            ("required-pre-action",),
        )
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                (
                    "required-pre-action",
                    "cancelled",
                    "cancelled_output_only",
                )
            ],
        )
        self.assertEqual(body_provider.calls, [])

    async def test_scoped_provider_cancel_failure_is_not_reported_as_stopped(
        self,
    ) -> None:
        started = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                raise ConnectionError("physical cancel failed")

        definition = _body_definition()
        registry = SkillRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="cancel-failure",
                    skills=[
                        {
                            "request_id": "motion-unknown",
                            "skill_id": definition.skill_id,
                        }
                    ],
                )
            )
        )
        await started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-motion-failure",
                requested_scope="embodied_motion",
            )
        )
        execution = await execution_task

        self.assertEqual(
            receipt.provider_cancel_failures,
            ("motion-unknown:physical cancel failed",),
        )
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[0].status, "failed")
        self.assertEqual(
            execution.results[0].reason_code,
            "cancellation_failed_embodied_motion",
        )
        self.assertIn(
            "provider cancellation was not confirmed",
            execution.results[0].message,
        )

    async def test_concurrent_cancel_callers_share_provider_failure(
        self,
    ) -> None:
        started = asyncio.Event()
        cancel_started = asyncio.Event()
        release_cancel = asyncio.Event()

        class Provider(MockSkillProvider):
            cancel_attempts = 0

            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.cancel_attempts += 1
                cancel_started.set()
                await release_cancel.wait()
                raise ConnectionError("shared physical cancel failure")

        registry = SkillRegistry()
        registry.register(_body_definition())
        provider = Provider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="concurrent-cancel-failure",
                    skills=[
                        {
                            "request_id": "motion-concurrent-failure",
                            "skill_id": "soridormi.nod_yes",
                        }
                    ],
                )
            )
        )
        await started.wait()
        directive = CancellationDirective(
            source_turn_id="turn-concurrent-cancel-failure",
            requested_scope="embodied_motion",
        )

        first_cancel = asyncio.create_task(runtime.cancel_scope(directive))
        await cancel_started.wait()
        second_cancel = asyncio.create_task(runtime.cancel_scope(directive))
        await asyncio.sleep(0)
        release_cancel.set()
        first_receipt, second_receipt = await asyncio.gather(
            first_cancel,
            second_cancel,
        )
        execution = await execution_task

        self.assertEqual(provider.cancel_attempts, 1)
        for receipt in (first_receipt, second_receipt):
            self.assertEqual(
                receipt.provider_cancel_failures,
                (
                    "motion-concurrent-failure:"
                    "shared physical cancel failure",
                ),
            )
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[0].status, "failed")
        self.assertEqual(
            execution.results[0].reason_code,
            "cancellation_failed_embodied_motion",
        )

    async def test_distinct_turns_share_in_flight_global_provider_cancel(
        self,
    ) -> None:
        started = asyncio.Event()
        cancel_started = asyncio.Event()
        release_cancel = asyncio.Event()

        class Provider(MockSkillProvider):
            cancel_attempts = 0

            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.cancel_attempts += 1
                cancel_started.set()
                await release_cancel.wait()

        definition = _body_definition().model_copy(
            update={
                "metadata": {
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "cancellation_granularity": "global_domain",
                }
            }
        )
        registry = SkillRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="distinct-turn-shared-cancel",
                    skills=[
                        {
                            "request_id": "motion-shared-in-flight",
                            "skill_id": definition.skill_id,
                        }
                    ],
                )
            )
        )
        await started.wait()

        first_cancel = asyncio.create_task(
            runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-shared-in-flight-a",
                    requested_scope="embodied_motion",
                )
            )
        )
        await cancel_started.wait()
        second_cancel = asyncio.create_task(
            runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-shared-in-flight-b",
                    requested_scope="embodied_motion",
                )
            )
        )
        await asyncio.sleep(0)
        self.assertEqual(provider.cancel_attempts, 1)
        release_cancel.set()
        first_receipt, second_receipt = await asyncio.gather(
            first_cancel,
            second_cancel,
        )
        execution = await execution_task

        self.assertEqual(provider.cancel_attempts, 1)
        self.assertEqual(first_receipt.provider_cancel_failures, ())
        self.assertEqual(second_receipt.provider_cancel_failures, ())
        self.assertEqual(
            first_receipt.cancel_requested_request_ids,
            ("motion-shared-in-flight",),
        )
        self.assertEqual(
            second_receipt.cancel_requested_request_ids,
            ("motion-shared-in-flight",),
        )
        self.assertEqual(execution.status, "cancelled")

    async def test_completed_success_cancel_is_reused_for_same_context(
        self,
    ) -> None:
        started = asyncio.Event()
        release_execution = asyncio.Event()
        cancel_completed = asyncio.Event()

        class Provider(MockSkillProvider):
            cancel_attempts = 0

            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                while not release_execution.is_set():
                    try:
                        await release_execution.wait()
                    except asyncio.CancelledError:
                        continue
                return await MockSkillProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.cancel_attempts += 1
                if self.cancel_attempts > 1:
                    raise RuntimeError("duplicate successful provider cancel")
                cancel_completed.set()

        definition = _body_definition().model_copy(
            update={
                "metadata": {
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "cancellation_granularity": "global_domain",
                }
            }
        )
        registry = SkillRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        active_key = ("completed-success-reuse", "motion-success-reuse")
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id=active_key[0],
                    skills=[
                        {
                            "request_id": active_key[1],
                            "skill_id": definition.skill_id,
                        }
                    ],
                )
            )
        )
        await started.wait()

        first_cancel = asyncio.create_task(
            runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-success-reuse-a",
                    requested_scope="embodied_motion",
                )
            )
        )
        await cancel_completed.wait()
        for _ in range(100):
            provider_future = runtime._active[active_key][
                3
            ].provider_cancel_future
            if provider_future is not None and provider_future.done():
                break
            await asyncio.sleep(0)
        self.assertIsNotNone(provider_future)
        self.assertTrue(provider_future.done())

        second_cancel = asyncio.create_task(
            runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-success-reuse-b",
                    requested_scope="embodied_motion",
                )
            )
        )
        for _ in range(100):
            if (
                runtime._active[active_key][
                    3
                ].provider_cancel_source_turn_id
                == "turn-success-reuse-b"
            ):
                break
            await asyncio.sleep(0)
        self.assertEqual(provider.cancel_attempts, 1)

        release_execution.set()
        first_receipt, second_receipt = await asyncio.gather(
            first_cancel,
            second_cancel,
        )
        execution = await execution_task

        self.assertEqual(provider.cancel_attempts, 1)
        self.assertEqual(first_receipt.provider_cancel_failures, ())
        self.assertEqual(second_receipt.provider_cancel_failures, ())
        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            execution.results[0].reason_code,
            "cancelled_embodied_motion",
        )

    async def test_new_started_motion_forces_new_global_cancel_epoch(
        self,
    ) -> None:
        started = {
            "global-epoch-first": asyncio.Event(),
            "global-epoch-second": asyncio.Event(),
        }
        first_cancel_started = asyncio.Event()
        two_cancel_attempts = asyncio.Event()
        release_cancel = asyncio.Event()

        class Provider(MockSkillProvider):
            cancel_attempts = 0

            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started[context.interaction_id].set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.cancel_attempts += 1
                first_cancel_started.set()
                if self.cancel_attempts == 2:
                    two_cancel_attempts.set()
                await release_cancel.wait()

        definition = _body_definition(exclusive_group=None).model_copy(
            update={
                "metadata": {
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "cancellation_granularity": "global_domain",
                }
            }
        )
        registry = SkillRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = SkillRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)
        first_execution = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="global-epoch-first",
                    skills=[
                        {
                            "request_id": "motion-first-epoch",
                            "skill_id": definition.skill_id,
                        }
                    ],
                )
            )
        )
        await started["global-epoch-first"].wait()
        first_cancel = asyncio.create_task(
            runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-global-epoch-a",
                    requested_scope="embodied_motion",
                )
            )
        )
        await first_cancel_started.wait()

        second_execution = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="global-epoch-second",
                    skills=[
                        {
                            "request_id": "motion-second-epoch",
                            "skill_id": definition.skill_id,
                        }
                    ],
                )
            )
        )
        await started["global-epoch-second"].wait()
        second_cancel = asyncio.create_task(
            runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id="turn-global-epoch-b",
                    requested_scope="embodied_motion",
                )
            )
        )
        try:
            await asyncio.wait_for(two_cancel_attempts.wait(), timeout=0.5)
            self.assertEqual(provider.cancel_attempts, 2)
        finally:
            release_cancel.set()

        (
            first_receipt,
            second_receipt,
            first_result,
            second_result,
        ) = await asyncio.gather(
            first_cancel,
            second_cancel,
            first_execution,
            second_execution,
        )

        self.assertEqual(provider.cancel_attempts, 2)
        self.assertEqual(
            first_receipt.selected_request_ids,
            ("motion-first-epoch",),
        )
        self.assertEqual(
            second_receipt.selected_request_ids,
            ("motion-first-epoch", "motion-second-epoch"),
        )
        self.assertEqual(first_result.status, "cancelled")
        self.assertEqual(second_result.status, "cancelled")

    async def test_current_cancel_failure_still_terminalizes_queued_work(
        self,
    ) -> None:
        started = asyncio.Event()

        class Provider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                raise ConnectionError("current provider cancel failed")

        barrier_definition = _tool_definition(
            skill_id="chromie.current-barrier",
        ).model_copy(
            update={
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "metadata": {"type": "object"},
                    },
                    "additionalProperties": False,
                }
            }
        )
        registry = SkillRegistry()
        registry.register(barrier_definition)
        registry.register(
            _tool_definition(skill_id="chromie.current-queued")
        )
        provider = Provider("mock.tool")
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    interaction_id="current-cancel-failure",
                    skills=[
                        {
                            "request_id": "active-current-failure",
                            "skill_id": barrier_definition.skill_id,
                            "timing": "sequential",
                            "args": {
                                "metadata": {
                                    "abort_remaining_on_failure": True,
                                }
                            },
                        },
                        {
                            "request_id": "queued-current-failure",
                            "skill_id": "chromie.current-queued",
                            "timing": "sequential",
                        },
                    ],
                )
            )
        )
        await started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-current-cancel-failure",
                requested_scope="current_interaction",
                foreground_interaction_id="current-cancel-failure",
            )
        )
        execution = await execution_task

        self.assertEqual(
            receipt.queued_request_ids,
            ("queued-current-failure",),
        )
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                (
                    "active-current-failure",
                    "failed",
                    "cancellation_failed_current_interaction",
                ),
                (
                    "queued-current-failure",
                    "cancelled",
                    "cancelled_before_start",
                ),
            ],
        )
        self.assertEqual(
            [request.request_id for request in provider.calls],
            ["active-current-failure"],
        )

    async def test_sequential_requests_preserve_order(self) -> None:
        provider = MockSkillProvider("mock.body")
        registry = SkillRegistry()
        registry.register(_body_definition(skill_id="soridormi.nod_yes"))
        registry.register(_body_definition(skill_id="soridormi.express_attention"))
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)

        await runtime.execute(
            InteractionResponse(
                skills=[
                    {
                        "skill_id": "soridormi.nod_yes",
                        "args": {},
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "soridormi.express_attention",
                        "args": {},
                        "timing": "sequential",
                    },
                ]
            )
        )

        self.assertEqual(
            [request.skill_id for request in provider.calls],
            ["soridormi.nod_yes", "soridormi.express_attention"],
        )

    async def test_after_skills_speech_waits_for_parallel_body_work(self) -> None:
        events: list[str] = []

        async def speak(args: dict[str, object]) -> dict[str, object]:
            events.append("speech")
            return {"spoken": True}

        class OrderedBodyProvider(MockSkillProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                events.append("body_start")
                await asyncio.sleep(0.01)
                events.append("body_end")
                return await super().execute(request, definition, context)

        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        runtime = SkillRuntime(registry)
        runtime.register_provider(LocalSpeechSkillProvider(speak))
        runtime.register_provider(OrderedBodyProvider("mock.body"))

        await runtime.execute(
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_skills"}],
                skills=[
                    {
                        "skill_id": "soridormi.nod_yes",
                        "args": {},
                        "timing": "parallel",
                    }
                ],
            )
        )

        self.assertEqual(events, ["body_start", "body_end", "speech"])

    async def test_preflight_rejects_unknown_invalid_and_unconfirmed_skills(self) -> None:
        provider = MockSkillProvider("mock.body")
        registry = SkillRegistry()
        registry.register(_body_definition(requires_confirmation=True))
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)

        with self.assertRaisesRegex(ValueError, "unknown skill"):
            await runtime.execute(
                InteractionResponse(skills=[{"skill_id": "missing.skill"}])
            )
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            await runtime.execute(
                InteractionResponse(
                    skills=[
                        {
                            "skill_id": "soridormi.nod_yes",
                            "args": {"joint": "not-in-schema"},
                        }
                    ]
                )
            )
        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            await runtime.execute(
                InteractionResponse(
                    skills=[{"request_id": "nod-1", "skill_id": "soridormi.nod_yes"}]
                )
            )
        self.assertEqual(provider.calls, [])

    async def test_confirmation_proof_allows_request(self) -> None:
        provider = MockSkillProvider("mock.body")
        registry = SkillRegistry()
        registry.register(_body_definition(requires_confirmation=True))
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)

        execution = await runtime.execute(
            InteractionResponse(
                skills=[{"request_id": "nod-1", "skill_id": "soridormi.nod_yes"}]
            ),
            authorization=RuntimeAuthorization(confirmed_request_ids={"nod-1"}),
        )

        self.assertEqual(execution.status, "completed")

    async def test_timeout_calls_provider_cancel(self) -> None:
        provider = MockSkillProvider("mock.body", delay_s=0.2)
        registry = SkillRegistry()
        registry.register(_body_definition(timeout_ms=10))
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)

        execution = await runtime.execute(
            InteractionResponse(
                skills=[{"request_id": "nod-1", "skill_id": "soridormi.nod_yes"}]
            )
        )

        self.assertEqual(execution.results[0].status, "timed_out")
        self.assertEqual(provider.cancelled_request_ids, ["nod-1"])

    async def test_cancel_failure_does_not_override_timeout(self) -> None:
        class FailingCancelProvider(MockSkillProvider):
            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                raise ConnectionError("provider disconnected during cancellation")

        provider = FailingCancelProvider("mock.body", delay_s=0.2)
        registry = SkillRegistry()
        registry.register(_body_definition(timeout_ms=10))
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)

        execution = await runtime.execute(
            InteractionResponse(
                skills=[{"request_id": "nod-1", "skill_id": "soridormi.nod_yes"}]
            )
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[0].status, "timed_out")
        self.assertEqual(execution.results[0].reason_code, "timeout")
        self.assertIn(
            "provider cancellation failed",
            execution.results[0].message,
        )

    async def test_cancel_failure_does_not_override_interruption(self) -> None:
        class FailingCancelProvider(MockSkillProvider):
            cancel_attempts = 0

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.cancel_attempts += 1
                raise ConnectionError("provider disconnected during cancellation")

        provider = FailingCancelProvider("mock.body", delay_s=5)
        registry = SkillRegistry()
        registry.register(_body_definition())
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)
        task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    skills=[
                        {
                            "request_id": "nod-1",
                            "skill_id": "soridormi.nod_yes",
                        }
                    ]
                )
            )
        )
        while not provider.calls:
            await asyncio.sleep(0)

        task.cancel()
        execution = await task

        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [("nod-1", "cancelled", "cancelled")],
        )
        self.assertEqual(
            [(trace.request_id, trace.status) for trace in execution.traces],
            [("nod-1", "cancelled")],
        )
        self.assertIn(
            "provider cancellation failed",
            execution.results[0].message,
        )
        self.assertEqual(runtime.scheduler_status().active_count, 0)
        self.assertEqual(provider.cancel_attempts, 1)

    async def test_interruption_cancels_all_cancellable_children(self) -> None:
        speech_provider = LocalSpeechSkillProvider(
            lambda args: asyncio.sleep(5, result={"spoken": True})
        )
        body_provider = MockSkillProvider("mock.body", delay_s=5)
        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        runtime = SkillRuntime(registry)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)

        task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    speech=[{"id": "speech-1", "text": "Hello."}],
                    skills=[
                        {
                            "request_id": "nod-1",
                            "skill_id": "soridormi.nod_yes",
                        }
                    ],
                )
            )
        )
        while len(body_provider.calls) < 1:
            await asyncio.sleep(0)
        task.cancel()
        execution = await task

        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [
                ("speech-1", "cancelled", "cancelled"),
                ("nod-1", "cancelled", "cancelled"),
            ],
        )
        self.assertEqual(
            [
                (trace.request_id, trace.status)
                for trace in execution.traces
            ],
            [
                ("speech-1", "cancelled"),
                ("nod-1", "cancelled"),
            ],
        )
        self.assertEqual(speech_provider.cancelled_request_ids, {"speech-1"})
        self.assertEqual(body_provider.cancelled_request_ids, ["nod-1"])
        self.assertEqual(runtime.scheduler_status().active_count, 0)

    async def test_interruption_omits_unstarted_sequential_request(self) -> None:
        provider = MockSkillProvider("mock.body", delay_s=5)
        registry = SkillRegistry()
        registry.register(
            _body_definition(
                skill_id="soridormi.nod_yes",
                exclusive_group=None,
            )
        )
        registry.register(
            _body_definition(
                skill_id="soridormi.express_attention",
                exclusive_group=None,
            )
        )
        runtime = SkillRuntime(registry)
        runtime.register_provider(provider)

        task = asyncio.create_task(
            runtime.execute(
                InteractionResponse(
                    skills=[
                        {
                            "request_id": "first-active",
                            "skill_id": "soridormi.nod_yes",
                            "timing": "sequential",
                        },
                        {
                            "request_id": "second-unstarted",
                            "skill_id": "soridormi.express_attention",
                            "timing": "sequential",
                        },
                    ],
                )
            )
        )
        while not provider.calls:
            await asyncio.sleep(0)
        task.cancel()
        execution = await task

        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            [
                (result.request_id, result.status, result.reason_code)
                for result in execution.results
            ],
            [("first-active", "cancelled", "cancelled")],
        )
        self.assertEqual(
            [request.request_id for request in provider.calls],
            ["first-active"],
        )
        self.assertEqual(provider.cancelled_request_ids, ["first-active"])
        self.assertEqual(runtime.scheduler_status().active_count, 0)

    async def test_agent_result_adapter_preserves_speech_actions_and_graphs(self) -> None:
        response = AgentResultInteractionAdapter().convert(
            AgentResult(
                speak_immediate=[SpeechItem(text="Starting.")],
                actions=[
                    ActionCommand(
                        id="nod-1",
                        target="motion_controller",
                        type="soridormi.nod_yes",
                        params={"count": 2},
                    )
                ],
                speak_after=[SpeechItem(text="Done.")],
                task_graphs=[
                    {
                        "graph_id": "legacy-1",
                        "nodes": [],
                        "requires_confirmation": True,
                    }
                ],
            )
        )

        self.assertEqual(response.speech[0].timing, "immediate")
        self.assertEqual(response.speech[1].timing, "after_skills")
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(response.skills[1].skill_id, "chromie.task_graph.execute")
        self.assertTrue(response.skills[1].requires_confirmation)
        self.assertTrue(response.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
