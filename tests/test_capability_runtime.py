from __future__ import annotations

from tests.capability_runtime_test_support import submit_and_wait_terminal

import asyncio
import time
import unittest

from shared.chromie_contracts.action import ActionCommand
from shared.chromie_contracts.interaction import CapabilityResult, InteractionResponse
from shared.chromie_contracts.reflex import CancellationDirective, CancellationDispatchReceipt

from orchestrator.runtime.capability_runtime import (
    LocalSpeechCapabilityProvider,
    MockCapabilityProvider,
    RuntimeAuthorization,
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityRuntime,
    local_speech_definition,
)
from orchestrator.runtime.soridormi_capability_provider import (
    SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA,
    import_soridormi_capability_catalog,
)


def _request_ids(bindings):  # type: ignore[no-untyped-def]
    return tuple(item.request_id for item in bindings)


def _provider_failure_texts(receipt):  # type: ignore[no-untyped-def]
    return tuple(
        f"{item.request_id}:{item.error}"
        for item in receipt.provider_cancel_failure_evidence
    )


def _body_definition(
    *,
    capability_id: str = "soridormi.nod_yes",
    provider_id: str = "mock.body",
    timeout_ms: int = 1000,
    requires_confirmation: bool = False,
    interruptible: bool = True,
    can_run_parallel: bool = True,
    exclusive_group: str | None = "soridormi.robot_motion",
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
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
    capability_id: str,
    provider_id: str = "mock.tool",
    interruptible: bool = True,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
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


class CapabilityRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_returns_after_runtime_acceptance_before_provider_completion(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class SlowProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await release.wait()
                return await MockCapabilityProvider.execute(
                    self, request, definition, context
                )

        registry = CapabilityRegistry()
        registry.register(_body_definition(exclusive_group=None))
        provider = SlowProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        response = InteractionResponse(
            interaction_id="async-dispatch",
            capabilities=[
                {
                    "request_id": "slow-request",
                    "capability_id": "soridormi.nod_yes",
                }
            ],
        )

        receipt = await runtime.submit(response)

        self.assertEqual(receipt.status, "accepted")
        self.assertEqual(receipt.interaction_id, "async-dispatch")
        self.assertEqual(receipt.request_ids, ["slow-request"])
        observation = await runtime.execution_observation()
        self.assertIn("async-dispatch", observation.open_interaction_ids)
        self.assertIn("async-dispatch", observation.executing_interaction_ids)
        self.assertEqual(
            [
                (item.request_id, item.capability_id, item.provider_started)
                for item in observation.requests
            ],
            [("slow-request", "soridormi.nod_yes", False)],
        )

        await started.wait()
        self.assertFalse(release.is_set())
        release.set()
        terminal = await runtime.wait_terminal(receipt)

        self.assertEqual(terminal.status, "completed")
        self.assertEqual([item.status for item in terminal.results], ["completed"])
        final_observation = await runtime.execution_observation()
        self.assertNotIn("async-dispatch", final_observation.open_interaction_ids)
        self.assertNotIn("async-dispatch", final_observation.executing_interaction_ids)
        self.assertEqual(final_observation.requests, [])

    async def test_duplicate_submit_fails_without_corrupting_first_submission(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class SlowProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await release.wait()
                return await MockCapabilityProvider.execute(
                    self, request, definition, context
                )

        registry = CapabilityRegistry()
        registry.register(_body_definition(exclusive_group=None))
        provider = SlowProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        response = InteractionResponse(
            interaction_id="duplicate-dispatch",
            capabilities=[
                {
                    "request_id": "first-request",
                    "capability_id": "soridormi.nod_yes",
                }
            ],
        )
        first = await runtime.submit(response)
        await started.wait()

        with self.assertRaisesRegex(ValueError, "cannot reuse interaction_id"):
            await runtime.submit(response)

        observation = await runtime.execution_observation()
        self.assertIn("duplicate-dispatch", observation.executing_interaction_ids)
        self.assertEqual([item.request_id for item in observation.requests], ["first-request"])
        release.set()
        terminal = await runtime.wait_terminal(first)
        self.assertEqual(terminal.status, "completed")

    async def test_runtime_events_publish_accepted_running_progress_and_terminal(self) -> None:
        class ProgressProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                await context.publish_progress({"fraction": 0.5}, message="halfway")
                return CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status="completed",
                    provider_id=self.provider_id,
                    output={"done": True},
                )

        registry = CapabilityRegistry()
        registry.register(_tool_definition(capability_id="chromie.progress"))
        provider = ProgressProvider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        receipt = await runtime.submit(
            InteractionResponse(
                interaction_id="progress-events",
                capabilities=[
                    {
                        "request_id": "progress-1",
                        "capability_id": "chromie.progress",
                    }
                ],
            )
        )
        terminal = await runtime.wait_terminal(receipt)
        events = await runtime.runtime_events_after(
            receipt.event_cursor,
            dispatch_id=receipt.dispatch_id,
        )

        self.assertEqual(terminal.status, "completed")
        self.assertEqual(
            [event.type for event in events],
            ["accepted", "running", "progress", "completed"],
        )
        self.assertEqual(events[2].progress, {"fraction": 0.5})
        self.assertEqual(events[2].message, "halfway")
        self.assertTrue(events[-1].terminal)
        self.assertEqual(events[-1].request_id, "progress-1")
        self.assertEqual(events[-1].capability_id, "chromie.progress")
        self.assertEqual(events[-1].provider_id, "mock.tool")
        self.assertEqual(events[-1].result.status, "completed")

    async def test_parallel_terminal_event_is_visible_before_slow_sibling_finishes(self) -> None:
        slow_started = asyncio.Event()
        release_slow = asyncio.Event()

        class SplitProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                if request.capability_id == "chromie.slow":
                    slow_started.set()
                    await release_slow.wait()
                return CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status="completed",
                    provider_id=self.provider_id,
                    output={"capability": request.capability_id},
                )

        registry = CapabilityRegistry()
        registry.register(_tool_definition(capability_id="chromie.fast"))
        registry.register(_tool_definition(capability_id="chromie.slow"))
        provider = SplitProvider("mock.tool")
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)
        receipt = await runtime.submit(
            InteractionResponse(
                interaction_id="independent-events",
                capabilities=[
                    {
                        "request_id": "fast-1",
                        "capability_id": "chromie.fast",
                        "timing": "parallel",
                    },
                    {
                        "request_id": "slow-1",
                        "capability_id": "chromie.slow",
                        "timing": "parallel",
                    },
                ],
            )
        )
        await slow_started.wait()

        cursor = receipt.event_cursor
        fast_terminal = None
        while fast_terminal is None:
            event = await runtime.wait_runtime_event(
                cursor,
                dispatch_id=receipt.dispatch_id,
            )
            cursor = event.sequence
            if event.request_id == "fast-1" and event.terminal:
                fast_terminal = event

        observed = await runtime.runtime_events_after(
            receipt.event_cursor,
            dispatch_id=receipt.dispatch_id,
        )
        self.assertEqual(fast_terminal.type, "completed")
        self.assertFalse(
            any(event.request_id == "slow-1" and event.terminal for event in observed),
            observed,
        )
        observation = await runtime.execution_observation()
        self.assertTrue(
            any(item.request_id == "slow-1" for item in observation.requests),
            observation,
        )

        release_slow.set()
        terminal = await runtime.wait_terminal(receipt)
        self.assertEqual(terminal.status, "completed")

    async def test_provider_result_identity_mismatch_fails_closed_and_event_stays_canonical(
        self,
    ) -> None:
        class SpoofingProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                return CapabilityResult(
                    request_id="provider-spoofed-request",
                    capability_id="provider.spoofed.capability",
                    capability_version="9.9.9",
                    status="completed",
                    provider_id="provider.spoofed",
                    output={"done": True},
                )

        registry = CapabilityRegistry()
        registry.register(_tool_definition(capability_id="chromie.identity"))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SpoofingProvider("mock.tool"))
        receipt = await runtime.submit(
            InteractionResponse(
                interaction_id="identity-authority",
                capabilities=[
                    {
                        "request_id": "canonical-request",
                        "capability_id": "chromie.identity",
                    }
                ],
            )
        )
        terminal = await runtime.wait_terminal(receipt)
        events = await runtime.runtime_events_after(
            receipt.event_cursor,
            dispatch_id=receipt.dispatch_id,
        )
        terminal_event = next(event for event in events if event.terminal)

        self.assertEqual(terminal.status, "failed")
        self.assertEqual(terminal.results[0].request_id, "canonical-request")
        self.assertEqual(terminal.results[0].capability_id, "chromie.identity")
        self.assertEqual(terminal.results[0].provider_id, "mock.tool")
        self.assertEqual(terminal.results[0].reason_code, "provider_identity_mismatch")
        self.assertEqual(terminal_event.request_id, "canonical-request")
        self.assertEqual(terminal_event.capability_id, "chromie.identity")
        self.assertEqual(terminal_event.provider_id, "mock.tool")
        self.assertEqual(terminal_event.type, "failed")

    async def test_provider_execute_non_terminal_result_fails_closed(self) -> None:
        class NonTerminalProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                return CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status="running",
                    provider_id=self.provider_id,
                    output={"provider_state": "still_running"},
                )

        registry = CapabilityRegistry()
        registry.register(_tool_definition(capability_id="chromie.non_terminal"))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(NonTerminalProvider("mock.tool"))
        receipt = await runtime.submit(
            InteractionResponse(
                interaction_id="non-terminal-result",
                capabilities=[
                    {
                        "request_id": "non-terminal-request",
                        "capability_id": "chromie.non_terminal",
                    }
                ],
            )
        )

        terminal = await runtime.wait_terminal(receipt)
        events = await runtime.runtime_events_after(
            receipt.event_cursor,
            dispatch_id=receipt.dispatch_id,
        )
        terminal_event = next(event for event in events if event.terminal)

        self.assertEqual(terminal.status, "failed")
        self.assertEqual(terminal.results[0].status, "failed")
        self.assertEqual(terminal.results[0].reason_code, "provider_non_terminal_result")
        self.assertEqual(terminal.results[0].metadata["provider_reported_status"], "running")
        self.assertEqual(terminal_event.type, "failed")
        self.assertEqual(terminal_event.request_id, "non-terminal-request")

    async def test_cancellation_publishes_terminal_runtime_event(self) -> None:
        started = asyncio.Event()

        class BlockingProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled capability resumed")

        registry = CapabilityRegistry()
        registry.register(_body_definition())
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(BlockingProvider("mock.body"))
        receipt = await runtime.submit(
            InteractionResponse(
                interaction_id="cancel-event",
                capabilities=[
                    {
                        "request_id": "cancel-me",
                        "capability_id": "soridormi.nod_yes",
                    }
                ],
            )
        )
        await started.wait()
        await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-cancel-event",
                requested_scope="current_interaction",
                foreground_interaction_id="cancel-event",
            )
        )
        terminal = await runtime.wait_terminal(receipt)
        events = await runtime.runtime_events_after(
            receipt.event_cursor,
            dispatch_id=receipt.dispatch_id,
        )

        self.assertEqual(terminal.status, "cancelled")
        self.assertTrue(
            any(
                event.request_id == "cancel-me"
                and event.type == "cancelled"
                and event.result is not None
                for event in events
            ),
            events,
        )

    async def test_runtime_event_cursors_are_non_destructive_for_multiple_consumers(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_tool_definition(capability_id="chromie.cursor"))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(MockCapabilityProvider("mock.tool"))
        receipt = await runtime.submit(
            InteractionResponse(
                interaction_id="cursor-events",
                capabilities=[
                    {
                        "request_id": "cursor-1",
                        "capability_id": "chromie.cursor",
                    }
                ],
            )
        )
        await runtime.wait_terminal(receipt)

        first = await runtime.runtime_events_after(
            receipt.event_cursor, dispatch_id=receipt.dispatch_id
        )
        second = await runtime.runtime_events_after(
            receipt.event_cursor, dispatch_id=receipt.dispatch_id
        )
        self.assertEqual(
            [event.event_id for event in first],
            [event.event_id for event in second],
        )
        self.assertEqual([event.type for event in first], ["accepted", "running", "completed"])

    async def test_submit_validation_failure_does_not_leave_runtime_ownership(self) -> None:
        runtime = CapabilityRuntime(CapabilityRegistry())
        response = InteractionResponse(
            interaction_id="invalid-dispatch",
            capabilities=[
                {
                    "request_id": "unknown-request",
                    "capability_id": "chromie.unknown",
                }
            ],
        )

        with self.assertRaisesRegex(ValueError, "unknown capability"):
            await runtime.submit(response)

        observation = await runtime.execution_observation()
        self.assertNotIn("invalid-dispatch", observation.open_interaction_ids)
        self.assertNotIn("invalid-dispatch", observation.executing_interaction_ids)
        self.assertEqual(observation.requests, [])

    def test_runtime_has_no_aggregate_execute_api(self) -> None:
        runtime = CapabilityRuntime(CapabilityRegistry())
        self.assertFalse(hasattr(runtime, "execute"))

    def test_soridormi_resource_outcome_schema_accepts_simulation_marker(self) -> None:
        resource = SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA["properties"]["resource_outcome"]
        self.assertIn("mocked_simulation", resource["properties"])
        self.assertEqual(
            resource["properties"]["mocked_simulation"],
            {"type": "boolean"},
        )

    async def test_runtime_rejects_execution_id_collision_after_model_copy(
        self,
    ) -> None:
        response = InteractionResponse(
            interaction_id="collision-turn",
            speech=[{"id": "same-id", "text": "Hello."}],
            capabilities=[
                {
                    "request_id": "different-id",
                    "capability_id": "chromie.test",
                }
            ],
        )
        unsafe = response.model_copy(
            update={
                "capabilities": [
                    response.capabilities[0].model_copy(
                        update={"request_id": "same-id"}
                    )
                ]
            }
        )
        runtime = CapabilityRuntime(CapabilityRegistry())

        with self.assertRaisesRegex(ValueError, "must be unique"):
            await submit_and_wait_terminal(runtime, unsafe)

    async def test_soridormi_import_preserves_provider_confirmation_requirement(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Visible head nod.",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "available": True,
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "requires_confirmation": True,
                }
            ]
        )

        self.assertTrue(registry.get("soridormi.nod_yes").requires_confirmation)
        self.assertEqual(
            registry.get("soridormi.nod_yes").output_schema,
            SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA,
        )

    async def test_soridormi_import_preserves_provider_confirmation_exemption(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
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
            ]
        )

        self.assertFalse(registry.get("soridormi.nod_yes").requires_confirmation)

    async def test_soridormi_import_upserts_catalog_entries(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Old nod.",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "available": True,
                    "timeout_s": 1.0,
                }
            ]
        )
        import_soridormi_capability_catalog(registry,
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
            ]
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
        self.assertEqual(
            definition.output_schema,
            SORIDORMI_NAMED_CAPABILITY_OUTPUT_SCHEMA,
        )
        self.assertEqual(
            definition.metadata["output_contract"],
            "chromie_soridormi_named_capability_v1",
        )

    async def test_soridormi_import_accepts_nested_catalog_contracts(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {
                    "skill_id": "look_at_person",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "availability": {
                        "available": True,
                        "reason": None,
                    },
                    "execution": {
                        "timeout_s": 4.0,
                        "can_run_parallel": False,
                        "exclusive_group": "soridormi.head",
                        "resource_claims": ["head"],
                    },
                    "confirmation": {"required": False},
                    "effects": ["physical_motion"],
                }
            ]
        )

        definition = registry.get("soridormi.look_at_person")
        self.assertTrue(definition.available)
        self.assertEqual(definition.timeout_ms, 4000)
        self.assertFalse(definition.can_run_parallel)
        self.assertEqual(definition.exclusive_group, "soridormi.head")
        self.assertEqual(definition.metadata["resource_claims"], ["head"])

    async def test_soridormi_import_rejects_duplicate_catalog_atomically(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [{"skill_id": "nod_yes", "available": True}]
        )
        before = registry.get("soridormi.nod_yes").model_dump(mode="json")

        with self.assertRaisesRegex(ValueError, "duplicate Soridormi wire skill_id"):
            import_soridormi_capability_catalog(registry,
                [
                    {"skill_id": "wave_hand", "available": True},
                    {"skill_id": "wave_hand", "available": False},
                ]
            )

        self.assertEqual(
            registry.get("soridormi.nod_yes").model_dump(mode="json"),
            before,
        )
        with self.assertRaisesRegex(ValueError, "unknown capability"):
            registry.get("soridormi.wave_hand")

    async def test_soridormi_import_marks_absent_live_capabilities_unavailable(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
            [
                {"skill_id": "nod_yes", "available": True},
                {"skill_id": "wave_hand", "available": True},
            ]
        )
        import_soridormi_capability_catalog(registry,
            [{"skill_id": "wave_hand", "available": True}]
        )

        removed = registry.get("soridormi.nod_yes")
        self.assertFalse(removed.available)
        self.assertEqual(
            removed.unavailable_reason,
            "not present in latest provider catalog",
        )
        self.assertTrue(removed.metadata["catalog_absent"])
        self.assertTrue(registry.get("soridormi.wave_hand").available)

    async def test_speech_only_request_completes(self) -> None:
        spoken: list[str] = []
        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(
            LocalSpeechCapabilityProvider(
                lambda args: spoken.append(args["text"]) or {"spoken": True}
            )
        )

        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                speech=[
                    {
                        "text": "Hello.",
                        "metadata": {
                            "source_goal_ids": ["goal-greeting"],
                            "canonical_plan_id": "plan-greeting",
                        },
                    }
                ]
            )
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(spoken, ["Hello."])
        self.assertEqual(execution.results[0].capability_id, "chromie.speak")
        self.assertEqual(
            execution.results[0].metadata["source_goal_ids"],
            ["goal-greeting"],
        )
        self.assertEqual(
            execution.results[0].metadata["canonical_plan_id"],
            "plan-greeting",
        )

    async def test_failed_playback_start_barrier_prevents_following_body_effect(self) -> None:
        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        body = MockCapabilityProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(
            LocalSpeechCapabilityProvider(
                lambda _args: {
                    "scheduled": True,
                    "playback_started": False,
                }
            )
        )
        runtime.register_provider(body)

        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                speech=[
                    {
                        "text": "I heard you.",
                        "timing": "immediate",
                        "metadata": {"wait_for_playback_start": True},
                    }
                ],
                capabilities=[
                    {
                        "request_id": "nod-after-cue",
                        "capability_id": "soridormi.nod_yes",
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

        class OrderedBodyProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                events.append("body_start")
                return await super().execute(request, definition, context)

        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        body = OrderedBodyProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(LocalSpeechCapabilityProvider(speak))
        runtime.register_provider(body)

        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                speech=[
                    {
                        "text": "I heard you.",
                        "timing": "immediate",
                        "metadata": {"wait_for_playback_start": True},
                    }
                ],
                capabilities=[
                    {
                        "request_id": "nod-after-cue",
                        "capability_id": "soridormi.nod_yes",
                        "timing": "parallel",
                    }
                ],
            )
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(events, ["playback_start", "body_start"])

    async def test_action_only_request_reaches_mock_provider(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_body_definition())
        provider = MockCapabilityProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
                        "capability_version": "1.0.0",
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

        class TimedProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                events.append(("body_start", time.monotonic()))
                result = await super().execute(request, definition, context)
                events.append(("body_end", time.monotonic()))
                return result

        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(LocalSpeechCapabilityProvider(speak))
        runtime.register_provider(TimedProvider("mock.body", delay_s=0.05))

        await submit_and_wait_terminal(runtime,
            InteractionResponse(
                speech=[{"text": "Hello.", "timing": "parallel"}],
                capabilities=[
                    {
                        "capability_id": "soridormi.nod_yes",
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

        class VariableProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(float(request.args["delay_s"]))
                active -= 1
                return await super().execute(request, definition, context)

        registry = CapabilityRegistry()
        for index in range(3):
            registry.register(
                CapabilityDefinition(
                    capability_id=f"test.skill_{index}",
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
        runtime = CapabilityRuntime(registry, max_concurrency=2)

        runtime.register_provider(provider)
        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": f"request-{index}",
                        "capability_id": f"test.skill_{index}",
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

        class ExclusiveProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.02)
                active -= 1
                return await super().execute(request, definition, context)

        registry = CapabilityRegistry()
        registry.register(_body_definition())
        provider = ExclusiveProvider("mock.body")
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)

        await asyncio.gather(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="interaction-a",
                    capabilities=[
                        {
                            "request_id": "same-request",
                            "capability_id": "soridormi.nod_yes",
                        }
                    ],
                )
            ),
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="interaction-b",
                    capabilities=[
                        {
                            "request_id": "same-request",
                            "capability_id": "soridormi.nod_yes",
                        }
                    ],
                )
            ),
        )

        self.assertEqual(peak, 1)

    def test_cancellation_receipt_exposes_only_qualified_request_identity(self) -> None:
        fields = set(CancellationDispatchReceipt.model_fields)
        self.assertTrue(
            {
                "selected_request_bindings",
                "active_request_bindings",
                "queued_request_bindings",
                "cancel_requested_request_bindings",
                "non_interruptible_request_bindings",
                "shared_owner_conflict_request_bindings",
                "stale_binding_request_bindings",
                "provider_cancel_failure_evidence",
            }.issubset(fields)
        )
        self.assertTrue(
            {
                "selected_request_ids",
                "active_request_ids",
                "queued_request_ids",
                "cancel_requested_request_ids",
                "non_interruptible_request_ids",
                "shared_owner_conflict_request_ids",
                "stale_binding_request_ids",
                "provider_cancel_failures",
            }.isdisjoint(fields)
        )

    async def test_duplicate_request_ids_do_not_collide_across_interactions(self) -> None:
        cancelled_interactions: list[str] = []

        class CollisionProvider(MockCapabilityProvider):
            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                cancelled_interactions.append(context.interaction_id)
                raise RuntimeError(
                    f"cancel failed for {context.interaction_id}"
                )

        provider = CollisionProvider("mock.body", delay_s=5)
        registry = CapabilityRegistry()
        registry.register(
            _body_definition(
                exclusive_group=None,
            )
        )
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)

        executions = [
            asyncio.create_task(
                submit_and_wait_terminal(runtime,
                    InteractionResponse(
                        interaction_id=interaction_id,
                        capabilities=[
                            {
                                "request_id": "shared-request",
                                "capability_id": "soridormi.nod_yes",
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
            len(_request_ids(receipt.cancel_requested_request_bindings)),
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

        class IsolatedProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                if context.interaction_id == "keep":
                    await release_keep.wait()
                else:
                    await asyncio.Event().wait()
                return await super().execute(request, definition, context)

        provider = IsolatedProvider("mock.body")
        registry = CapabilityRegistry()
        registry.register(_body_definition(exclusive_group=None))
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)

        cancel_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="cancel",
                    capabilities=[
                        {
                            "request_id": "cancel-request",
                            "capability_id": "soridormi.nod_yes",
                        }
                    ],
                )
            )
        )
        keep_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="keep",
                    capabilities=[
                        {
                            "request_id": "keep-request",
                            "capability_id": "soridormi.nod_yes",
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

        class BodyProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                body_started.set()
                await release_body.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        speech_provider = LocalSpeechCapabilityProvider(speak)
        body_provider = BodyProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)
        interaction_id = "scoped-output"
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id=interaction_id,
                    speech=[
                        {
                            "id": "speech-output",
                            "text": "Still speaking.",
                            "timing": "parallel",
                        }
                    ],
                    capabilities=[
                        {
                            "request_id": "motion-keep",
                            "capability_id": "soridormi.nod_yes",
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

        self.assertEqual(_request_ids(receipt.selected_request_bindings), ("speech-output",))
        self.assertEqual(
            _request_ids(receipt.cancel_requested_request_bindings),
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

        class MotionProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                motion_started.set()
                await asyncio.Event().wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        class ToolProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                tool_started.set()
                await release_tool.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(_body_definition())
        registry.register(_tool_definition(capability_id="chromie.weather"))
        motion_provider = MotionProvider("mock.body")
        tool_provider = ToolProvider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(motion_provider)
        runtime.register_provider(tool_provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="scoped-motion",
                    capabilities=[
                        {
                            "request_id": "motion-cancel",
                            "capability_id": "soridormi.nod_yes",
                            "timing": "parallel",
                        },
                        {
                            "request_id": "weather-keep",
                            "capability_id": "chromie.weather",
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

        self.assertEqual(_request_ids(receipt.selected_request_bindings), ("motion-cancel",))
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

        class SequentialProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "keep-first":
                    first_started.set()
                    await release_first.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.keep",
                provider_id="mock.tool",
            )
        )
        registry.register(
            _tool_definition(
                capability_id="chromie.cancel",
                provider_id="mock.tool",
            )
        )
        provider = SequentialProvider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        plan_metadata = {
            "canonical_plan_id": "plan-scoped",
            "canonical_plan_fingerprint": "fingerprint-scoped",
        }
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="specific-queued",
                    capabilities=[
                        {
                            "request_id": "keep-first",
                            "capability_id": "chromie.keep",
                            "timing": "sequential",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-keep"],
                            },
                        },
                        {
                            "request_id": "cancel-before-start",
                            "capability_id": "chromie.cancel",
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
            _request_ids(receipt.queued_request_bindings),
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
        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.future_bound_task",
                provider_id="mock.tool",
            )
        )
        provider = MockCapabilityProvider("mock.tool")
        runtime = CapabilityRuntime(registry)
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
            execution = await submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id=interaction_id,
                    capabilities=[
                        {
                            "request_id": "future-bound-request",
                            "capability_id": "chromie.future_bound_task",
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
        self.assertEqual(_request_ids(receipt.selected_request_bindings), ())
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

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "unrelated-active":
                    unrelated_started.set()
                    await release_unrelated.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.unrelated_active",
                provider_id="mock.tool",
            )
        )
        registry.register(
            _tool_definition(
                capability_id="chromie.later_exact_target",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        interaction_id = "specific-unrelated-scheduled"
        self.assertTrue(runtime.begin_interaction(interaction_id))
        plan_metadata = {
            "canonical_plan_id": "plan-later-exact",
            "canonical_plan_fingerprint": "fingerprint-later-exact",
        }

        try:
            unrelated_execution_task = asyncio.create_task(
                submit_and_wait_terminal(runtime,
                    InteractionResponse(
                        interaction_id=interaction_id,
                        capabilities=[
                            {
                                "request_id": "unrelated-active",
                                "capability_id": "chromie.unrelated_active",
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
            target_execution = await submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id=interaction_id,
                    capabilities=[
                        {
                            "request_id": "later-exact-target",
                            "capability_id": "chromie.later_exact_target",
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
        self.assertEqual(_request_ids(receipt.selected_request_bindings), ())
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
        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        speech_provider = LocalSpeechCapabilityProvider(
            lambda _args: {
                "scheduled": True,
                "playback_started": True,
                "spoken": True,
            }
        )
        body_provider = MockCapabilityProvider("mock.body")
        runtime = CapabilityRuntime(registry)
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
            execution = await submit_and_wait_terminal(runtime,
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
                    capabilities=[
                        {
                            "request_id": "future-motion",
                            "capability_id": "soridormi.nod_yes",
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

        class SequentialProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "cancel-active":
                    target_started.set()
                    await asyncio.Event().wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.cancel",
                provider_id="mock.tool",
            )
        )
        registry.register(
            _tool_definition(
                capability_id="chromie.keep",
                provider_id="mock.tool",
            )
        )
        provider = SequentialProvider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        plan_metadata = {
            "canonical_plan_id": "plan-active",
            "canonical_plan_fingerprint": "fingerprint-active",
        }
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="specific-active",
                    capabilities=[
                        {
                            "request_id": "cancel-active",
                            "capability_id": "chromie.cancel",
                            "timing": "sequential",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-cancel"],
                            },
                        },
                        {
                            "request_id": "keep-after",
                            "capability_id": "chromie.keep",
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

        self.assertEqual(_request_ids(receipt.active_request_bindings), ("cancel-active",))
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

        class SharedProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.shared",
                provider_id="mock.tool",
            )
        )
        provider = SharedProvider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="specific-shared",
                    capabilities=[
                        {
                            "request_id": "shared-request",
                            "capability_id": "chromie.shared",
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

        self.assertEqual(_request_ids(receipt.selected_request_bindings), ())
        self.assertEqual(
            _request_ids(receipt.shared_owner_conflict_request_bindings),
            ("shared-request",),
        )
        self.assertEqual(provider.cancelled_request_ids, [])
        self.assertEqual(execution.status, "completed")

    async def test_specific_goal_stale_plan_binding_is_a_noop(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.bound_task",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="specific-stale",
                    capabilities=[
                        {
                            "request_id": "stale-request",
                            "capability_id": "chromie.bound_task",
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

        self.assertEqual(_request_ids(receipt.selected_request_bindings), ())
        self.assertEqual(
            _request_ids(receipt.stale_binding_request_bindings),
            ("stale-request",),
        )
        self.assertEqual(provider.cancelled_request_ids, [])
        self.assertEqual(execution.status, "completed")

    async def test_specific_physical_goal_reports_provider_scope_widening(
        self,
    ) -> None:
        both_started = asyncio.Event()
        started_count = 0

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                nonlocal started_count
                started_count += 1
                if started_count == 2:
                    both_started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled motion resumed")

        definition_a = _body_definition(
            capability_id="soridormi.motion_a",
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
            update={"capability_id": "soridormi.motion_b"}
        )
        registry = CapabilityRegistry()
        registry.register(definition_a)
        registry.register(definition_b)
        provider = Provider("mock.body")
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)
        plan_metadata = {
            "canonical_plan_id": "plan-physical",
            "canonical_plan_fingerprint": "fingerprint-physical",
        }
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="specific-physical",
                    capabilities=[
                        {
                            "request_id": "motion-a",
                            "capability_id": definition_a.capability_id,
                            "timing": "parallel",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-a"],
                            },
                        },
                        {
                            "request_id": "motion-b",
                            "capability_id": definition_b.capability_id,
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
            _request_ids(receipt.selected_request_bindings),
            ("motion-a", "motion-b"),
        )
        self.assertEqual(
            receipt.affected_goal_ids,
            ("goal-a", "goal-b"),
        )
        self.assertEqual(execution.status, "cancelled")

    async def test_specific_speech_goal_reports_shared_output_widening(
        self,
    ) -> None:
        registry = CapabilityRegistry()
        for capability_id in ("chromie.speech-a", "chromie.speech-b"):
            registry.register(
                CapabilityDefinition(
                    capability_id=capability_id,
                    version="1.0.0",
                    provider_id="mock.output",
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    interruptible=True,
                    can_run_parallel=True,
                    cancellation_domains=("output",),
                    metadata={"cancellation_granularity": "global_domain"},
                )
            )
        runtime = CapabilityRuntime(registry)
        provider = MockCapabilityProvider("mock.output", delay_s=10.0)
        runtime.register_provider(provider)
        plan_metadata = {
            "canonical_plan_id": "plan-speech",
            "canonical_plan_fingerprint": "fingerprint-speech",
        }
        first = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="speech-a",
                    capabilities=[
                        {
                            "request_id": "speech-request-a",
                            "capability_id": "chromie.speech-a",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-speech-a"],
                            },
                        }
                    ],
                )
            )
        )
        second = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="speech-b",
                    capabilities=[
                        {
                            "request_id": "speech-request-b",
                            "capability_id": "chromie.speech-b",
                            "metadata": {
                                **plan_metadata,
                                "source_goal_ids": ["goal-speech-b"],
                            },
                        }
                    ],
                )
            )
        )
        for _ in range(100):
            if len(provider.calls) == 2:
                break
            await asyncio.sleep(0.001)

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-cancel-speech-a",
                requested_scope="specific_goal",
                foreground_interaction_id="speech-a",
                target_goal_ids=("goal-speech-a",),
                expected_plan_id="plan-speech",
                expected_plan_fingerprint="fingerprint-speech",
            )
        )
        await asyncio.gather(first, second)

        self.assertTrue(receipt.widened)
        self.assertEqual(receipt.effective_scope, "output_only")
        self.assertEqual(
            receipt.widening_reason,
            "provider_supports_only_global_output_cancel",
        )
        self.assertEqual(
            _request_ids(receipt.selected_request_bindings),
            ("speech-request-a", "speech-request-b"),
        )
        self.assertEqual(
            receipt.affected_goal_ids,
            ("goal-speech-a", "goal-speech-b"),
        )

    async def test_current_interaction_scope_does_not_cancel_another_interaction(
        self,
    ) -> None:
        started: dict[str, asyncio.Event] = {
            "cancel": asyncio.Event(),
            "keep": asyncio.Event(),
        }
        release_keep = asyncio.Event()

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started[context.interaction_id].set()
                if context.interaction_id == "keep":
                    await release_keep.wait()
                    return await MockCapabilityProvider.execute(
                        self,
                        request,
                        definition,
                        context,
                    )
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.long_task",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)
        cancel_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="cancel",
                    capabilities=[
                        {
                            "request_id": "cancel-request",
                            "capability_id": "chromie.long_task",
                        }
                    ],
                )
            )
        )
        keep_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="keep",
                    capabilities=[
                        {
                            "request_id": "keep-request",
                            "capability_id": "chromie.long_task",
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
            _request_ids(receipt.selected_request_bindings),
            ("cancel-request",),
        )
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(kept.status, "completed")

    async def test_concurrent_execute_rejects_reused_interaction_id(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        registry.register(
            _tool_definition(
                capability_id="chromie.long_task",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        first = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="reused-interaction",
                    capabilities=[
                        {
                            "request_id": "first-request",
                            "capability_id": "chromie.long_task",
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
            await submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="reused-interaction",
                    capabilities=[
                        {
                            "request_id": "second-request",
                            "capability_id": "chromie.long_task",
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

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                await release.wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        definition = _body_definition(interruptible=False)
        registry = CapabilityRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="non-interruptible",
                    capabilities=[
                        {
                            "request_id": "cannot-interrupt",
                            "capability_id": definition.capability_id,
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
            _request_ids(receipt.non_interruptible_request_bindings),
            ("cannot-interrupt",),
        )
        self.assertEqual(_request_ids(receipt.cancel_requested_request_bindings), ())
        release.set()
        execution = await execution_task
        self.assertEqual(execution.status, "completed")

    async def test_current_scope_terminalizes_every_queued_sequential_request(
        self,
    ) -> None:
        started = asyncio.Event()

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                if request.request_id == "active-barrier":
                    started.set()
                    await asyncio.Event().wait()
                return await MockCapabilityProvider.execute(
                    self,
                    request,
                    definition,
                    context,
                )

        registry = CapabilityRegistry()
        barrier_definition = _tool_definition(
            capability_id="chromie.barrier",
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
                capability_id="chromie.queued",
                provider_id="mock.tool",
            )
        )
        provider = Provider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(
            LocalSpeechCapabilityProvider(
                lambda _args: {
                    "scheduled": True,
                    "playback_started": True,
                    "spoken": True,
                }
            )
        )
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="current-sequential",
                    speech=[
                        {
                            "id": "completed-pre-action",
                            "text": "Starting.",
                            "timing": "sequential",
                        }
                    ],
                    capabilities=[
                        {
                            "request_id": "active-barrier",
                            "capability_id": "chromie.barrier",
                            "timing": "sequential",
                            "args": {
                                "metadata": {
                                    "abort_remaining_on_failure": True,
                                }
                            },
                        },
                        {
                            "request_id": "queued-after-barrier",
                            "capability_id": "chromie.queued",
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
            _request_ids(receipt.queued_request_bindings),
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

        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        speech_provider = LocalSpeechCapabilityProvider(speak)
        body_provider = MockCapabilityProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
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
                    capabilities=[
                        {
                            "request_id": "motion-after-speech",
                            "capability_id": "soridormi.nod_yes",
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
            _request_ids(receipt.selected_request_bindings),
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

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                raise ConnectionError("physical cancel failed")

        definition = _body_definition()
        registry = CapabilityRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="cancel-failure",
                    capabilities=[
                        {
                            "request_id": "motion-unknown",
                            "capability_id": definition.capability_id,
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
            _provider_failure_texts(receipt),
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

        class Provider(MockCapabilityProvider):
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

        registry = CapabilityRegistry()
        registry.register(_body_definition())
        provider = Provider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="concurrent-cancel-failure",
                    capabilities=[
                        {
                            "request_id": "motion-concurrent-failure",
                            "capability_id": "soridormi.nod_yes",
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
                _provider_failure_texts(receipt),
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

        class Provider(MockCapabilityProvider):
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
        registry = CapabilityRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="distinct-turn-shared-cancel",
                    capabilities=[
                        {
                            "request_id": "motion-shared-in-flight",
                            "capability_id": definition.capability_id,
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
        self.assertEqual(_provider_failure_texts(first_receipt), ())
        self.assertEqual(_provider_failure_texts(second_receipt), ())
        self.assertEqual(
            _request_ids(first_receipt.cancel_requested_request_bindings),
            ("motion-shared-in-flight",),
        )
        self.assertEqual(
            _request_ids(second_receipt.cancel_requested_request_bindings),
            ("motion-shared-in-flight",),
        )
        self.assertEqual(execution.status, "cancelled")

    async def test_completed_success_cancel_is_reused_for_same_context(
        self,
    ) -> None:
        started = asyncio.Event()
        release_execution = asyncio.Event()
        cancel_completed = asyncio.Event()

        class Provider(MockCapabilityProvider):
            cancel_attempts = 0

            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                started.set()
                while not release_execution.is_set():
                    try:
                        await release_execution.wait()
                    except asyncio.CancelledError:
                        continue
                return await MockCapabilityProvider.execute(
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
        registry = CapabilityRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        active_key = ("completed-success-reuse", "motion-success-reuse")
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id=active_key[0],
                    capabilities=[
                        {
                            "request_id": active_key[1],
                            "capability_id": definition.capability_id,
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
        self.assertEqual(_provider_failure_texts(first_receipt), ())
        self.assertEqual(_provider_failure_texts(second_receipt), ())
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

        class Provider(MockCapabilityProvider):
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
        registry = CapabilityRegistry()
        registry.register(definition)
        provider = Provider("mock.body")
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(provider)
        first_execution = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="global-epoch-first",
                    capabilities=[
                        {
                            "request_id": "motion-first-epoch",
                            "capability_id": definition.capability_id,
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
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="global-epoch-second",
                    capabilities=[
                        {
                            "request_id": "motion-second-epoch",
                            "capability_id": definition.capability_id,
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
            _request_ids(first_receipt.selected_request_bindings),
            ("motion-first-epoch",),
        )
        self.assertEqual(
            _request_ids(second_receipt.selected_request_bindings),
            ("motion-first-epoch", "motion-second-epoch"),
        )
        self.assertEqual(first_result.status, "cancelled")
        self.assertEqual(second_result.status, "cancelled")

    async def test_current_cancel_failure_still_terminalizes_queued_work(
        self,
    ) -> None:
        started = asyncio.Event()

        class Provider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.calls.append(request)
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled request resumed")

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                raise ConnectionError("current provider cancel failed")

        barrier_definition = _tool_definition(
            capability_id="chromie.current-barrier",
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
        registry = CapabilityRegistry()
        registry.register(barrier_definition)
        registry.register(
            _tool_definition(capability_id="chromie.current-queued")
        )
        provider = Provider("mock.tool")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id="current-cancel-failure",
                    capabilities=[
                        {
                            "request_id": "active-current-failure",
                            "capability_id": barrier_definition.capability_id,
                            "timing": "sequential",
                            "args": {
                                "metadata": {
                                    "abort_remaining_on_failure": True,
                                }
                            },
                        },
                        {
                            "request_id": "queued-current-failure",
                            "capability_id": "chromie.current-queued",
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
            _request_ids(receipt.queued_request_bindings),
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
        provider = MockCapabilityProvider("mock.body")
        registry = CapabilityRegistry()
        registry.register(_body_definition(capability_id="soridormi.nod_yes"))
        registry.register(_body_definition(capability_id="soridormi.express_attention"))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        await submit_and_wait_terminal(runtime,
            InteractionResponse(
                capabilities=[
                    {
                        "capability_id": "soridormi.nod_yes",
                        "args": {},
                        "timing": "sequential",
                    },
                    {
                        "capability_id": "soridormi.express_attention",
                        "args": {},
                        "timing": "sequential",
                    },
                ]
            )
        )

        self.assertEqual(
            [request.capability_id for request in provider.calls],
            ["soridormi.nod_yes", "soridormi.express_attention"],
        )

    async def test_after_capabilities_speech_waits_for_parallel_body_work(self) -> None:
        events: list[str] = []

        async def speak(args: dict[str, object]) -> dict[str, object]:
            events.append("speech")
            return {"spoken": True}

        class OrderedBodyProvider(MockCapabilityProvider):
            async def execute(self, request, definition, context):  # type: ignore[no-untyped-def]
                events.append("body_start")
                await asyncio.sleep(0.01)
                events.append("body_end")
                return await super().execute(request, definition, context)

        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(LocalSpeechCapabilityProvider(speak))
        runtime.register_provider(OrderedBodyProvider("mock.body"))

        await submit_and_wait_terminal(runtime,
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_capabilities"}],
                capabilities=[
                    {
                        "capability_id": "soridormi.nod_yes",
                        "args": {},
                        "timing": "parallel",
                    }
                ],
            )
        )

        self.assertEqual(events, ["body_start", "body_end", "speech"])

    async def test_preflight_rejects_unknown_invalid_and_unconfirmed_capabilities(self) -> None:
        provider = MockCapabilityProvider("mock.body")
        registry = CapabilityRegistry()
        registry.register(_body_definition(requires_confirmation=True))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        with self.assertRaisesRegex(ValueError, "unknown capability"):
            await submit_and_wait_terminal(runtime,
                InteractionResponse(capabilities=[{"capability_id": "missing.skill"}])
            )
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            await submit_and_wait_terminal(runtime,
                InteractionResponse(
                    capabilities=[
                        {
                            "capability_id": "soridormi.nod_yes",
                            "args": {"joint": "not-in-schema"},
                        }
                    ]
                )
            )
        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            await submit_and_wait_terminal(runtime,
                InteractionResponse(
                    capabilities=[{"request_id": "nod-1", "capability_id": "soridormi.nod_yes"}]
                )
            )
        self.assertEqual(provider.calls, [])

    async def test_confirmation_proof_allows_request(self) -> None:
        provider = MockCapabilityProvider("mock.body")
        registry = CapabilityRegistry()
        registry.register(_body_definition(requires_confirmation=True))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                capabilities=[{"request_id": "nod-1", "capability_id": "soridormi.nod_yes"}]
            ),
            authorization=RuntimeAuthorization(confirmed_request_ids={"nod-1"}),
        )

        self.assertEqual(execution.status, "completed")

    async def test_timeout_calls_provider_cancel(self) -> None:
        provider = MockCapabilityProvider("mock.body", delay_s=0.2)
        registry = CapabilityRegistry()
        registry.register(_body_definition(timeout_ms=10))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                capabilities=[{"request_id": "nod-1", "capability_id": "soridormi.nod_yes"}]
            )
        )

        self.assertEqual(execution.results[0].status, "timed_out")
        self.assertEqual(provider.cancelled_request_ids, ["nod-1"])

    async def test_cancel_failure_does_not_override_timeout(self) -> None:
        class FailingCancelProvider(MockCapabilityProvider):
            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                raise ConnectionError("provider disconnected during cancellation")

        provider = FailingCancelProvider("mock.body", delay_s=0.2)
        registry = CapabilityRegistry()
        registry.register(_body_definition(timeout_ms=10))
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                capabilities=[{"request_id": "nod-1", "capability_id": "soridormi.nod_yes"}]
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
        class FailingCancelProvider(MockCapabilityProvider):
            cancel_attempts = 0

            async def cancel(self, request, definition, context):  # type: ignore[no-untyped-def]
                self.cancel_attempts += 1
                raise ConnectionError("provider disconnected during cancellation")

        provider = FailingCancelProvider("mock.body", delay_s=5)
        registry = CapabilityRegistry()
        registry.register(_body_definition())
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    capabilities=[
                        {
                            "request_id": "nod-1",
                            "capability_id": "soridormi.nod_yes",
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
        speech_provider = LocalSpeechCapabilityProvider(
            lambda args: asyncio.sleep(5, result={"spoken": True})
        )
        body_provider = MockCapabilityProvider("mock.body", delay_s=5)
        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(_body_definition())
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)

        task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    speech=[{"id": "speech-1", "text": "Hello."}],
                    capabilities=[
                        {
                            "request_id": "nod-1",
                            "capability_id": "soridormi.nod_yes",
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
        provider = MockCapabilityProvider("mock.body", delay_s=5)
        registry = CapabilityRegistry()
        registry.register(
            _body_definition(
                capability_id="soridormi.nod_yes",
                exclusive_group=None,
            )
        )
        registry.register(
            _body_definition(
                capability_id="soridormi.express_attention",
                exclusive_group=None,
            )
        )
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)

        task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    capabilities=[
                        {
                            "request_id": "first-active",
                            "capability_id": "soridormi.nod_yes",
                            "timing": "sequential",
                        },
                        {
                            "request_id": "second-unstarted",
                            "capability_id": "soridormi.express_attention",
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



if __name__ == "__main__":
    unittest.main()
