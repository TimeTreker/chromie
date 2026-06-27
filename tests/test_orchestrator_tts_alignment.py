from __future__ import annotations

import asyncio
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
from orchestrator.runtime.session import SessionTracker
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from orchestrator.schemas.route import RouteDecision
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
                "Too fast. Walking normally.",
                "La la, tiny steps and circuits bright, I am walking through the light.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
