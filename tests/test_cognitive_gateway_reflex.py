from __future__ import annotations

import asyncio
import unittest
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.confirmation import ConfirmationDialogue
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.reflex import ReflexFilter


class ReflexFilterTests(unittest.TestCase):
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
                self.assertEqual(outcome.intent, "stop_current_output")
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


class CognitiveGatewayReflexTests(unittest.IsolatedAsyncioTestCase):
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
                if with_pending_confirmation:
                    approval_during_provider_cancel.append(
                        confirmation_dialogue.resolve("yes").decision
                    )

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
                if "interrupt_output" not in events:
                    raise AssertionError(
                        "confirmation persistence must not delay interruption"
                    )
                events.append("confirmation_scope_cancelled")
                self.confirmation_id = confirmation_id
                self.confirmation_decision = decision
                return True

        async def interrupt_output(
            self: VoiceAssistant,
            new_session_id: str | None = None,
            log_event: bool = True,
        ) -> None:
            events.append("interrupt_output")

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
        assistant.playback_generation = 7
        assistant.interaction_runtime = _Runtime()
        assistant.router_client = _Router()
        assistant.sessions = _Sessions()
        assistant.conversation_state = _ConversationState()
        assistant.confirmation_dialogue = confirmation_dialogue
        assistant.interrupt_output = MethodType(interrupt_output, assistant)
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
        self.assertLess(events.index("interrupt_output"), events.index("record_user_turn"))
        self.assertLess(events.index("skill_runtime_cancel_all"), events.index("record_user_turn"))
        self.assertIn("cognitive_gateway_reflex_detected", events)
        self.assertIn("cognitive_gateway_reflex_applied", events)
        self.assertEqual(assistant.sessions.state["sid-stop"]["llm_done"], True)
        self.assertEqual(recorded_turn["route"], "interrupt")
        self.assertEqual(recorded_turn["intent"], "stop_current_output")
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
            events.index("interrupt_output"),
        )
        self.assertLess(
            events.index("interrupt_output"),
            events.index("confirmation_scope_cancelled"),
        )
        self.assertLess(
            events.index("skill_runtime_cancel_all"),
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
