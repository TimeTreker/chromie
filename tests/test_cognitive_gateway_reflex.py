from __future__ import annotations

import asyncio
import json
import unittest
from contextlib import nullcontext
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.confirmation import ConfirmationDialogue
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
)
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    ReflexFilter,
)


class ReflexFilterTests(unittest.TestCase):
    def test_cancellation_contract_rejects_ambiguous_plan_bindings(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "specific_goal cancellation",
        ):
            CancellationDirective(
                source_turn_id="turn-invalid-plan",
                requested_scope="current_interaction",
                foreground_interaction_id="interaction-1",
                expected_plan_id="plan-1",
                expected_plan_fingerprint="fingerprint-1",
            )
        with self.assertRaisesRegex(ValueError, "exact plan identity"):
            CancellationDirective(
                source_turn_id="turn-missing-plan",
                requested_scope="specific_goal",
                foreground_interaction_id="interaction-1",
                target_goal_ids=("goal-1",),
            )
        with self.assertRaisesRegex(ValueError, "marked widened"):
            CancellationDispatchReceipt(
                source_turn_id="turn-invalid-widening",
                requested_scope="specific_goal",
                effective_scope="embodied_motion",
                target_goal_ids=("goal-1",),
                expected_plan_id="plan-1",
                expected_plan_fingerprint="fingerprint-1",
            )
        with self.assertRaisesRegex(ValueError, "global emergency"):
            CancellationDispatchReceipt(
                source_turn_id="turn-invalid-emergency-evidence",
                requested_scope="current_interaction",
                effective_scope="current_interaction",
                emergency_stop_evidence={"status": "success"},
            )

    def test_emergency_stop_is_a_structured_deterministic_interrupt(self) -> None:
        reflex_filter = ReflexFilter()

        for text, language in (
            ("Emergency stop!", "en-US"),
            ("E stop!", "en-US"),
            ("急停！", "zh-CN"),
            ("请急停一下", "zh-CN"),
        ):
            with self.subTest(text=text):
                outcome = reflex_filter.evaluate(text)

                self.assertTrue(outcome.matched)
                self.assertEqual(outcome.action, "interrupt")
                self.assertEqual(outcome.trigger, "emergency_stop_command")
                self.assertEqual(outcome.intent, "global_emergency_stop")
                self.assertEqual(
                    outcome.cancellation_scope,
                    "global_emergency",
                )
                self.assertEqual(outcome.language, language)
                self.assertTrue(outcome.interrupt_current)
                self.assertFalse(outcome.should_speak)

    def test_context_and_negation_are_not_operational(self) -> None:
        reflex_filter = ReflexFilter()

        for text in (
            "What does emergency stop mean?",
            "The emergency stop button is red.",
            "Don't emergency stop the robot.",
            "What does E stop mean?",
            "Please explain the phrase 'stop talking for a moment'.",
            "Please do not stop.",
            "请解释什么是急停。",
            "不要急停。",
        ):
            with self.subTest(text=text):
                outcome = reflex_filter.evaluate(text)

                self.assertFalse(outcome.matched)
                self.assertEqual(outcome.action, "continue")
                self.assertFalse(outcome.interrupt_current)

    def test_fixed_stop_phrases_map_to_closed_cancellation_scopes(self) -> None:
        reflex_filter = ReflexFilter()

        for text, scope, intent in (
            ("Stop talking.", "output_only", "stop_current_output"),
            ("别说了。", "output_only", "stop_current_output"),
            ("Stop moving.", "embodied_motion", "stop_embodied_motion"),
            ("Stop all motion.", "embodied_motion", "stop_embodied_motion"),
            ("停止移动。", "embodied_motion", "stop_embodied_motion"),
            ("停止机器人。", "embodied_motion", "stop_embodied_motion"),
            ("请让机器人停下。", "embodied_motion", "stop_embodied_motion"),
            ("Stop.", "current_interaction", "cancel_current_interaction"),
            (
                "Stop everything.",
                "current_interaction",
                "cancel_current_interaction",
            ),
            ("停止。", "current_interaction", "cancel_current_interaction"),
            ("Cancel.", "current_interaction", "cancel_current_interaction"),
            ("取消。", "current_interaction", "cancel_current_interaction"),
            ("取消一切。", "current_interaction", "cancel_current_interaction"),
        ):
            with self.subTest(text=text):
                outcome = reflex_filter.evaluate(text)

                self.assertEqual(outcome.action, "interrupt")
                self.assertEqual(outcome.cancellation_scope, scope)
                self.assertEqual(outcome.intent, intent)

    def test_named_selective_stop_stays_cognitive(self) -> None:
        reflex_filter = ReflexFilter()

        for text in (
            "Stop bringing water, but keep playing music.",
            "停止送水，继续播放音乐。",
            "Stop that one.",
            "把那个停掉。",
        ):
            with self.subTest(text=text):
                outcome = reflex_filter.evaluate(text)

                self.assertEqual(outcome.action, "continue")
                self.assertEqual(outcome.cancellation_scope, "none")


class CognitiveGatewayReflexTests(unittest.IsolatedAsyncioTestCase):
    def _blocked_reflex_assistant(
        self,
    ) -> tuple[VoiceAssistant, dict[str, asyncio.Event], list[str]]:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        controls = {
            "release_abort": asyncio.Event(),
            "abort_started": asyncio.Event(),
            "second_abort_started": asyncio.Event(),
            "release_output_reflex": asyncio.Event(),
            "emergency_dispatched": asyncio.Event(),
            "release_emergency": asyncio.Event(),
            "ordinary_started": asyncio.Event(),
        }
        events: list[str] = []

        class _Runtime:
            async def cancel_scope(self, directive: Any) -> Any:
                events.append(
                    f"runtime_cancel:{directive.requested_scope}"
                )
                if directive.requested_scope == "output_only":
                    await controls["release_output_reflex"].wait()
                return CancellationDispatchReceipt(
                    source_turn_id=directive.source_turn_id,
                    requested_scope=directive.requested_scope,
                    effective_scope=directive.requested_scope,
                )

            async def emergency_stop(self, *, reason: str) -> dict[str, Any]:
                events.append("emergency_stop")
                controls["emergency_dispatched"].set()
                await controls["release_emergency"].wait()
                return {
                    "status": "success",
                    "output": {
                        "stopped": True,
                        "emergency": True,
                        "safe_idle": True,
                    },
                }

        class _Sessions:
            state = {
                "sid-output": {"llm_done": False},
                "sid-motion": {"llm_done": False},
                "sid-emergency": {"llm_done": False},
                "sid-ordinary": {"llm_done": False},
            }

            def trace_context(self, session_id: str) -> Any:
                return nullcontext()

        class _ConversationState:
            conversation_id = "conversation-reflex-priority"

            def record_user_turn(
                self,
                sid: str,
                user_text: str,
                *,
                route: str,
                intent: str,
                metadata: dict[str, Any],
            ) -> None:
                events.append(f"record:{sid}:{route}")

        async def abort_output_stream(
            self: VoiceAssistant,
        ) -> None:
            events.append("abort_output_stream")
            controls["abort_started"].set()
            if events.count("abort_output_stream") >= 2:
                controls["second_abort_started"].set()
            await controls["release_abort"].wait()

        real_handle_routed_text = VoiceAssistant.handle_routed_text

        async def handle_routed_text(
            self: VoiceAssistant,
            text: str,
            session_id: str,
        ) -> None:
            if ReflexFilter().evaluate(text).action == "interrupt":
                await real_handle_routed_text(self, text, session_id)
                return
            events.append(f"ordinary_started:{session_id}")
            controls["ordinary_started"].set()

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            events.append((message % args).split(":", 1)[0])

        assistant.active_turn_task = None
        assistant.active_reflex_task = None
        assistant._pending_turn_after_reflex = None
        assistant.concurrent_protective_reflex_tasks = set()
        assistant.active_interaction_task = None
        assistant.active_interaction_id = "foreground-interaction"
        assistant.active_interaction_tasks = {}
        assistant.interaction_runtime = _Runtime()
        assistant.confirmation_dialogue = ConfirmationDialogue()
        assistant.conversation_state = _ConversationState()
        assistant.sessions = _Sessions()
        assistant.playback_generation = 0
        assistant.playback_start_waiters = {}
        assistant.active_llm_task = None
        assistant.active_synthesis_tasks = set()
        assistant.pending_audio = {}
        assistant.cancelled_playback_orders = set()
        assistant.playback_queue = asyncio.Queue()
        assistant.next_playback_order = 0
        assistant.synthesis_order = 0
        assistant.output_abort_tasks = set()
        assistant.abort_output_stream = MethodType(
            abort_output_stream,
            assistant,
        )
        assistant.handle_routed_text = MethodType(
            handle_routed_text,
            assistant,
        )
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(
            lambda self, session_id: None,
            assistant,
        )
        return assistant, controls, events

    async def _exercise_local_stop(
        self,
        text: str,
        *,
        with_pending_confirmation: bool = False,
    ) -> tuple[list[str], dict[str, Any]]:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        events: list[str] = []
        network_calls = {"confirmation": 0, "session": 0, "router": 0, "model": 0}
        recorded_turn: dict[str, Any] = {}
        approval_during_provider_cancel: list[str] = []

        class _ConfirmationDialogue:
            def __init__(self) -> None:
                self.dialogue = ConfirmationDialogue(clock=lambda: 100.0)
                if with_pending_confirmation:
                    self.dialogue.begin(
                        InteractionResponse(
                            interaction_id="interaction-stop",
                            skills=[
                                {
                                    "request_id": "move-stop",
                                    "skill_id": "soridormi.walk_velocity",
                                    "args": {"vx_mps": 0.1, "duration_s": 1.0},
                                    "requires_confirmation": True,
                                }
                            ],
                        ),
                        confirmed_request_ids={"move-stop"},
                        origin_session_id="sid-stop",
                        conversation_id="conversation-stop",
                    )

            def cancel(self) -> Any:
                events.append("confirmation_cancel")
                return self.dialogue.cancel()

            def resolve(self, text: str) -> Any:
                return self.dialogue.resolve(text)

        confirmation_dialogue = _ConfirmationDialogue()

        class _Runtime:
            async def cancel_all(self) -> None:
                events.append("skill_runtime_cancel_all")

            async def cancel_scope(self, directive: Any) -> Any:
                events.append("skill_runtime_cancel_scope")
                if with_pending_confirmation:
                    approval_during_provider_cancel.append(
                        confirmation_dialogue.resolve("yes").decision
                    )
                return CancellationDispatchReceipt(
                    source_turn_id=directive.source_turn_id,
                    requested_scope=directive.requested_scope,
                    effective_scope=directive.requested_scope,
                    interaction_ids=("interaction-stop",),
                )

            async def emergency_stop(self, *, reason: str) -> dict[str, Any]:
                events.append("soridormi_emergency_stop")
                return {
                    "status": "success",
                    "output": {
                        "stopped": True,
                        "emergency": True,
                        "safe_idle": True,
                    },
                }

        class _Router:
            async def route(self, *args: Any, **kwargs: Any) -> None:
                network_calls["router"] += 1
                raise AssertionError("Router must not run for a local stop reflex")

        class _Sessions:
            state = {"sid-stop": {"llm_done": False}}

        class _ConversationState:
            def record_user_turn(
                self,
                sid: str,
                user_text: str,
                *,
                route: str,
                intent: str,
                metadata: dict[str, Any],
            ) -> None:
                events.append("record_user_turn")
                recorded_turn.update(
                    {
                        "sid": sid,
                        "text": user_text,
                        "route": route,
                        "intent": intent,
                        "metadata": metadata,
                    }
                )

            def resolve_confirmation_scope(
                self,
                *,
                confirmation_id: str,
                decision: str,
            ) -> bool:
                if "output_invalidation" not in events:
                    raise AssertionError(
                        "confirmation persistence must not delay interruption"
                    )
                events.append("confirmation_scope_cancelled")
                self.confirmation_id = confirmation_id
                self.confirmation_decision = decision
                return True

        def invalidate_output_state(
            self: VoiceAssistant,
            *,
            cancel_cognitive_work: bool = True,
        ) -> None:
            events.append("output_invalidation")

        def schedule_output_abort(
            self: VoiceAssistant,
            *,
            new_session_id: str | None,
            log_event: bool,
        ) -> None:
            events.append("output_abort_scheduled")

        async def fail_confirmation(
            self: VoiceAssistant,
            user_text: str,
            session_id: str,
        ) -> bool:
            network_calls["confirmation"] += 1
            raise AssertionError("confirmation handling must be bypassed")

        async def fail_session(self: VoiceAssistant) -> None:
            network_calls["session"] += 1
            raise AssertionError("network session must not be requested")

        async def fail_model(self: VoiceAssistant, *args: Any, **kwargs: Any) -> None:
            network_calls["model"] += 1
            raise AssertionError("model must not run for a local stop reflex")

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            events.append((message % args).split(":", 1)[0])

        def maybe_session_done(self: VoiceAssistant, sid: str | None) -> None:
            events.append("session_done")

        assistant.active_interaction_task = None
        assistant.active_interaction_id = "interaction-stop"
        assistant.playback_generation = 7
        assistant.interaction_runtime = _Runtime()
        assistant.router_client = _Router()
        assistant.sessions = _Sessions()
        assistant.conversation_state = _ConversationState()
        assistant.confirmation_dialogue = confirmation_dialogue
        assistant._invalidate_output_state = MethodType(
            invalidate_output_state,
            assistant,
        )
        assistant._schedule_output_abort = MethodType(
            schedule_output_abort,
            assistant,
        )
        assistant._handle_confirmation_reply = MethodType(fail_confirmation, assistant)
        assistant.get_http_session = MethodType(fail_session, assistant)
        assistant.process_llm_tts = MethodType(fail_model, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)

        await assistant.handle_routed_text(text, "sid-stop")

        self.assertEqual(
            network_calls,
            {"confirmation": 0, "session": 0, "router": 0, "model": 0},
        )
        self.assertLess(
            events.index("output_invalidation"),
            events.index("record_user_turn"),
        )
        self.assertLess(events.index("skill_runtime_cancel_scope"), events.index("record_user_turn"))
        self.assertIn("cognitive_gateway_reflex_detected", events)
        self.assertIn("cognitive_gateway_reflex_applied", events)
        self.assertEqual(assistant.sessions.state["sid-stop"]["llm_done"], True)
        self.assertEqual(recorded_turn["route"], "interrupt")
        expected_intent = (
            "global_emergency_stop"
            if recorded_turn["metadata"]["reflex_outcome"]["trigger"]
            == "emergency_stop_command"
            else "cancel_current_interaction"
        )
        self.assertEqual(recorded_turn["intent"], expected_intent)
        self.assertEqual(recorded_turn["metadata"]["source"], "cognitive_gateway_reflex")
        self.assertEqual(recorded_turn["metadata"]["reflex_outcome"]["action"], "interrupt")
        envelope = recorded_turn["metadata"]["user_turn_envelope"]
        self.assertEqual(envelope["schema_version"], 1)
        self.assertEqual(envelope["turn_id"], "sid-stop")
        self.assertEqual(envelope["session_id"], "sid-stop")
        self.assertEqual(envelope["original_input"]["text"], text)
        self.assertEqual(envelope["reflex"]["action"], "interrupt")
        self.assertEqual(envelope["admission"], "reflex_and_admit")
        recorded_turn["approval_during_provider_cancel"] = approval_during_provider_cancel
        return events, recorded_turn

    async def test_english_emergency_stop_bypasses_router_and_model(self) -> None:
        _, turn = await self._exercise_local_stop("Emergency stop!")
        self.assertEqual(
            turn["metadata"]["reflex_outcome"]["trigger"],
            "emergency_stop_command",
        )

    async def test_chinese_emergency_stop_bypasses_router_and_model(self) -> None:
        _, turn = await self._exercise_local_stop("急停！")
        self.assertEqual(
            turn["metadata"]["reflex_outcome"]["trigger"],
            "emergency_stop_command",
        )

    async def test_stop_invalidates_pending_confirmation_before_first_await(self) -> None:
        events, turn = await self._exercise_local_stop(
            "Stop now.",
            with_pending_confirmation=True,
        )

        self.assertLess(
            events.index("confirmation_cancel"),
            events.index("output_invalidation"),
        )
        self.assertLess(
            events.index("output_invalidation"),
            events.index("confirmation_scope_cancelled"),
        )
        self.assertLess(
            events.index("skill_runtime_cancel_scope"),
            events.index("confirmation_scope_cancelled"),
        )
        self.assertLess(
            events.index("confirmation_scope_cancelled"),
            events.index("record_user_turn"),
        )
        self.assertEqual(turn["approval_during_provider_cancel"], ["no_pending"])
        cancelled = turn["metadata"]["reflex_outcome"]["metadata"][
            "cancelled_confirmation"
        ]
        self.assertTrue(cancelled["confirmation_id"].startswith("confirm_"))
        self.assertEqual(len(cancelled["fingerprint"]), 64)

    async def test_output_and_motion_reflexes_preserve_unrelated_interaction_work(
        self,
    ) -> None:
        for text, expected_scope, expected_invalidations in (
            (
                "Stop talking.",
                "output_only",
                [False, False],
            ),
            ("Stop moving.", "embodied_motion", []),
        ):
            with self.subTest(text=text):
                assistant = VoiceAssistant.__new__(VoiceAssistant)
                output_invalidations: list[bool] = []
                output_aborts: list[str | None] = []
                directives: list[Any] = []

                class _Runtime:
                    async def cancel_scope(self, directive: Any) -> Any:
                        directives.append(directive)
                        return CancellationDispatchReceipt(
                            source_turn_id=directive.source_turn_id,
                            requested_scope=directive.requested_scope,
                            effective_scope=directive.requested_scope,
                            interaction_ids=("foreground-interaction",),
                        )

                def invalidate_output_state(
                    self: VoiceAssistant,
                    *,
                    cancel_cognitive_work: bool = True,
                ) -> None:
                    output_invalidations.append(
                        cancel_cognitive_work
                    )

                def schedule_output_abort(
                    self: VoiceAssistant,
                    *,
                    new_session_id: str | None,
                    log_event: bool,
                ) -> None:
                    output_aborts.append(new_session_id)

                assistant.interaction_runtime = _Runtime()
                assistant.active_interaction_id = "foreground-interaction"
                assistant.active_interaction_task = asyncio.create_task(
                    asyncio.Event().wait()
                )
                assistant._invalidate_output_state = MethodType(
                    invalidate_output_state,
                    assistant,
                )
                assistant._schedule_output_abort = MethodType(
                    schedule_output_abort,
                    assistant,
                )
                assistant.session_log = MethodType(
                    lambda self, *args, **kwargs: None,
                    assistant,
                )
                try:
                    outcome = ReflexFilter().evaluate(text)
                    receipt = await assistant._apply_reflex_cancellation(
                        outcome,
                        source_turn_id="turn-scoped",
                    )

                    self.assertEqual(receipt.requested_scope, expected_scope)
                    self.assertEqual(
                        directives[0].foreground_interaction_id,
                        (
                            "foreground-interaction"
                            if expected_scope == "output_only"
                            else None
                        ),
                    )
                    self.assertEqual(
                        output_invalidations,
                        expected_invalidations,
                    )
                    self.assertEqual(
                        output_aborts,
                        (
                            ["turn-scoped"]
                            if expected_scope == "output_only"
                            else []
                        ),
                    )
                    self.assertFalse(
                        assistant.active_interaction_task.done()
                    )
                finally:
                    assistant.active_interaction_task.cancel()
                    await asyncio.gather(
                        assistant.active_interaction_task,
                        return_exceptions=True,
                    )

    async def test_emergency_reflex_dispatches_dedicated_estop_without_active_work(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        emergency_reasons: list[str] = []

        class _Runtime:
            async def cancel_scope(self, directive: Any) -> Any:
                return CancellationDispatchReceipt(
                    source_turn_id=directive.source_turn_id,
                    requested_scope=directive.requested_scope,
                    effective_scope=directive.requested_scope,
                )

            async def emergency_stop(self, *, reason: str) -> dict[str, Any]:
                emergency_reasons.append(reason)
                return {
                    "status": "success",
                    "tool": "soridormi.safety.emergency_stop",
                    "output": {
                        "stopped": True,
                        "emergency": True,
                        "safe_idle": True,
                    },
                }

        async def interrupt_output(
            self: VoiceAssistant,
            new_session_id: str | None = None,
            *,
            log_event: bool = True,
            cancel_cognitive_work: bool = True,
        ) -> None:
            return None

        assistant.interaction_runtime = _Runtime()
        assistant.active_interaction_id = None
        assistant.active_interaction_task = None
        assistant.interrupt_output = MethodType(
            interrupt_output,
            assistant,
        )
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        receipt = await assistant._apply_reflex_cancellation(
            ReflexFilter().evaluate("Emergency stop!"),
            source_turn_id="turn-emergency",
        )

        self.assertEqual(len(emergency_reasons), 1)
        self.assertEqual(
            receipt.emergency_stop_evidence["status"],
            "success",
        )
        self.assertTrue(
            receipt.emergency_stop_evidence["output"]["safe_idle"]
        )

    async def test_blocked_audio_abort_does_not_delay_runtime_or_estop(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        output_started = asyncio.Event()
        release_output = asyncio.Event()
        runtime_cancelled = asyncio.Event()
        emergency_dispatched = asyncio.Event()

        class _Runtime:
            async def cancel_scope(self, directive: Any) -> Any:
                runtime_cancelled.set()
                return CancellationDispatchReceipt(
                    source_turn_id=directive.source_turn_id,
                    requested_scope=directive.requested_scope,
                    effective_scope=directive.requested_scope,
                )

            async def emergency_stop(self, *, reason: str) -> dict[str, Any]:
                emergency_dispatched.set()
                return {
                    "status": "success",
                    "output": {
                        "stopped": True,
                        "emergency": True,
                        "safe_idle": True,
                    },
                }

        async def abort_output_stream(
            self: VoiceAssistant,
        ) -> None:
            output_started.set()
            await release_output.wait()

        assistant.interaction_runtime = _Runtime()
        assistant.active_interaction_id = None
        assistant.active_interaction_task = None
        assistant.active_interaction_tasks = {}
        assistant.playback_generation = 0
        assistant.playback_start_waiters = {}
        assistant.active_llm_task = None
        assistant.active_turn_task = None
        assistant.active_reflex_task = None
        assistant.active_synthesis_tasks = set()
        assistant.pending_audio = {}
        assistant.cancelled_playback_orders = set()
        assistant.playback_queue = asyncio.Queue()
        assistant.next_playback_order = 0
        assistant.synthesis_order = 0
        assistant.output_abort_tasks = set()
        assistant.abort_output_stream = MethodType(
            abort_output_stream,
            assistant,
        )
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        cancellation_task = asyncio.create_task(
            assistant._apply_reflex_cancellation(
                ReflexFilter().evaluate("Emergency stop!"),
                source_turn_id="turn-blocked-output",
            )
        )
        await output_started.wait()
        await asyncio.wait_for(runtime_cancelled.wait(), timeout=1.0)
        await asyncio.wait_for(emergency_dispatched.wait(), timeout=1.0)
        receipt = await asyncio.wait_for(
            cancellation_task,
            timeout=1.0,
        )
        self.assertTrue(
            any(
                not task.done()
                for task in assistant.output_abort_tasks
            )
        )

        release_output.set()
        await asyncio.wait_for(
            asyncio.gather(
                *tuple(assistant.output_abort_tasks),
            ),
            timeout=1.0,
        )
        self.assertEqual(
            receipt.emergency_stop_evidence["status"],
            "success",
        )
        self.assertEqual(receipt.dispatch_failures, ())

    async def test_global_emergency_cancels_all_host_interactions_when_runtime_fails(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        started = {
            "older": asyncio.Event(),
            "newer": asyncio.Event(),
        }

        async def unfinished(interaction_id: str) -> None:
            started[interaction_id].set()
            await asyncio.Event().wait()

        older_task = asyncio.create_task(unfinished("older"))
        newer_task = asyncio.create_task(unfinished("newer"))
        await asyncio.gather(
            started["older"].wait(),
            started["newer"].wait(),
        )

        class _Runtime:
            async def cancel_scope(self, directive: Any) -> Any:
                raise RuntimeError("runtime cancellation unavailable")

            async def emergency_stop(self, *, reason: str) -> dict[str, Any]:
                return {
                    "status": "success",
                    "output": {
                        "stopped": True,
                        "emergency": True,
                        "safe_idle": True,
                    },
                }

        assistant.interaction_runtime = _Runtime()
        assistant.active_interaction_tasks = {
            older_task: "older",
            newer_task: "newer",
        }
        assistant.active_interaction_task = newer_task
        assistant.active_interaction_id = "newer"
        assistant._invalidate_output_state = MethodType(
            lambda self, **kwargs: None,
            assistant,
        )
        assistant._schedule_output_abort = MethodType(
            lambda self, **kwargs: None,
            assistant,
        )
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        receipt = await assistant._apply_reflex_cancellation(
            ReflexFilter().evaluate("Emergency stop!"),
            source_turn_id="turn-global-host-fallback",
        )
        await asyncio.gather(
            older_task,
            newer_task,
            return_exceptions=True,
        )

        self.assertTrue(older_task.cancelled())
        self.assertTrue(newer_task.cancelled())
        self.assertEqual(receipt.interaction_ids, ("newer", "older"))
        self.assertEqual(receipt.host_interaction_ids, ("newer", "older"))
        self.assertEqual(
            receipt.host_task_cancel_requested_interaction_ids,
            ("newer", "older"),
        )
        self.assertTrue(
            any(
                failure.startswith("skill_runtime:RuntimeError:")
                for failure in receipt.dispatch_failures
            )
        )

    async def test_foreground_interaction_restores_older_unfinished_work(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.active_interaction_task = None
        assistant.active_interaction_id = None
        assistant.active_interaction_tasks = {}
        started = {
            "older": asyncio.Event(),
            "newer": asyncio.Event(),
        }
        release = {
            "older": asyncio.Event(),
            "newer": asyncio.Event(),
        }

        async def execute_interaction_response(
            self: VoiceAssistant,
            response: InteractionResponse,
            session_id: str | None,
            **kwargs: Any,
        ) -> None:
            started[response.interaction_id].set()
            await release[response.interaction_id].wait()

        assistant.execute_interaction_response = MethodType(
            execute_interaction_response,
            assistant,
        )
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        assistant._launch_interaction(
            InteractionResponse(interaction_id="older"),
            "sid-older",
        )
        older_task = assistant.active_interaction_task
        assistant._launch_interaction(
            InteractionResponse(interaction_id="newer"),
            "sid-newer",
        )
        newer_task = assistant.active_interaction_task
        await asyncio.gather(
            started["older"].wait(),
            started["newer"].wait(),
        )

        release["newer"].set()
        await newer_task
        await asyncio.sleep(0)

        self.assertIs(assistant.active_interaction_task, older_task)
        self.assertEqual(assistant.active_interaction_id, "older")
        release["older"].set()
        await older_task
        await asyncio.sleep(0)
        self.assertIsNone(assistant.active_interaction_task)
        self.assertIsNone(assistant.active_interaction_id)

    async def test_output_only_does_not_revoke_unrelated_confirmation(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.confirmation_dialogue = ConfirmationDialogue(
            clock=lambda: 100.0
        )
        pending = assistant.confirmation_dialogue.begin(
            InteractionResponse(
                interaction_id="confirm-output",
                skills=[
                    {
                        "request_id": "weather-request",
                        "skill_id": "chromie.weather",
                    }
                ],
            ),
            confirmed_request_ids={"weather-request"},
            origin_session_id="sid-confirm",
            conversation_id="conversation-confirm",
        )

        revoked = assistant._revoke_pending_confirmation_for_reflex(
            ReflexFilter().evaluate("Stop talking.")
        )

        self.assertIsNone(revoked)
        self.assertIs(assistant.confirmation_dialogue.pending, pending)

    async def test_motion_stop_revokes_unknown_confirmed_request(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.confirmation_dialogue = ConfirmationDialogue(
            clock=lambda: 100.0
        )
        assistant.confirmation_dialogue.begin(
            InteractionResponse(
                interaction_id="confirm-unknown-motion",
                skills=[
                    {
                        "request_id": "unknown-request",
                        "skill_id": "unknown.pending.skill",
                    }
                ],
            ),
            confirmed_request_ids={"unknown-request"},
            origin_session_id="sid-confirm",
            conversation_id="conversation-confirm",
        )

        class _Registry:
            def get(self, skill_id: str) -> Any:
                raise ValueError(f"unknown skill {skill_id}")

        assistant.interaction_runtime = type(
            "Runtime",
            (),
            {"registry": _Registry()},
        )()

        revoked = assistant._revoke_pending_confirmation_for_reflex(
            ReflexFilter().evaluate("Stop moving.")
        )

        self.assertIsNotNone(revoked)
        self.assertEqual(
            revoked.confirmed_request_ids,
            frozenset({"unknown-request"}),
        )
        self.assertIsNone(assistant.confirmation_dialogue.pending)

    async def test_motion_stop_revokes_shared_confirmation_scope(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.confirmation_dialogue = ConfirmationDialogue(
            clock=lambda: 100.0
        )
        assistant.confirmation_dialogue.begin(
            InteractionResponse(
                interaction_id="confirm-mixed-motion",
                skills=[
                    {
                        "request_id": "motion-request",
                        "skill_id": "soridormi.walk",
                    },
                    {
                        "request_id": "tool-request",
                        "skill_id": "chromie.weather",
                    },
                ],
            ),
            confirmed_request_ids={
                "motion-request",
                "tool-request",
            },
            origin_session_id="sid-confirm",
            conversation_id="conversation-confirm",
        )

        class _Definition:
            def __init__(self, *domains: str) -> None:
                self.cancellation_domains = domains

        class _Registry:
            def get(self, skill_id: str) -> Any:
                if skill_id == "soridormi.walk":
                    return _Definition("embodied_motion")
                return _Definition()

        assistant.interaction_runtime = type(
            "Runtime",
            (),
            {"registry": _Registry()},
        )()

        revoked = assistant._revoke_pending_confirmation_for_reflex(
            ReflexFilter().evaluate("Stop moving.")
        )

        self.assertIsNotNone(revoked)
        self.assertEqual(
            revoked.confirmed_request_ids,
            frozenset({"motion-request", "tool-request"}),
        )
        self.assertIsNone(assistant.confirmation_dialogue.pending)

    async def test_emergency_bypasses_blocked_output_reflex_and_is_not_replaced(
        self,
    ) -> None:
        assistant, controls, events = (
            self._blocked_reflex_assistant()
        )

        assistant._launch_routed_turn("Stop talking.", "sid-output")
        output_reflex = assistant.active_reflex_task
        assert output_reflex is not None
        await asyncio.wait_for(
            controls["abort_started"].wait(),
            timeout=1.0,
        )

        assistant._launch_routed_turn(
            "Stop moving.",
            "sid-motion",
        )
        for _ in range(20):
            if "runtime_cancel:embodied_motion" in events:
                break
            await asyncio.sleep(0)
        self.assertIn("runtime_cancel:embodied_motion", events)
        self.assertFalse(output_reflex.done())

        assistant._launch_routed_turn(
            "Emergency stop!",
            "sid-emergency",
        )
        await asyncio.wait_for(
            controls["emergency_dispatched"].wait(),
            timeout=1.0,
        )
        self.assertFalse(output_reflex.done())
        self.assertEqual(
            assistant._pending_turn_after_reflex,
            None,
        )
        emergency_tasks = set(
            assistant.concurrent_protective_reflex_tasks
        )
        self.assertEqual(len(emergency_tasks), 1)

        assistant._launch_routed_turn(
            "What time is it?",
            "sid-ordinary",
        )
        await asyncio.sleep(0)

        self.assertEqual(
            assistant._pending_turn_after_reflex,
            ("What time is it?", "sid-ordinary"),
        )
        self.assertFalse(controls["ordinary_started"].is_set())
        self.assertTrue(
            any(not task.done() for task in emergency_tasks)
        )
        self.assertLess(
            events.index("emergency_stop"),
            events.index(
                "turn_queued_behind_cognitive_gateway_reflex"
            ),
        )

        controls["release_output_reflex"].set()
        await asyncio.wait_for(output_reflex, timeout=1.0)
        await asyncio.sleep(0)
        self.assertFalse(controls["ordinary_started"].is_set())

        controls["release_emergency"].set()
        await asyncio.wait_for(
            asyncio.gather(*emergency_tasks),
            timeout=1.0,
        )
        await asyncio.wait_for(
            controls["ordinary_started"].wait(),
            timeout=1.0,
        )
        self.assertFalse(controls["release_abort"].is_set())

        controls["release_abort"].set()
        await asyncio.wait_for(
            asyncio.gather(
                *tuple(assistant.output_abort_tasks),
            ),
            timeout=1.0,
        )
        await asyncio.sleep(0)

    async def test_vad_emergency_bypasses_blocked_output_abort(
        self,
    ) -> None:
        assistant, controls, events = (
            self._blocked_reflex_assistant()
        )

        class _Asr:
            close_code = None

            async def send(self, audio: bytes) -> None:
                events.append(f"asr_send:{len(audio)}")

            async def recv(self) -> str:
                return json.dumps(
                    {
                        "type": "final",
                        "text": "Emergency stop!",
                    }
                )

            async def close(self) -> None:
                return None

        assistant._launch_routed_turn("Stop talking.", "sid-output")
        output_reflex = assistant.active_reflex_task
        assert output_reflex is not None
        await asyncio.wait_for(
            controls["abort_started"].wait(),
            timeout=1.0,
        )

        assistant.target_asr_rate = 16000
        assistant.max_vad_utterance_ms = 1000
        assistant.min_audio_ms = 10
        assistant.min_rms = 1.0
        assistant.barge_in_min_rms = 1.0
        assistant.is_playing_audio = False
        assistant.asr_timeout_s = 1.0
        assistant.asr_ws = _Asr()
        assistant.active_llm_task = None
        assistant.active_synthesis_tasks = set()
        assistant.pending_audio = {}
        assistant.cancelled_playback_orders = set()
        assistant.playback_queue = asyncio.Queue()
        assistant.next_playback_order = 0
        assistant.synthesis_order = 0
        assistant.playback_start_waiters = {}
        assistant.create_session = MethodType(
            lambda self: "sid-emergency",
            assistant,
        )
        assistant.save_audio = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        pcm16 = int(1000).to_bytes(
            2,
            byteorder="little",
            signed=True,
        ) * 1600
        vad_task = asyncio.create_task(
            assistant.handle_vad_audio(pcm16)
        )
        await asyncio.wait_for(
            controls["emergency_dispatched"].wait(),
            timeout=1.0,
        )

        self.assertFalse(output_reflex.done())
        self.assertFalse(controls["release_abort"].is_set())
        self.assertIn("runtime_cancel:global_emergency", events)
        self.assertIn("emergency_stop", events)
        self.assertEqual(events.count("abort_output_stream"), 1)
        self.assertTrue(
            any(
                not task.done()
                for task in assistant.output_abort_tasks
            )
        )

        controls["release_output_reflex"].set()
        controls["release_emergency"].set()
        controls["release_abort"].set()
        await asyncio.wait_for(vad_task, timeout=1.0)
        await asyncio.wait_for(output_reflex, timeout=1.0)
        await asyncio.wait_for(
            asyncio.gather(
                *tuple(
                    assistant.concurrent_protective_reflex_tasks
                ),
            ),
            timeout=1.0,
        )
        await asyncio.wait_for(
            asyncio.gather(
                *tuple(assistant.output_abort_tasks),
            ),
            timeout=1.0,
        )
        await asyncio.sleep(0)

    async def test_launch_reservation_blocks_preflight_execution_after_stop(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        reset_started = asyncio.Event()
        release_reset = asyncio.Event()
        provider_calls: list[str] = []

        async def speak(args: dict[str, Any]) -> dict[str, Any]:
            provider_calls.append(str(args.get("text") or ""))
            return {
                "scheduled": True,
                "playback_started": True,
                "spoken": True,
            }

        async def reset_playback_ordering(
            self: VoiceAssistant,
        ) -> None:
            reset_started.set()
            await release_reset.wait()

        async def interrupt_output(
            self: VoiceAssistant,
            new_session_id: str | None = None,
            *,
            log_event: bool = True,
            cancel_cognitive_work: bool = True,
        ) -> None:
            return None

        coordinator = InteractionRuntimeCoordinator(speak)
        interaction_id = "reserved-before-preflight"
        assistant.interaction_runtime = coordinator
        assistant.active_interaction_task = None
        assistant.active_interaction_id = None
        assistant.active_interaction_tasks = {}
        assistant.active_interaction_reservations = {}
        assistant.reset_playback_ordering = MethodType(
            reset_playback_ordering,
            assistant,
        )
        assistant.interrupt_output = MethodType(
            interrupt_output,
            assistant,
        )
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        assistant._launch_interaction(
            InteractionResponse(
                interaction_id=interaction_id,
                speech=[
                    {
                        "text": "This must never start.",
                        "timing": "immediate",
                    }
                ],
            ),
            "sid-reserved",
        )
        interaction_task = assistant.active_interaction_task
        assert interaction_task is not None
        await asyncio.wait_for(reset_started.wait(), timeout=1.0)
        self.assertIn(
            interaction_id,
            coordinator.runtime._open_interactions,
        )

        receipt = await assistant._apply_reflex_cancellation(
            ReflexFilter().evaluate("Stop."),
            source_turn_id="sid-stop-reserved",
        )
        await asyncio.wait_for(
            asyncio.gather(
                interaction_task,
                return_exceptions=True,
            ),
            timeout=1.0,
        )
        await asyncio.sleep(0)

        self.assertEqual(provider_calls, [])
        self.assertEqual(
            receipt.interaction_ids,
            (interaction_id,),
        )
        self.assertEqual(
            receipt.host_task_cancel_requested_interaction_ids,
            (interaction_id,),
        )
        self.assertNotIn(
            interaction_id,
            coordinator.runtime._open_interactions,
        )
        self.assertEqual(assistant.active_interaction_tasks, {})
        self.assertIsNone(assistant.active_interaction_task)
        self.assertIsNone(assistant.active_interaction_id)
        release_reset.set()

    async def test_following_turn_waits_for_reflex_instead_of_cancelling_it(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        events: list[str] = []
        reflex_started = asyncio.Event()
        release_reflex = asyncio.Event()
        following_completed = asyncio.Event()

        class _Sessions:
            state = {
                "sid-stop": {"llm_done": False},
                "sid-next": {"llm_done": False},
            }

        async def handle(self: VoiceAssistant, text: str, session_id: str) -> None:
            if text == "Stop now.":
                events.append("reflex_started")
                reflex_started.set()
                await release_reflex.wait()
                events.append("reflex_completed")
                return
            events.append(f"following_started:{text}")
            following_completed.set()

        async def abort_output_stream(self: VoiceAssistant) -> None:
            events.append("abort_output_stream")

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            events.append((message % args).split(":", 1)[0])

        def maybe_session_done(self: VoiceAssistant, sid: str | None) -> None:
            events.append(f"session_done:{sid}")

        assistant.active_turn_task = None
        assistant.active_reflex_task = None
        assistant._pending_turn_after_reflex = None
        assistant.playback_generation = 0
        assistant.active_llm_task = None
        assistant.active_synthesis_tasks = set()
        assistant.pending_audio = {}
        assistant.cancelled_playback_orders = set()
        assistant.playback_queue = asyncio.Queue()
        assistant.next_playback_order = 0
        assistant.synthesis_order = 0
        assistant.resolve_all_playback_start_waiters = lambda **kwargs: None
        assistant.sessions = _Sessions()
        assistant.handle_routed_text = MethodType(handle, assistant)
        assistant.abort_output_stream = MethodType(abort_output_stream, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)

        assistant._launch_routed_turn("Stop now.", "sid-stop")
        reflex_task = assistant.active_turn_task
        assert reflex_task is not None
        await reflex_started.wait()

        # The real voice path interrupts old audio from the ASR/VAD task before
        # it launches the next routed turn. That output cleanup must not cancel
        # an in-flight protective reflex.
        await assistant.interrupt_output(new_session_id="sid-next")
        self.assertFalse(reflex_task.cancelled())

        assistant._launch_routed_turn("Hello after stop.", "sid-next")
        await asyncio.sleep(0)

        self.assertIs(assistant.active_turn_task, reflex_task)
        self.assertFalse(reflex_task.cancelled())
        self.assertFalse(following_completed.is_set())
        self.assertEqual(
            assistant._pending_turn_after_reflex,
            ("Hello after stop.", "sid-next"),
        )

        release_reflex.set()
        await asyncio.wait_for(following_completed.wait(), timeout=1.0)
        await asyncio.sleep(0)

        self.assertFalse(reflex_task.cancelled())
        self.assertLess(
            events.index("reflex_completed"),
            events.index("following_started:Hello after stop."),
        )
