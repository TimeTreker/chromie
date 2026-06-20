from __future__ import annotations

import asyncio
import time
import unittest

from shared.chromie_contracts.agent import AgentResult, SpeechItem
from shared.chromie_contracts.action import ActionCommand
from shared.chromie_contracts.interaction import InteractionResponse

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
    )


class SkillRuntimeTests(unittest.IsolatedAsyncioTestCase):
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
                await super().cancel(request, definition, context)

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

        await runtime.cancel_all()
        results = await asyncio.gather(*executions)

        self.assertEqual(set(cancelled_interactions), {"interaction-a", "interaction-b"})
        self.assertEqual([result.status for result in results], ["cancelled", "cancelled"])

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
        self.assertIn("keep", status.active_interaction_ids)
        self.assertNotIn("cancel", status.active_interaction_ids)
        self.assertEqual(kept.status, "completed")

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
        self.assertIn("speech-1", speech_provider.cancelled_request_ids)
        self.assertIn("nod-1", body_provider.cancelled_request_ids)

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
