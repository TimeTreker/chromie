from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from types import MethodType
from typing import Any

for module_name in ("aiohttp", "numpy", "sounddevice", "websockets"):
    if module_name not in sys.modules:
        sys.modules[module_name] = types.ModuleType(module_name)
if "scipy" not in sys.modules:
    scipy = types.ModuleType("scipy")
    scipy.signal = types.ModuleType("signal")  # type: ignore[attr-defined]
    sys.modules["scipy"] = scipy
    sys.modules["scipy.signal"] = scipy.signal  # type: ignore[attr-defined]

from orchestrator.orchestrator import VoiceAssistant
import orchestrator.orchestrator as orchestrator_module
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.mind import MindManager
from orchestrator.runtime.session import SessionTracker
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.interaction import InteractionResponse


class OrchestratorTtsAlignmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_deep_thought_ack_is_language_matched_and_scheduled(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160
        seen: list[tuple[int, str]] = []

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            del session_id, generation
            seen.append((order, text))
            await asyncio.sleep(0)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)
        decision = RouteDecision(
            route="deep_thought",
            agents=["deepthinking_agent", "speaker_agent"],
            language="zh-CN",
        )

        scheduled = await assistant._schedule_deep_thought_ack(
            decision,
            "请帮我认真规划一下。",
            session_id,
        )
        pending = list(assistant.active_synthesis_tasks)
        if pending:
            await asyncio.gather(*pending)

        self.assertTrue(scheduled)
        self.assertEqual(seen, [(0, "好的，我想一下。")])
        self.assertEqual(
            assistant.sessions.state[session_id]["scheduled_tts"],
            1,
        )

    async def test_low_confidence_deep_thought_does_not_schedule_prelude(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160
        seen: list[str] = []

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            del order, session_id, generation
            seen.append(text)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)
        decision = RouteDecision(
            route="deep_thought",
            agents=["deepthinking_agent", "speaker_agent"],
            intent="deep_thought_low_confidence",
            language="en-US",
            metadata={"thinking_ack_allowed": False},
        )

        scheduled = await assistant._schedule_deep_thought_ack(
            decision,
            "Please do it.",
            session_id,
        )
        response = assistant._deep_thought_body_cue_response(
            decision,
            "Please do it.",
        )

        self.assertFalse(scheduled)
        self.assertEqual(seen, [])
        self.assertIsNone(response)
        self.assertEqual(
            assistant.sessions.state[session_id]["scheduled_tts"],
            0,
        )

    def test_fast_first_response_text_is_route_truthful(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True

        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(route="chat", intent="general_conversation", language="en-US"),
                "Hello, how are you?",
            ),
            "I'm here.",
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(route="chat", intent="fact_question", language="en-US"),
                "What is 2 plus 2?",
            ),
            "I'll answer.",
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(route="robot_action", intent="robot_action", language="en-US"),
                "Walk forward for 15 seconds.",
            ),
            "Checking.",
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(route="robot_action", intent="robot_action", language="zh-CN"),
                "往前走个15秒。",
            ),
            "我先确认。",
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(route="clarify", intent="clarify_target_location", language="en-US"),
                "Move over there.",
            )
        )

    def test_fast_first_response_can_be_disabled(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = False

        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(route="robot_action", intent="robot_action", language="en-US"),
                "Walk forward.",
            )
        )

    async def test_fast_first_response_schedules_before_agent(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160
        seen: list[tuple[int, str]] = []

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            del session_id, generation
            seen.append((order, text))
            await asyncio.sleep(0)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "speaker_agent"],
            intent="robot_action",
            language="en-US",
        )

        scheduled = await assistant._schedule_fast_first_response(
            decision,
            "Walk forward for 15 seconds.",
            session_id,
        )
        pending = list(assistant.active_synthesis_tasks)
        if pending:
            await asyncio.gather(*pending)

        self.assertTrue(scheduled)
        self.assertEqual(seen, [(0, "Checking.")])
        self.assertEqual(
            assistant.sessions.state[session_id]["scheduled_tts"],
            1,
        )

    def test_deep_thought_body_cue_uses_optional_express_attention(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.enable_interaction_response = True
        assistant.enable_soridormi_skills = True
        assistant.auto_confirm_sim_skills = True
        assistant.action_dry_run = True
        decision = RouteDecision(
            route="deep_thought",
            agents=["deepthinking_agent", "speaker_agent"],
            language="en-US",
        )

        response = assistant._deep_thought_body_cue_response(
            decision,
            "Please think this through.",
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(len(response.skills), 1)
        self.assertEqual(
            response.skills[0].skill_id,
            "soridormi.express_attention",
        )
        self.assertEqual(
            response.skills[0].args,
            {
                "style": "neutral",
                "duration_s": 2.4,
                "hold_fraction": 0.35,
            },
        )
        self.assertTrue(response.skills[0].requires_confirmation)
        self.assertTrue(response.metadata["optional_body_cue"])
        self.assertEqual(response.metadata["ability_id"], "social.thinking_pose")
        self.assertEqual(response.metadata["ability_status"], "sim_only")

    def test_deep_thought_body_cue_is_sim_safe_only(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.enable_interaction_response = True
        assistant.enable_soridormi_skills = True
        assistant.auto_confirm_sim_skills = True
        assistant.action_dry_run = False
        decision = RouteDecision(
            route="deep_thought",
            agents=["deepthinking_agent", "speaker_agent"],
            language="en-US",
        )

        response = assistant._deep_thought_body_cue_response(
            decision,
            "Please think this through.",
        )

        self.assertIsNone(response)

    def test_unavailable_ability_response_is_language_matched(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        response = assistant._ability_unavailable_response(
            "social.look_at_user",
            language=None,
            user_text="请看着我。",
        )

        self.assertEqual(response.speech[0].text, "抱歉，我现在还没有这个能力。")
        self.assertEqual(response.metadata["ability_id"], "social.look_at_user")
        self.assertEqual(response.metadata["ability_status"], "stub")

    def test_router_exception_on_embodied_text_fails_closed(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        response = assistant._router_exception_safe_response(
            "Please walk ahead quickly for 10 minutes.",
            context={},
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(
            response.speech[0].text,
            "I couldn't route that movement safely. Please try again.",
        )
        self.assertEqual(
            response.metadata["source"],
            "host_router_exception_safe_fallback",
        )

    def test_router_exception_on_plain_text_can_use_direct_llm(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        response = assistant._router_exception_safe_response(
            "Tell me a quick joke.",
            context={},
        )

        self.assertIsNone(response)

    def test_auto_confirm_suppresses_confirmation_only_speech_chunk(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        assistant.session_log = MethodType(session_log, assistant)
        response = InteractionResponse(
            speech=[
                {"text": "I will walk forward quickly for 15 seconds."},
                {"text": "Can you confirm this action?"},
            ],
            skills=[
                {
                    "request_id": "walk-1",
                    "skill_id": "soridormi.walk_forward",
                    "requires_confirmation": True,
                }
            ],
        )

        assistant._suppress_auto_confirm_confirmation_speech(
            response,
            exempted_request_ids={"walk-1"},
            session_id=session_id,
        )

        self.assertEqual(
            [item.text for item in response.speech],
            ["I will walk forward quickly for 15 seconds."],
        )
        self.assertEqual(response.metadata["auto_confirm_suppressed_confirmation_speech"], 1)

    def test_direct_llm_prompt_preserves_chromie_robot_identity(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.voice_system_prompt = "Answer briefly for spoken playback."
        assistant.mind = MindManager(default_mind_profile())
        assistant.conversation_state = ConversationStateManager(enabled=True)
        assistant.conversation_state.record_user_turn(
            "sid-prev",
            "Hello, how are you?",
            route="chat",
            intent="small_talk",
        )
        assistant.conversation_state.record_assistant_turn(
            "sid-prev",
            "Hello. I am listening.",
        )

        prompt = assistant._build_direct_llm_prompt(
            "Can you walk forward for 15 seconds?",
            "sid-now",
            fallback_reason="agent_exception",
            route="robot_action",
        )

        self.assertIn("You are Chromie speaking as the robot herself", prompt)
        self.assertIn("name: Chromie", prompt)
        self.assertIn("age: 6 years old", prompt)
        self.assertIn("not a backend text model", prompt)
        self.assertIn("Never say you are text-based", prompt)
        self.assertIn("Direct fallback reason: agent_exception", prompt)
        self.assertIn("Route hint: robot_action", prompt)
        self.assertIn("Hello. I am listening.", prompt)
        self.assertIn("do not claim you can only respond to text", prompt)

    async def test_input_barge_in_does_not_cancel_body_before_routing(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_generation = 0
        assistant.playback_start_waiters = {}
        assistant.active_synthesis_tasks = set()
        assistant.pending_audio = {0: (0, b"audio", 48000, "old-sid", None)}
        assistant.playback_queue = asyncio.Queue()
        assistant.next_playback_order = 4
        assistant.synthesis_order = 7
        logs: list[str] = []
        aborts = 0

        class _Runtime:
            cancel_calls = 0

            async def cancel_all(self) -> None:
                self.cancel_calls += 1

        async def abort_output_stream(self: VoiceAssistant) -> None:
            nonlocal aborts
            aborts += 1

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            logs.append(message % args)

        assistant.interaction_runtime = _Runtime()
        assistant.abort_output_stream = MethodType(abort_output_stream, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.active_llm_task = asyncio.create_task(asyncio.sleep(60))
        assistant.active_interaction_task = asyncio.create_task(asyncio.sleep(60))
        synthesis_task = asyncio.create_task(asyncio.sleep(60))
        assistant.active_synthesis_tasks.add(synthesis_task)
        await assistant.playback_queue.put((0, 0, b"queued", 48000, "old-sid", None))

        try:
            await assistant.interrupt_output(new_session_id="new-sid")
            await asyncio.sleep(0)

            self.assertEqual(assistant.playback_generation, 1)
            self.assertEqual(assistant.pending_audio, {})
            self.assertTrue(assistant.playback_queue.empty())
            self.assertEqual(assistant.next_playback_order, 0)
            self.assertEqual(assistant.synthesis_order, 0)
            self.assertEqual(aborts, 1)
            self.assertTrue(assistant.active_llm_task.cancelled())
            self.assertTrue(synthesis_task.cancelled())
            self.assertFalse(assistant.active_interaction_task.cancelled())
            self.assertEqual(assistant.interaction_runtime.cancel_calls, 0)
            self.assertEqual(logs, ["interrupt_previous_audio_done: playback_generation=1"])
        finally:
            assistant.active_llm_task.cancel()
            assistant.active_interaction_task.cancel()
            synthesis_task.cancel()
            await asyncio.gather(
                assistant.active_llm_task,
                assistant.active_interaction_task,
                synthesis_task,
                return_exceptions=True,
            )

    async def test_final_deep_thought_response_can_keep_ack_playback_queue(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        reset_calls = 0
        done_calls = 0

        async def reset_playback_ordering(self: VoiceAssistant) -> None:
            nonlocal reset_calls
            reset_calls += 1

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        def maybe_session_done(self: VoiceAssistant, sid: str | None) -> None:
            nonlocal done_calls
            done_calls += 1

        class _Runtime:
            async def execute(
                self,
                response: InteractionResponse,
                *,
                session_id: str | None,
                confirmed_request_ids: set[str] | None = None,
            ) -> SkillRuntimeResult:
                del session_id, confirmed_request_ids
                return SkillRuntimeResult(
                    interaction_id=response.interaction_id,
                    status="completed",
                )

        assistant.reset_playback_ordering = MethodType(reset_playback_ordering, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant.interaction_runtime = _Runtime()
        response = InteractionResponse(speech=[{"text": "Here is the plan."}])

        await assistant.execute_interaction_response(
            response,
            session_id,
            reset_playback=False,
        )
        await assistant.execute_interaction_response(
            response,
            session_id,
            reset_playback=True,
        )

        self.assertEqual(reset_calls, 1)
        self.assertEqual(done_calls, 2)

    async def test_nonterminal_body_cue_does_not_mark_session_done(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        done_calls = 0

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        def maybe_session_done(self: VoiceAssistant, sid: str | None) -> None:
            nonlocal done_calls
            done_calls += 1

        class _Runtime:
            async def execute(
                self,
                response: InteractionResponse,
                *,
                session_id: str | None,
                confirmed_request_ids: set[str] | None = None,
            ) -> SkillRuntimeResult:
                del session_id, confirmed_request_ids
                return SkillRuntimeResult(
                    interaction_id=response.interaction_id,
                    status="completed",
                )

        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant.interaction_runtime = _Runtime()

        await assistant.execute_interaction_response(
            InteractionResponse(
                skills=[{"skill_id": "soridormi.express_attention"}],
                metadata={"optional_body_cue": True},
            ),
            session_id,
            reset_playback=False,
            mark_session_done=False,
        )

        self.assertEqual(done_calls, 0)
        self.assertFalse(assistant.sessions.state[session_id]["llm_done"])

    async def test_cancelled_interaction_closes_missing_skill_requests(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        closed: list[tuple[str | None, str]] = []

        async def reset_playback_ordering(self: VoiceAssistant) -> None:
            return None

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        def maybe_session_done(self: VoiceAssistant, sid: str | None) -> None:
            return None

        def record_experience(
            self: VoiceAssistant,
            *,
            response: InteractionResponse,
            execution: SkillRuntimeResult | None,
            session_id: str | None,
        ) -> None:
            return None

        class _ConversationState:
            def update_pending_task_status_for_request_id(
                self,
                *,
                request_id: str | None,
                status: str,
            ) -> bool:
                closed.append((request_id, status))
                return True

        class _Runtime:
            async def execute(
                self,
                response: InteractionResponse,
                *,
                session_id: str | None,
                confirmed_request_ids: set[str] | None = None,
            ) -> SkillRuntimeResult:
                del confirmed_request_ids
                return SkillRuntimeResult(
                    interaction_id=response.interaction_id,
                    status="cancelled",
                    results=[
                        {
                            "request_id": "speech-1",
                            "skill_id": "chromie.speak",
                            "status": "completed",
                        }
                    ],
                )

        assistant.reset_playback_ordering = MethodType(reset_playback_ordering, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant._record_experience = MethodType(record_experience, assistant)
        assistant.conversation_state = _ConversationState()
        assistant.interaction_runtime = _Runtime()

        await assistant.execute_interaction_response(
            InteractionResponse(
                speech=[{"id": "speech-1", "text": "Moving."}],
                skills=[
                    {"request_id": "walk-1", "skill_id": "soridormi.walk_forward"},
                    {"request_id": "turn-1", "skill_id": "soridormi.turn_left"},
                ],
            ),
            session_id,
        )

        self.assertEqual(
            closed,
            [
                ("speech-1", "completed"),
                ("walk-1", "cancelled"),
                ("turn-1", "cancelled"),
            ],
        )

    async def test_interaction_speech_can_wait_until_playback_starts(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            del text
            await asyncio.sleep(0)
            self.resolve_playback_start_waiter(
                generation,
                order,
                session_id,
                started=True,
                reason="test_playback_start",
            )

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)

        result = await assistant._schedule_interaction_speech(
            {
                "text": "La la, walking with you.",
                "metadata": {
                    "session_id": session_id,
                    "wait_for_playback_start": True,
                    "playback_start_timeout_ms": 500,
                },
            }
        )

        self.assertTrue(result["scheduled"])
        self.assertTrue(result["playback_started"])
        self.assertEqual(result["order"], 0)
        self.assertEqual(assistant.playback_start_waiters, {})

    async def test_interaction_speech_splits_long_text_into_ordered_chunks(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 20
        assistant.tts_min_chunk_chars = 1
        assistant.tts_flush_chars = 160
        seen: list[tuple[int, str]] = []

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            seen.append((order, text))
            if order == 0:
                self.resolve_playback_start_waiter(
                    generation,
                    order,
                    session_id,
                    started=True,
                    reason="test_playback_start",
                )
            await asyncio.sleep(0)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)

        result = await assistant._schedule_interaction_speech(
            {
                "text": "First chunk. Second chunk. Third chunk.",
                "metadata": {
                    "session_id": session_id,
                    "wait_for_playback_start": True,
                    "playback_start_timeout_ms": 500,
                },
            }
        )
        pending = list(assistant.active_synthesis_tasks)
        if pending:
            await asyncio.gather(*pending)

        self.assertTrue(result["scheduled"])
        self.assertTrue(result["playback_started"])
        self.assertEqual(result["chunks"], 3)
        self.assertEqual(result["orders"], [0, 1, 2])
        self.assertEqual(
            seen,
            [
                (0, "First chunk."),
                (1, "Second chunk."),
                (2, "Third chunk."),
            ],
        )

    async def test_single_tts_worker_pipelines_next_chunk_during_playback(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.playback_start_waiters = {}
        assistant.active_synthesis_tasks = set()
        assistant.playback_queue = asyncio.Queue()
        assistant.playback_task = None
        assistant.pending_audio = {}
        assistant.next_playback_order = 0
        assistant.synthesis_semaphore = asyncio.Semaphore(1)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 40
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160
        assistant.tts_url = "ws://tts"
        assistant.speaker_id = "default"
        assistant.tts_ws_retries = 1
        assistant.tts_ws_retry_delay_ms = 0
        assistant.default_tts_rate = 44100
        assistant.output_rate = 44100
        assistant.is_playing_audio = False
        assistant.save_audio_enabled = False

        events: list[tuple[str, int]] = []
        first_playback_started = asyncio.Event()
        second_request_started = asyncio.Event()

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            self.sessions.log(sid, message, *args)

        def maybe_session_done(self: VoiceAssistant, sid: str | None) -> None:
            self.sessions.maybe_done(sid)

        def save_audio(
            self: VoiceAssistant,
            data: bytes,
            prefix: str,
            session_id: str | None = None,
        ) -> None:
            del self, data, prefix, session_id

        async def play_audio(
            self: VoiceAssistant,
            audio_bytes: bytes,
            source_rate: int | None,
            generation: int,
            sid: str | None,
        ) -> None:
            del audio_bytes, source_rate, generation, sid
            order = self.next_playback_order
            events.append(("playback_start", order))
            if order == 0:
                first_playback_started.set()
                await asyncio.wait_for(second_request_started.wait(), timeout=1.0)
            await asyncio.sleep(0)
            events.append(("playback_end", order))

        class _FakeTtsWebSocket:
            def __init__(self) -> None:
                self._messages: list[str | bytes] = []

            async def send(self, payload: str) -> None:
                data = json.loads(payload)
                order = int(str(data["request_id"]).rsplit("-", 1)[-1])
                events.append(("tts_request", order))
                if order == 1:
                    second_request_started.set()
                self._messages = [
                    json.dumps({"type": "start", "sample_rate": 44100}),
                    b"\x00\x00" * 441,
                    json.dumps({"type": "end"}),
                ]

            def __aiter__(self) -> "_FakeTtsWebSocket":
                return self

            async def __anext__(self) -> str | bytes:
                if not self._messages:
                    raise StopAsyncIteration
                await asyncio.sleep(0)
                return self._messages.pop(0)

        class _FakeConnect:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                del args, kwargs
                self.ws = _FakeTtsWebSocket()

            async def __aenter__(self) -> _FakeTtsWebSocket:
                return self.ws

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: object | None,
            ) -> None:
                del exc_type, exc, tb

        original_connect = getattr(orchestrator_module.websockets, "connect", None)
        orchestrator_module.websockets.connect = _FakeConnect  # type: ignore[attr-defined]
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant.save_audio = MethodType(save_audio, assistant)
        assistant.play_audio = MethodType(play_audio, assistant)

        try:
            scheduled = await assistant.schedule_tts_text(
                "Okay. I will explain the next safe step.",
                session_id,
            )
            await asyncio.wait_for(first_playback_started.wait(), timeout=1.0)
            await asyncio.wait_for(second_request_started.wait(), timeout=1.0)
            pending = list(assistant.active_synthesis_tasks)
            if pending:
                await asyncio.gather(*pending)
            await assistant.playback_queue.put((None, None, None, None, None, None))
            if assistant.playback_task is not None:
                await asyncio.wait_for(assistant.playback_task, timeout=1.0)
        finally:
            if original_connect is None:
                delattr(orchestrator_module.websockets, "connect")
            else:
                orchestrator_module.websockets.connect = original_connect

        self.assertTrue(scheduled["scheduled"])
        self.assertEqual(scheduled["chunks"], 2)
        self.assertLess(
            events.index(("tts_request", 1)),
            events.index(("playback_end", 0)),
        )

    async def test_tts_splitter_groups_tiny_fragments_without_swallowing_long_chunk(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "Too fast. Walking normally. "
            "La la, tiny steps and circuits bright, I am walking through the light."
        )

        self.assertEqual(
            chunks,
            [
                "Too fast.",
                "Walking normally. La la, tiny steps and circuits bright, I am walking through the light.",
            ],
        )

    def test_tts_splitter_preserves_fast_first_section(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 40
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "Okay. I will check the route, then I will explain the next safe step."
        )

        self.assertEqual(
            chunks,
            [
                "Okay.",
                "I will check the route, then I will explain the next safe step.",
            ],
        )

    def test_tts_splitter_allows_tiny_complete_first_sentence(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 8
        assistant.tts_chunk_chars = 40
        assistant.tts_min_chunk_chars = 20
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "Hello. I am doing well and ready to help."
        )

        self.assertEqual(
            chunks,
            [
                "Hello.",
                "I am doing well and ready to help.",
            ],
        )

    def test_tts_splitter_keeps_sentences_intact_below_service_limit(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 16
        assistant.tts_chunk_chars = 40
        assistant.tts_min_chunk_chars = 20
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            'I apologize, but your input "Yeah, so you guys" is incomplete. '
            "Could you please provide a full request or question so I can assist you?"
        )

        self.assertEqual(
            chunks,
            [
                'I apologize, but your input "Yeah, so you guys" is incomplete.',
                "Could you please provide a full request or question so I can assist you?",
            ],
        )

    def test_tts_splitter_does_not_split_ready_sentence_by_length(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 16
        assistant.tts_chunk_chars = 40
        assistant.tts_min_chunk_chars = 20
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "Hello! I am functioning correctly and ready to assist you. "
            "How can I help you today?"
        )

        self.assertEqual(
            chunks,
            [
                "Hello!",
                "I am functioning correctly and ready to assist you.",
                "How can I help you today?",
            ],
        )

    def test_tts_splitter_keeps_substantial_followup_sentences_separate(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 16
        assistant.tts_chunk_chars = 120
        assistant.tts_min_chunk_chars = 20
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "Hello! I am doing well, thank you for asking. "
            "I am ready to help you with whatever you need."
        )

        self.assertEqual(
            chunks,
            [
                "Hello!",
                "I am doing well, thank you for asking.",
                "I am ready to help you with whatever you need.",
            ],
        )

    def test_tts_splitter_uses_clause_boundaries_for_long_sentence(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 16
        assistant.tts_chunk_chars = 120
        assistant.tts_min_chunk_chars = 20
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "I can help you practice English, check simple ideas, plan small tasks, "
            "and keep you company while we work."
        )

        self.assertEqual(
            chunks,
            [
                "I can help you practice English,",
                "check simple ideas, plan small tasks,",
                "and keep you company while we work.",
            ],
        )

    def test_tts_splitter_splits_chinese_sentences_without_spaces(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 16
        assistant.tts_chunk_chars = 40
        assistant.tts_min_chunk_chars = 20
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text("你好。我可以帮你。")

        self.assertEqual(chunks, ["你好。", "我可以帮你。"])

    def test_tts_splitter_does_not_make_tiny_fragment_without_sentence_boundary(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 8
        assistant.tts_chunk_chars = 40
        assistant.tts_min_chunk_chars = 20
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "I am doing well and ready to help."
        )

        self.assertEqual(chunks, ["I am doing well and ready to help."])

    def test_tts_splitter_does_not_split_one_medium_sentence_for_first_chunk(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 40
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "I will explain the route carefully without creating another section."
        )

        self.assertEqual(
            chunks,
            ["I will explain the route carefully without creating another section."],
        )


if __name__ == "__main__":
    unittest.main()
