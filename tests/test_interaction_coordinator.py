from __future__ import annotations

import asyncio
import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
)
from orchestrator.runtime.interaction_ledger import InteractionLedger
from shared.chromie_contracts.interaction import InteractionResponse, CapabilityRequest
from shared.chromie_contracts.plan import FastPlannerCompleteResponseAct
from shared.chromie_contracts.reflex import CancellationDirective



def _request_ids(bindings):  # type: ignore[no-untyped-def]
    return tuple(item.request_id for item in bindings)


def _provider_failure_texts(receipt):  # type: ignore[no-untyped-def]
    return tuple(
        f"{item.request_id}:{item.error}"
        for item in receipt.provider_cancel_failure_evidence
    )


async def _execute_to_terminal(coordinator, response, *, session_id, confirmed_request_ids=None):
    dispatch = await coordinator.submit_response(
        response,
        session_id=session_id,
        confirmed_request_ids=confirmed_request_ids,
    )
    return await coordinator.wait_dispatch(dispatch)


class _SoridormiInvoker:
    def __init__(
        self,
        *,
        execute_outcome: ToolCallOutcome | None = None,
        monitor_outcome: ToolCallOutcome | None = None,
        execute_delay_s: float = 0,
        requires_confirmation: bool = False,
        provider_mode: str = "opaque-backend",
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []
        self.execute_outcome = execute_outcome
        self.monitor_outcome = monitor_outcome
        self.execute_delay_s = execute_delay_s
        self.requires_confirmation = requires_confirmation
        self.provider_mode = provider_mode

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append((tool_name, args, context))
        if tool_name == "soridormi.skill.list":
            return ToolCallOutcome.success(
                {
                    "mode": self.provider_mode,
                    "skills": [
                        {
                            "skill_id": "nod_yes",
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
                            "interruptible": True,
                            "requires_confirmation": self.requires_confirmation,
                        }
                    ],
                }
            )
        if tool_name == "soridormi.skill.create_plan":
            return ToolCallOutcome.success({"plan_id": "plan-1"})
        if tool_name == "soridormi.safety.monitor_motion":
            if self.monitor_outcome is not None:
                return self.monitor_outcome
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.skill.execute_plan":
            if self.execute_delay_s:
                await asyncio.sleep(self.execute_delay_s)
            if self.execute_outcome is not None:
                return self.execute_outcome
            return ToolCallOutcome.success(
                {"completed": True, "skill_id": "nod_yes"}
            )
        if tool_name == "soridormi.motion.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        if tool_name == "soridormi.safety.emergency_stop":
            return ToolCallOutcome.success(
                {
                    "stopped": True,
                    "emergency": True,
                    "safe_idle": True,
                }
            )
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


class InteractionRuntimeCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivered_fast_communicative_act_is_recorded_for_continuity(self) -> None:
        recorded: list[tuple[str | None, str, dict[str, Any]]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {
                "scheduled": True,
                "playback_started": True,
                "voice_released": True,
            },
            communicative_delivery_recorder=(
                lambda sid, text, metadata: recorded.append((sid, text, metadata))
            ),
        )

        ready = await coordinator.start_fast_planner_communicative_act(
            FastPlannerCompleteResponseAct.model_validate({
                "activity_id": "a1",
                "role": "complete_response",
                "speech_act": "respond",
                "text": "Hello there.",
                "truth_stage": "context_grounded",
                "source_responsibility_refs": ["r1"],
            }),
            session_id="sid-continuity",
            turn_id="turn-continuity",
            language="en-US",
        )
        await ready.task
        await asyncio.sleep(0)

        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0][0:2], ("sid-continuity", "Hello there."))
        self.assertEqual(
            recorded[0][2]["source"],
            "fast_planner_communicative_delivery",
        )

    async def test_completed_fast_response_can_bind_to_later_canonical_goal(self) -> None:
        completed: list[tuple[str | None, list[str], dict[str, Any]]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {
                "scheduled": True,
                "playback_started": True,
                "voice_released": True,
            },
            communicative_goal_completion_recorder=(
                lambda sid, goal_ids, metadata: completed.append(
                    (sid, goal_ids, metadata)
                )
            ),
        )

        ready = await coordinator.start_fast_planner_communicative_act(
            FastPlannerCompleteResponseAct.model_validate({
                "activity_id": "a-complete",
                "role": "complete_response",
                "speech_act": "respond",
                "text": "你好呀！",
                "truth_stage": "context_grounded",
                "source_responsibility_refs": ["r1"],
            }),
            session_id="sid-late-bind",
            turn_id="turn-late-bind",
            language="zh-CN",
        )
        # Fast Planner Communicative Activity may finish before Goal Association has canonical Goal IDs.
        await ready.task
        bound = coordinator.bind_fast_planner_communicative_execution(
            ready,
            session_id="sid-late-bind",
            goal_ids_by_responsibility={"r1": ["goal-greeting"]},
        )
        await asyncio.sleep(0)

        self.assertEqual(bound, ["goal-greeting"])
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0][0], "sid-late-bind")
        self.assertEqual(completed[0][1], ["goal-greeting"])
        self.assertEqual(
            completed[0][2]["source"],
            "fast_planner_communicative_completion",
        )
        self.assertEqual(completed[0][2]["delivery_role"], "complete_response")
        self.assertEqual(completed[0][2]["source_responsibility_refs"], ["r1"])

    async def test_failed_fast_communicative_act_is_not_recorded(self) -> None:
        recorded: list[tuple[str | None, str, dict[str, Any]]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": False, "playback_started": False},
            communicative_delivery_recorder=(
                lambda sid, text, metadata: recorded.append((sid, text, metadata))
            ),
        )

        ready = await coordinator.start_fast_planner_communicative_act(
            FastPlannerCompleteResponseAct.model_validate({
                "activity_id": "a1",
                "role": "complete_response",
                "speech_act": "respond",
                "text": "Hello there.",
                "truth_stage": "context_grounded",
                "source_responsibility_refs": ["r1"],
            }),
            session_id="sid-continuity",
            turn_id="turn-continuity",
            language="en-US",
        )
        await ready.task
        await asyncio.sleep(0)

        self.assertEqual(recorded, [])

    async def test_emergency_stop_uses_dedicated_soridormi_control(self) -> None:
        invoker = _SoridormiInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": True},
            soridormi_invoker=invoker,
        )

        evidence = await coordinator.emergency_stop(
            reason="user requested emergency stop"
        )

        self.assertEqual(evidence["status"], "success")
        self.assertTrue(evidence["output"]["safe_idle"])
        tool_name, args, context = invoker.calls[-1]
        self.assertEqual(
            tool_name,
            "soridormi.safety.emergency_stop",
        )
        self.assertEqual(
            args,
            {"reason": "user requested emergency stop"},
        )
        self.assertIsNotNone(context)
        self.assertTrue(context.allow_safety_controls)

    async def test_emergency_stop_fails_closed_when_soridormi_is_disabled(
        self,
    ) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": True},
        )

        evidence = await coordinator.emergency_stop(
            reason="user requested emergency stop"
        )

        self.assertEqual(evidence["status"], "unavailable")
        self.assertEqual(
            evidence["reason"],
            "soridormi_invoker_disabled",
        )

    async def test_emergency_stop_rejects_success_without_safe_postcondition(
        self,
    ) -> None:
        class UnconfirmedInvoker(_SoridormiInvoker):
            def __init__(self, output: dict[str, Any]) -> None:
                super().__init__()
                self.output = output

            async def invoke(
                self,
                tool_name: str,
                args: dict[str, Any],
                *,
                context: ToolInvocationContext | None = None,
            ) -> ToolCallOutcome:
                if tool_name == "soridormi.safety.emergency_stop":
                    return ToolCallOutcome.success(self.output)
                return await super().invoke(
                    tool_name,
                    args,
                    context=context,
                )

        for output in (
            {"stopped": False, "emergency": True, "safe_idle": True},
            {"stopped": True, "emergency": True},
        ):
            with self.subTest(output=output):
                coordinator = InteractionRuntimeCoordinator(
                    lambda _args: {"scheduled": True},
                    soridormi_invoker=UnconfirmedInvoker(output),
                )
                evidence = await coordinator.emergency_stop(reason="stop")
                self.assertEqual(evidence["status"], "unconfirmed")
                self.assertEqual(
                    evidence["reason"],
                    "emergency_stop_postcondition_unconfirmed",
                )
                self.assertFalse(
                    evidence.get("postcondition_confirmed", False)
                )

    async def test_speech_only_does_not_require_soridormi(self) -> None:
        scheduled: list[dict[str, Any]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: scheduled.append(args) or {"scheduled": True}
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(speech=[{"text": "Hello."}]),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(scheduled[0]["text"], "Hello.")
        self.assertEqual(scheduled[0]["metadata"]["session_id"], "sid-1")

    async def test_trusted_runtime_records_only_prepared_committed_requests(
        self,
    ) -> None:
        ledger = InteractionLedger()
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": True},
            interaction_ledger=ledger,
        )
        response = InteractionResponse(
            interaction_id="interaction-1",
            capabilities=[
                CapabilityRequest(
                    request_id="speak-1",
                    capability_id="chromie.speak",
                    args={"text": "Hello."},
                    metadata={
                        "execution_lane": "vocal",
                        "source_goal_ids": ["goal-greet"],
                    },
                )
            ],
            metadata={
                "user_turn_envelope": {"turn_id": "turn-1"},
            },
        )

        result = await _execute_to_terminal(coordinator, response, session_id="sid-1")

        self.assertEqual(result.status, "completed")
        context = ledger.context("sid-1", goal_ids=["goal-greet"])
        self.assertEqual(
            [item["event_type"] for item in context.vocal_actions],
            ["vocal_action_committed"],
        )
        self.assertEqual(
            context.unresolved[0]["waiting_for"],
            "vocal_action_terminal_result",
        )

    async def test_trusted_runtime_does_not_record_a_suppressed_request(
        self,
    ) -> None:
        ledger = InteractionLedger()
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": True},
            interaction_ledger=ledger,
        )
        response = InteractionResponse(
            interaction_id="interaction-blocked",
            capabilities=[
                CapabilityRequest(
                    request_id="interrupt-leak",
                    capability_id="session.interrupt",
                    args={},
                    metadata={"source_goal_ids": ["goal-blocked"]},
                )
            ],
            metadata={
                "planning_result": "blocked",
                "user_turn_envelope": {"turn_id": "turn-blocked"},
            },
        )

        result = await _execute_to_terminal(coordinator, response, session_id="sid-1")

        self.assertEqual(result.status, "completed")
        self.assertEqual(ledger.events("sid-1"), [])


    async def test_prepare_response_suppresses_effectful_skills_when_structured_planner_blocks(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True}
        )

        prepared = coordinator.prepare_response(
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "walk-leak",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15.0, "speed": "quick"},
                    }
                ],
                metadata={
                    "capability_decision": "clarify",
                    "planning_result": "needs_clarification",
                },
            ),
            session_id="sid-structured-block",
        )

        self.assertEqual(prepared.capabilities, [])
        self.assertFalse(prepared.requires_confirmation)
        self.assertTrue(prepared.metadata["structured_planning_execution_suppressed"])
        self.assertEqual(
            prepared.metadata["suppressed_capability_ids"],
            ["soridormi.walk_forward"],
        )


    async def test_post_execution_speech_is_not_classified_from_wording(self) -> None:
        coordinator = InteractionRuntimeCoordinator(lambda args: {"scheduled": True})

        for text in (
            "I walked forward and finished the turn.",
            "I've finished walking forward and turning.",
            "第一个目标执行失败。",
        ):
            with self.subTest(text=text):
                prepared = coordinator.prepare_response(
                    InteractionResponse(
                        speech=[
                            {
                                "text": text,
                                "metadata": {
                                    "source": (
                                        "evidence_bound_tool_result_interpretation"
                                    ),
                                    "phase": "post_execution",
                                },
                            }
                        ],
                        metadata={
                            "source": "evidence_bound_tool_result_interpretation",
                            "phase": "post_execution",
                        },
                    ),
                    session_id="sid-post-execution",
                )

                self.assertEqual(prepared.status, "ok")
                self.assertEqual(prepared.speech[0].text, text)





    async def test_prepare_response_adds_static_preflight_audit(self) -> None:
        coordinator = InteractionRuntimeCoordinator(lambda args: {"scheduled": True})

        prepared = coordinator.prepare_response(
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "local-unknown",
                        "capability_id": "chromie.unknown",
                    },
                    {
                        "request_id": "body-deferred",
                        "capability_id": "soridormi.nod_yes",
                    },
                ]
            ),
            session_id="sid-preflight",
        )

        preflight = prepared.metadata["preflight_validation"]
        by_request = {
            item["request_id"]: item for item in preflight["items"]
        }
        self.assertEqual(
            by_request["local-unknown"]["status"],
            "blocked",
        )
        self.assertEqual(
            by_request["local-unknown"]["reason_code"],
            "unknown_capability",
        )
        self.assertEqual(
            by_request["body-deferred"]["status"],
            "deferred",
        )
        self.assertEqual(preflight["summary"]["blocked_count"], 1)
        self.assertEqual(preflight["summary"]["deferred_count"], 1)

        self.assertNotIn("task_proposal_ledger", prepared.metadata)

    async def test_prepare_response_preflight_uses_loaded_catalog_and_confirmation(
        self,
    ) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(requires_confirmation=True),
        )
        response = InteractionResponse(
            capabilities=[
                {
                    "request_id": "nod-1",
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                }
            ]
        )

        request_ids = await coordinator.confirmation_request_ids(response)
        self.assertEqual(request_ids, {"nod-1"})

        needs_confirmation = coordinator.prepare_response(
            response,
            session_id="sid-preflight-confirm",
        )
        item = needs_confirmation.metadata["preflight_validation"]["items"][0]
        self.assertEqual(item["status"], "needs_confirmation")
        self.assertEqual(item["reason_code"], "confirmation_required")

        confirmed = coordinator.prepare_response(
            response,
            session_id="sid-preflight-confirmed",
            confirmed_request_ids={"nod-1"},
        )
        confirmed_item = confirmed.metadata["preflight_validation"]["items"][0]
        self.assertEqual(confirmed_item["status"], "passed")

    async def test_session_interrupt_completes_as_local_control(self) -> None:
        scheduled: list[dict[str, Any]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: scheduled.append(args) or {"scheduled": True}
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "interrupt-1",
                        "capability_id": "session.interrupt",
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.results[0].capability_id, "session.interrupt")
        self.assertEqual(result.results[0].provider_id, "chromie.session_control")
        self.assertEqual(
            result.results[0].output,
            {"control": "interrupt_acknowledged"},
        )
        self.assertEqual(scheduled, [])

    async def test_provider_body_skill_discovers_catalog_and_executes(self) -> None:
        invoker = _SoridormiInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            [call[0] for call in invoker.calls],
            [
                "soridormi.skill.list",
                "soridormi.skill.create_plan",
                "soridormi.safety.monitor_motion",
                "soridormi.skill.execute_plan",
            ],
        )
        self.assertFalse(invoker.calls[-1][2].confirmed)

    async def test_existing_body_skill_reuses_fresh_catalog(self) -> None:
        invoker = _SoridormiInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )

        for request_id in ["nod-1", "nod-2"]:
            result = await _execute_to_terminal(coordinator,
                InteractionResponse(
                    capabilities=[
                        {
                            "request_id": request_id,
                            "capability_id": "soridormi.nod_yes",
                            "args": {"count": 1},
                        }
                    ]
                ),
                session_id=f"sid-{request_id}",
            )
            self.assertEqual(result.status, "completed")

        self.assertEqual(
            [call[0] for call in invoker.calls].count("soridormi.skill.list"),
            1,
        )

    async def test_unknown_body_skill_forces_catalog_refresh(self) -> None:
        class ExpandingCatalogInvoker(_SoridormiInvoker):
            def __init__(self) -> None:
                super().__init__()
                self.catalog_calls = 0
                self.planned_skill_id = "nod_yes"

            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    self.catalog_calls += 1
                    skills = [
                        {
                            "skill_id": "nod_yes",
                            "available": True,
                            "parameters_schema": {"type": "object"},
                            "interruptible": True,
                        }
                    ]
                    if self.catalog_calls >= 2:
                        skills.append(
                            {
                                "skill_id": "wave_hand",
                                "available": True,
                                "parameters_schema": {"type": "object"},
                                "interruptible": True,
                            }
                        )
                    return ToolCallOutcome.success({"mode": "sim", "skills": skills})
                if tool_name == "soridormi.skill.create_plan":
                    self.planned_skill_id = str(args["skill_id"])
                    return ToolCallOutcome.success({"plan_id": f"plan-{self.planned_skill_id}"})
                if tool_name == "soridormi.safety.monitor_motion":
                    return ToolCallOutcome.success({"ok": True, "event": None})
                if tool_name == "soridormi.skill.execute_plan":
                    return ToolCallOutcome.success(
                        {"completed": True, "skill_id": self.planned_skill_id}
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        invoker = ExpandingCatalogInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )

        first = await _execute_to_terminal(coordinator,
            InteractionResponse(capabilities=[{"capability_id": "soridormi.nod_yes"}]),
            session_id="sid-nod",
        )
        second = await _execute_to_terminal(coordinator,
            InteractionResponse(capabilities=[{"capability_id": "soridormi.wave_hand"}]),
            session_id="sid-wave",
        )

        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertEqual(invoker.catalog_calls, 2)
        self.assertEqual(
            [
                call[1]["skill_id"]
                for call in invoker.calls
                if call[0] == "soridormi.skill.create_plan"
            ],
            ["nod_yes", "wave_hand"],
        )

    async def test_catalog_refresh_ttl_can_force_periodic_reload(self) -> None:
        class VersionedCatalogInvoker(_SoridormiInvoker):
            def __init__(self) -> None:
                super().__init__()
                self.catalog_calls = 0

            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                if tool_name == "soridormi.skill.list":
                    self.calls.append((tool_name, args, context))
                    self.catalog_calls += 1
                    return ToolCallOutcome.success(
                        {
                            "mode": "sim",
                            "skills": [
                                {
                                    "skill_id": "nod_yes",
                                    "available": True,
                                    "version": f"1.0.{self.catalog_calls}",
                                    "parameters_schema": {"type": "object"},
                                    "interruptible": True,
                                }
                            ],
                        }
                    )
                return await super().invoke(tool_name, args, context=context)

        invoker = VersionedCatalogInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )
        coordinator._catalog_refresh_ttl_s = 0.0

        for request_id in ["nod-1", "nod-2"]:
            result = await _execute_to_terminal(coordinator,
                InteractionResponse(
                    capabilities=[
                        {
                            "request_id": request_id,
                            "capability_id": "soridormi.nod_yes",
                        }
                    ]
                ),
                session_id=f"sid-{request_id}",
            )
            self.assertEqual(result.status, "completed")

        self.assertEqual(invoker.catalog_calls, 2)
        self.assertEqual(
            coordinator.registry.get("soridormi.nod_yes").version,
            "1.0.2",
        )

    async def test_catalog_absent_requested_skill_forces_refresh(self) -> None:
        class FlappingCatalogInvoker(_SoridormiInvoker):
            def __init__(self) -> None:
                super().__init__()
                self.catalog_calls = 0
                self.planned_skill_id = "nod_yes"

            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    self.catalog_calls += 1
                    skills = [
                        {
                            "skill_id": "nod_yes",
                            "available": True,
                            "parameters_schema": {"type": "object"},
                            "interruptible": True,
                        }
                    ]
                    if self.catalog_calls != 2:
                        skills.append(
                            {
                                "skill_id": "wave_hand",
                                "available": True,
                                "parameters_schema": {"type": "object"},
                                "interruptible": True,
                            }
                        )
                    return ToolCallOutcome.success({"mode": "sim", "skills": skills})
                if tool_name == "soridormi.skill.create_plan":
                    self.planned_skill_id = str(args["skill_id"])
                    return ToolCallOutcome.success({"plan_id": f"plan-{self.planned_skill_id}"})
                if tool_name == "soridormi.safety.monitor_motion":
                    return ToolCallOutcome.success({"ok": True, "event": None})
                if tool_name == "soridormi.skill.execute_plan":
                    return ToolCallOutcome.success(
                        {"completed": True, "skill_id": self.planned_skill_id}
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        invoker = FlappingCatalogInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )

        first = await _execute_to_terminal(coordinator,
            InteractionResponse(capabilities=[{"capability_id": "soridormi.wave_hand"}]),
            session_id="sid-wave-1",
        )
        await coordinator.refresh_soridormi_catalog(force=True)
        self.assertTrue(
            coordinator.registry.get("soridormi.wave_hand")
            .metadata["catalog_absent"]
        )

        second = await _execute_to_terminal(coordinator,
            InteractionResponse(capabilities=[{"capability_id": "soridormi.wave_hand"}]),
            session_id="sid-wave-2",
        )

        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertEqual(invoker.catalog_calls, 3)
        self.assertTrue(coordinator.registry.get("soridormi.wave_hand").available)

    async def test_provider_confirmation_is_not_changed_by_backend_metadata(self) -> None:
        for provider_mode in ("sim", "hardware", "opaque-backend"):
            with self.subTest(provider_mode=provider_mode):
                coordinator = InteractionRuntimeCoordinator(
                    lambda args: {"scheduled": True},
                    soridormi_invoker=_SoridormiInvoker(
                        requires_confirmation=True,
                        provider_mode=provider_mode,
                    ),
                )
                response = InteractionResponse(
                    capabilities=[
                        {
                            "request_id": "nod-1",
                            "capability_id": "soridormi.nod_yes",
                            "args": {"count": 2},
                        }
                    ]
                )

                self.assertEqual(
                    await coordinator.confirmation_request_ids(response),
                    {"nod-1"},
                )

    async def test_semantic_alternative_requires_confirmation_independent_of_backend(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(),
        )
        response = InteractionResponse(
            capabilities=[
                {
                    "request_id": "nod-alternative",
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                    "requires_confirmation": True,
                }
            ],
            metadata={"semantic_plan_confirmation_required": True},
        )

        self.assertEqual(
            await coordinator.confirmation_request_ids(response),
            {"nod-alternative"},
        )

    async def test_body_capability_fails_closed_when_provider_is_disabled(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True}
        )

        result = await _execute_to_terminal(
            coordinator,
            InteractionResponse(
                capabilities=[{"capability_id": "soridormi.nod_yes"}]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "provider_disabled")

    async def test_catalog_failure_becomes_terminal_evidence_without_host_speech(self) -> None:
        class CatalogFailureInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.failed(
                        "provider restarting",
                        retryable=True,
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=CatalogFailureInvoker(),
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "catalog_unavailable")
        self.assertEqual(spoken, [])

    async def test_legacy_optional_cue_metadata_cannot_hide_terminal_failure(self) -> None:
        class CatalogFailureInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.failed(
                        "provider restarting",
                        retryable=True,
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=CatalogFailureInvoker(),
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "attention-1",
                        "capability_id": "soridormi.express_attention",
                    }
                ],
                metadata={"optional_body" + "_cue": True},
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "catalog_unavailable")
        self.assertEqual(spoken, [])

    async def test_legacy_optional_cue_metadata_cannot_bypass_confirmation(self) -> None:
        class AttentionInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.success(
                        {
                            "mode": "hardware",
                            "skills": [
                                {
                                    "skill_id": "express_attention",
                                    "available": True,
                                    "requires_confirmation": True,
                                    "parameters_schema": {"type": "object"},
                                }
                            ],
                        }
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=AttentionInvoker(),
        )

        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            await _execute_to_terminal(coordinator,
                InteractionResponse(
                    capabilities=[
                        {
                            "request_id": "attention-1",
                            "capability_id": "soridormi.express_attention",
                            "requires_confirmation": True,
                        }
                    ],
                    metadata={"optional_body" + "_cue": True},
                ),
                session_id="sid-optional-confirmation",
            )

        self.assertEqual(spoken, [])

    async def test_unavailable_catalog_capability_becomes_terminal_failure(
        self,
    ) -> None:
        class UnavailableSkillInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.success(
                        {
                            "mode": "sim",
                            "skills": [
                                {
                                    "skill_id": "nod_yes",
                                    "available": False,
                                    "unavailable_reason": "provider not calibrated",
                                    "parameters_schema": {"type": "object"},
                                }
                            ],
                        }
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        invoker = UnavailableSkillInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "capability_unavailable")
        self.assertEqual(spoken, [])
        self.assertEqual(
            [call[0] for call in invoker.calls],
            ["soridormi.skill.list"],
        )

    async def test_request_bound_confirmation_authorizes_only_exact_request(self) -> None:
        invoker = _SoridormiInvoker(requires_confirmation=True)
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )
        response = InteractionResponse(
            capabilities=[
                {
                    "request_id": "nod-1",
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                }
            ]
        )

        request_ids = await coordinator.confirmation_request_ids(response)
        self.assertEqual(request_ids, {"nod-1"})

        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            await _execute_to_terminal(coordinator, response, session_id="sid-1")

        result = await _execute_to_terminal(coordinator,
            response,
            session_id="sid-2",
            confirmed_request_ids=request_ids,
        )

        self.assertEqual(result.status, "completed")
        self.assertTrue(invoker.calls[-1][2].confirmed)

    async def test_failed_body_capability_suppresses_unverified_completion_speech(
        self,
    ) -> None:
        spoken: list[dict[str, Any]] = []
        invoker = _SoridormiInvoker(
            execute_outcome=ToolCallOutcome.success(
                {"completed": False, "skill_id": "nod_yes"}
            )
        )
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(args) or {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                speech=[
                    {"text": "Starting.", "timing": "immediate"},
                    {"text": "Done.", "timing": "after_capabilities"},
                ],
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-failure",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual([item["text"] for item in spoken], ["Starting."])
        self.assertNotIn("Done.", [item["text"] for item in spoken])

    async def test_cognitive_body_failure_defers_terminal_speech_to_turn_closure(
        self,
    ) -> None:
        spoken: list[dict[str, Any]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(args) or {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(
                execute_outcome=ToolCallOutcome.success(
                    {"completed": False, "skill_id": "nod_yes"}
                )
            ),
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                speech=[
                    {"text": "Starting.", "timing": "immediate"},
                    {"text": "Done.", "timing": "after_capabilities"},
                ],
                capabilities=[
                    {
                        "request_id": "nod-cognitive",
                        "capability_id": "soridormi.nod_yes",
                    }
                ],
                metadata={
                    "language": "en-US",
                    "cognitive_runtime_apply": True,
                    "canonical_plan": {"plan_id": "plan-cognitive"},
                },
            ),
            session_id="sid-cognitive-failure",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual([item["text"] for item in spoken], ["Starting."])
        self.assertFalse(
            any(
                item["metadata"].get("source")
                == "host_body_failure_fallback"
                for item in spoken
            )
        )

    async def test_timed_out_body_capability_returns_terminal_evidence_without_host_speech(self) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(
                execute_outcome=ToolCallOutcome(
                    status="timeout",
                    error="simulated timeout",
                )
            ),
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[{"capability_id": "soridormi.nod_yes"}],
                metadata={"language": "zh-CN"},
            ),
            session_id="sid-timeout",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(spoken, [])
        self.assertEqual(result.results[0].status, "timed_out")

    async def test_refused_body_capability_reports_terminal_refusal_without_host_speech(self) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(
                monitor_outcome=ToolCallOutcome.success(
                    {"ok": False, "event": "workspace blocked"}
                )
            ),
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[{"capability_id": "soridormi.nod_yes"}],
                metadata={"language": "en-US"},
            ),
            session_id="sid-refused",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].status, "refused")
        self.assertEqual(spoken, [])

    async def test_successful_body_capability_still_defers_completion_wording_to_evidence(self) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(),
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_capabilities"}],
                capabilities=[{"capability_id": "soridormi.nod_yes"}],
            ),
            session_id="sid-success",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(spoken, [])

    async def test_task_graph_capability_executes_handler_and_defers_completion_wording(
        self,
    ) -> None:
        spoken: list[str] = []
        graphs: list[dict[str, Any]] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            graphs.append(graph)
            return {
                "graph_id": graph["graph_id"],
                "status": "success",
                "outcome_summary": "TaskGraph completed successfully.",
                "node_results": [],
                "events": [],
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_capabilities"}],
                capabilities=[
                    {
                        "request_id": "graph-1",
                        "capability_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
            ),
            session_id="sid-graph-success",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(graphs, [{"graph_id": "nav", "nodes": []}])
        self.assertEqual(spoken, [])
        self.assertEqual(result.results[0].capability_id, "chromie.task_graph.execute")
        self.assertEqual(result.results[0].status, "completed")

    async def test_failed_task_graph_suppresses_unverified_completion_speech(
        self,
    ) -> None:
        spoken: list[str] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            return {
                "graph_id": graph["graph_id"],
                "status": "failed",
                "outcome_summary": (
                    "TaskGraph failed at node go: "
                    "reason code: missing_navigation_pipeline"
                ),
                "node_results": [],
                "events": [],
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_capabilities"}],
                capabilities=[
                    {
                        "request_id": "graph-1",
                        "capability_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-graph-failure",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].status, "failed")
        self.assertEqual(result.results[0].reason_code, "task_graph_failed")
        self.assertIn("missing_navigation_pipeline", result.results[0].message)
        self.assertEqual(spoken, [])

    async def test_non_terminal_task_graph_result_fails_closed(self) -> None:
        for graph_status, expected_reason in (
            ("", "task_graph_missing_terminal_status"),
            ("pending", "task_graph_non_terminal_result"),
            ("running", "task_graph_non_terminal_result"),
            ("mystery", "task_graph_invalid_terminal_status"),
        ):
            with self.subTest(graph_status=graph_status):
                spoken: list[str] = []

                async def execute_graph(
                    graph: dict[str, Any],
                    status: str = graph_status,
                ) -> dict[str, Any]:
                    output = {
                        "graph_id": graph["graph_id"],
                        "outcome_summary": "No terminal execution evidence.",
                    }
                    if status:
                        output["status"] = status
                    return output

                coordinator = InteractionRuntimeCoordinator(
                    lambda args: spoken.append(str(args["text"]))
                    or {"scheduled": True},
                    task_graph_handler=execute_graph,
                )
                result = await _execute_to_terminal(coordinator,
                    InteractionResponse(
                        capabilities=[
                            {
                                "request_id": "graph-1",
                                "capability_id": "chromie.task_graph.execute",
                                "args": {
                                    "graph": {"graph_id": "nav", "nodes": []}
                                },
                                "timing": "sequential",
                            }
                        ],
                        metadata={"language": "en-US"},
                    ),
                    session_id=f"sid-graph-{graph_status or 'missing'}",
                )

                self.assertEqual(result.status, "failed")
                self.assertEqual(result.results[0].status, "failed")
                self.assertEqual(result.results[0].reason_code, expected_reason)
                self.assertEqual(spoken, [])

    async def test_cancelled_task_graph_suppresses_unverified_completion_speech(
        self,
    ) -> None:
        spoken: list[str] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            return {
                "graph_id": graph["graph_id"],
                "status": "cancelled",
                "outcome_summary": "TaskGraph was cancelled at node monitor.",
                "node_results": [],
                "events": [],
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_capabilities"}],
                capabilities=[
                    {
                        "request_id": "graph-1",
                        "capability_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-graph-cancelled",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].status, "cancelled")
        self.assertEqual(result.results[0].reason_code, "task_graph_cancelled")
        self.assertEqual(spoken, [])

    async def test_scoped_task_graph_cancel_uses_authoritative_endpoint(
        self,
    ) -> None:
        started = asyncio.Event()
        cancelled_graph_ids: list[str] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("cancelled TaskGraph execution resumed")

        async def cancel_graph(graph_id: str) -> dict[str, Any]:
            cancelled_graph_ids.append(graph_id)
            return {
                "graph_id": graph_id,
                "cancellation_requested": True,
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            task_graph_handler=execute_graph,
            task_graph_cancel_handler=cancel_graph,
        )
        execution_task = asyncio.create_task(
            _execute_to_terminal(coordinator,
                InteractionResponse(
                    interaction_id="interaction-task-graph-cancel",
                    capabilities=[
                        {
                            "request_id": "graph-request",
                            "capability_id": "chromie.task_graph.execute",
                            "args": {
                                "graph": {
                                    "graph_id": "graph-cancel",
                                    "nodes": [],
                                }
                            },
                            "timing": "sequential",
                        }
                    ],
                ),
                session_id="sid-task-graph-cancel",
            )
        )
        await started.wait()

        receipt = await coordinator.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-task-graph",
                requested_scope="embodied_motion",
            )
        )
        execution = await execution_task

        self.assertEqual(cancelled_graph_ids, ["graph-cancel"])
        self.assertEqual(_provider_failure_texts(receipt), ())
        self.assertEqual(
            _request_ids(receipt.cancel_requested_request_bindings),
            ("graph-request",),
        )
        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(execution.results[0].status, "cancelled")
        self.assertEqual(
            execution.results[0].reason_code,
            "cancelled_embodied_motion",
        )

    async def test_scoped_task_graph_cancel_fails_closed_without_endpoint(
        self,
    ) -> None:
        started = asyncio.Event()

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("cancelled TaskGraph execution resumed")

        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            task_graph_handler=execute_graph,
        )
        execution_task = asyncio.create_task(
            _execute_to_terminal(coordinator,
                InteractionResponse(
                    interaction_id="interaction-task-graph-no-cancel",
                    capabilities=[
                        {
                            "request_id": "graph-request",
                            "capability_id": "chromie.task_graph.execute",
                            "args": {
                                "graph": {
                                    "graph_id": "graph-no-cancel",
                                    "nodes": [],
                                }
                            },
                            "timing": "sequential",
                        }
                    ],
                ),
                session_id="sid-task-graph-no-cancel",
            )
        )
        await started.wait()

        receipt = await coordinator.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-task-graph-no-endpoint",
                requested_scope="embodied_motion",
            )
        )
        execution = await execution_task

        self.assertEqual(len(_provider_failure_texts(receipt)), 1)
        self.assertIn(
            "endpoint is not configured",
            _provider_failure_texts(receipt)[0],
        )
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[0].status, "failed")
        self.assertEqual(
            execution.results[0].reason_code,
            "cancellation_failed_embodied_motion",
        )

    async def test_task_graph_capability_fails_closed_when_handler_is_disabled(
        self,
    ) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "graph-1",
                        "capability_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-graph-disabled",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "task_graph_execution_disabled")
        self.assertEqual(spoken, [])

    async def test_cancelled_body_capability_suppresses_all_terminal_speech(self) -> None:
        spoken: list[str] = []
        invoker = _SoridormiInvoker(execute_delay_s=5)
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=invoker,
        )
        task = asyncio.create_task(
            _execute_to_terminal(coordinator,
                InteractionResponse(
                    speech=[
                        {"text": "Starting.", "timing": "immediate"},
                        {"text": "Done.", "timing": "after_capabilities"},
                    ],
                    capabilities=[{"capability_id": "soridormi.nod_yes"}],
                ),
                session_id="sid-cancelled",
            )
        )
        while not any(
            call[0] == "soridormi.skill.execute_plan" for call in invoker.calls
        ):
            await asyncio.sleep(0)

        task.cancel()
        result = await task

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(spoken, ["Starting."])

    async def test_recoverable_body_failure_returns_evidence_without_host_recovery_speech(
        self,
    ) -> None:
        spoken: list[dict[str, Any]] = []
        invoker = _SoridormiInvoker(
            execute_outcome=ToolCallOutcome.success(
                {
                    "completed": False,
                    "skill_id": "nod_yes",
                    "recoverable": True,
                    "user_message": "The motion profile slipped.",
                }
            )
        )
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(args) or {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                speech=[
                    {"text": "Starting.", "timing": "immediate"},
                    {"text": "Done.", "timing": "after_capabilities"},
                ],
                capabilities=[
                    {
                        "request_id": "nod-1",
                        "capability_id": "soridormi.nod_yes",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-recoverable",
        )

        self.assertEqual(result.status, "failed")
        body_results = [
            item for item in result.results if item.capability_id.startswith("soridormi.")
        ]
        self.assertEqual(body_results[0].status, "failed")
        self.assertEqual([item["text"] for item in spoken], ["Starting."])

    async def test_planner_retry_failure_returns_evidence_without_host_speech(
        self,
    ) -> None:
        spoken: list[str] = []
        invoker = _SoridormiInvoker(
            execute_outcome=ToolCallOutcome.success(
                {
                    "completed": False,
                    "skill_id": "nod_yes",
                    "recoverable": True,
                    "user_message": "The motion profile slipped again.",
                }
            )
        )
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await _execute_to_terminal(coordinator,
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "nod-1-retry",
                        "capability_id": "soridormi.nod_yes",
                        "metadata": {"source": "planner_retry_test"},
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-planner-retry",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(spoken, [])

    async def test_detached_cognitive_submit_returns_before_provider_terminal(
        self,
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_speech(_args: dict[str, Any]) -> dict[str, Any]:
            started.set()
            await release.wait()
            return {"scheduled": True, "playback_started": True}

        coordinator = InteractionRuntimeCoordinator(slow_speech)
        response = InteractionResponse(
            interaction_id="interaction-detached",
            capabilities=[
                CapabilityRequest(
                    request_id="request-slow",
                    capability_id="chromie.speak",
                    args={"text": "Working."},
                    metadata={"source_goal_ids": ["goal-detached"]},
                )
            ],
            metadata={
                "cognitive_runtime_apply": True,
                "canonical_plan": {"plan_id": "plan-detached"},
            },
        )

        dispatch = await coordinator.submit_response(
            response,
            session_id="sid-detached",
        )

        self.assertIsNotNone(dispatch.receipt)
        await asyncio.wait_for(started.wait(), timeout=1.0)
        observation = await coordinator.runtime.execution_observation()
        self.assertIn("interaction-detached", observation.open_interaction_ids)
        self.assertTrue(
            any(
                item.request_id == "request-slow" and item.provider_started
                for item in observation.requests
            )
        )

        release.set()
        execution = await coordinator.wait_dispatch(dispatch)
        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.results[0].request_id, "request-slow")

    async def test_detached_cognitive_submit_defers_pre_authored_result_speech(
        self,
    ) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": True, "playback_started": True}
        )
        response = InteractionResponse(
            interaction_id="interaction-result-wording",
            capabilities=[
                CapabilityRequest(
                    request_id="request-work",
                    capability_id="chromie.speak",
                    args={"text": "Working."},
                    metadata={"source_goal_ids": ["goal-work"]},
                )
            ],
            speech=[
                {
                    "id": "speech-unverified-result",
                    "text": "It definitely succeeded.",
                    "timing": "after_capabilities",
                }
            ],
            metadata={
                "cognitive_runtime_apply": True,
                "canonical_plan": {"plan_id": "plan-result-wording"},
            },
        )

        dispatch = await coordinator.submit_response(
            response,
            session_id="sid-result-wording",
        )

        self.assertEqual(dispatch.runtime_response.speech, [])
        self.assertEqual(
            dispatch.runtime_response.metadata["result_deferred_speech_ids"],
            ["speech-unverified-result"],
        )
        self.assertNotIn(
            "speech-unverified-result",
            dispatch.receipt.request_ids,
        )
        execution = await coordinator.wait_dispatch(dispatch)
        self.assertEqual(execution.status, "completed")



if __name__ == "__main__":
    unittest.main()
