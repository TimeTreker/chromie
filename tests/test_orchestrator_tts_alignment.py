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
from shared.chromie_contracts.interaction import InteractionResponse, SkillResult


class OrchestratorTtsAlignmentTests(unittest.IsolatedAsyncioTestCase):
    def test_post_interrupt_corrected_decision_is_normal_followup(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        interrupt = RouteDecision(
            route="interrupt",
            intent="stop_current_output",
            confidence=0.99,
            metadata={
                "post_interrupt_review": {"status": "corrected"},
                "post_interrupt_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "explain_phrase",
                    "confidence": 0.86,
                    "language": "en-US",
                    "source": "llm",
                    "speak_first": "Sorry, I misheard that as a stop command.",
                },
            },
        )

        corrected = assistant._post_interrupt_corrected_decision(interrupt)

        self.assertIsNotNone(corrected)
        assert corrected is not None
        self.assertEqual(corrected.route, "chat")
        self.assertFalse(corrected.interrupt_current)
        self.assertTrue(corrected.metadata["post_interrupt_correction"])
        self.assertEqual(
            corrected.metadata["original_interrupt_intent"],
            "stop_current_output",
        )

    def test_post_interrupt_confirmed_decision_has_no_followup(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        interrupt = RouteDecision(
            route="interrupt",
            intent="stop_current_output",
            confidence=0.99,
            metadata={"post_interrupt_review": {"status": "confirmed"}},
        )

        self.assertIsNone(assistant._post_interrupt_corrected_decision(interrupt))

    async def test_multi_goal_confirmation_denial_closes_all_scoped_goals(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.confirmation_dialogue = orchestrator_module.ConfirmationDialogue(
            ttl_s=20.0
        )
        assistant.conversation_state = ConversationStateManager(
            base_conversation_id="orchestrator-confirm-denied"
        )
        assistant.conversation_state.apply_goal_association_resolution(
            {
                "turn_id": "turn-confirm-denied",
                "new_goals": [
                    {
                        "goal_id": "goal-walk",
                        "description": "Walk forward.",
                        "source_text": "Walk forward.",
                    },
                    {
                        "goal_id": "goal-blink",
                        "description": "Blink.",
                        "source_text": "Blink.",
                    },
                ],
                "confidence": 0.95,
                "reason_summary": "Two independent actions.",
            },
            sid="sid-confirm",
            user_text="Walk and blink.",
            route="robot_action",
            intent="compound_action",
            atomic=True,
        )
        launched: list[tuple[InteractionResponse, set[str] | None]] = []

        class _Runtime:
            async def confirmation_request_ids(
                self,
                response: InteractionResponse,
            ) -> set[str]:
                return {request.request_id for request in response.skills}

            async def confirmation_exemption_request_ids(
                self,
                response: InteractionResponse,
            ) -> set[str]:
                del response
                return set()

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            del self, sid, message, args

        def launch_interaction(
            self: VoiceAssistant,
            response: InteractionResponse,
            session_id: str | None,
            *,
            confirmed_request_ids: set[str] | None = None,
            reset_playback: bool = True,
            mark_session_done: bool = True,
        ) -> None:
            del self, session_id, reset_playback, mark_session_done
            launched.append((response, confirmed_request_ids))

        assistant.interaction_runtime = _Runtime()
        assistant.session_log = MethodType(session_log, assistant)
        assistant._launch_interaction = MethodType(launch_interaction, assistant)
        response = InteractionResponse(
            interaction_id="interaction-confirm-denied",
            skills=[
                {
                    "request_id": "walk-1",
                    "skill_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "blink-1",
                    "skill_id": "soridormi.blink_eyes",
                    "metadata": {"source_goal_ids": ["goal-blink"]},
                },
            ],
            metadata={
                "planning_result": "composed_plan",
                "semantic_plan_confirmation_required": True,
            },
        )

        self.assertTrue(
            await assistant._stage_interaction_confirmation(
                response,
                "sid-confirm",
                language="en-US",
            )
        )
        self.assertEqual(
            [
                item["status"]
                for item in assistant.conversation_state.active_goal_snapshots()
            ],
            ["awaiting_confirmation", "awaiting_confirmation"],
        )
        self.assertTrue(
            await assistant._handle_confirmation_reply("no", "sid-confirm")
        )
        self.assertEqual(
            assistant.conversation_state.active_goal_snapshots(),
            [],
        )
        self.assertEqual(
            [
                item["status"]
                for item in assistant.conversation_state.snapshot()["task_contexts"]
            ],
            ["cancelled", "cancelled"],
        )
        self.assertEqual(len(launched), 2)

    async def test_multi_goal_confirmation_approval_schedules_all_scoped_goals(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.confirmation_dialogue = orchestrator_module.ConfirmationDialogue(
            ttl_s=20.0
        )
        assistant.conversation_state = ConversationStateManager(
            base_conversation_id="orchestrator-confirm-approved"
        )
        assistant.conversation_state.apply_goal_association_resolution(
            {
                "turn_id": "turn-confirm-approved",
                "new_goals": [
                    {
                        "goal_id": "goal-walk",
                        "description": "Walk forward.",
                        "source_text": "Walk forward.",
                    },
                    {
                        "goal_id": "goal-blink",
                        "description": "Blink.",
                        "source_text": "Blink.",
                    },
                ],
                "confidence": 0.95,
                "reason_summary": "Two independent actions.",
            },
            sid="sid-confirm",
            user_text="Walk and blink.",
            route="robot_action",
            intent="compound_action",
            atomic=True,
        )
        launched: list[tuple[InteractionResponse, set[str] | None]] = []

        class _Runtime:
            async def confirmation_request_ids(
                self,
                response: InteractionResponse,
            ) -> set[str]:
                return {request.request_id for request in response.skills}

            async def confirmation_exemption_request_ids(
                self,
                response: InteractionResponse,
            ) -> set[str]:
                del response
                return set()

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            del self, sid, message, args

        def launch_interaction(
            self: VoiceAssistant,
            response: InteractionResponse,
            session_id: str | None,
            *,
            confirmed_request_ids: set[str] | None = None,
            reset_playback: bool = True,
            mark_session_done: bool = True,
        ) -> None:
            del self, session_id, reset_playback, mark_session_done
            launched.append((response, confirmed_request_ids))

        assistant.interaction_runtime = _Runtime()
        assistant.session_log = MethodType(session_log, assistant)
        assistant._launch_interaction = MethodType(launch_interaction, assistant)
        response = InteractionResponse(
            interaction_id="interaction-confirm-approved",
            skills=[
                {
                    "request_id": "walk-1",
                    "skill_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "blink-1",
                    "skill_id": "soridormi.blink_eyes",
                    "metadata": {"source_goal_ids": ["goal-blink"]},
                },
            ],
            metadata={
                "planning_result": "composed_plan",
                "semantic_plan_confirmation_required": True,
            },
        )

        self.assertTrue(
            await assistant._stage_interaction_confirmation(
                response,
                "sid-confirm",
                language="en-US",
            )
        )
        self.assertTrue(
            await assistant._handle_confirmation_reply("yes", "sid-confirm")
        )

        self.assertEqual(
            [
                item["status"]
                for item in assistant.conversation_state.active_goal_snapshots()
            ],
            ["scheduled", "scheduled"],
        )
        self.assertEqual(len(launched), 2)
        self.assertEqual(launched[-1][1], {"walk-1", "blink-1"})

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

    async def test_low_confidence_deep_thought_schedules_model_speak_first(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.router_generated_fast_speech_enabled = True
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
            fast_speech={
                "text": "Give me a moment to think that through.",
                "purpose": "thinking",
                "commitment": "prelude_only",
            },
            metadata={
                "thinking_ack_allowed": True,
                "thinking_ack_source": "quick_llm_speak_first",
            },
        )

        scheduled = await assistant._schedule_deep_thought_ack(
            decision,
            "Please figure this out.",
            session_id,
        )
        pending = list(assistant.active_synthesis_tasks)
        if pending:
            await asyncio.gather(*pending)

        self.assertTrue(scheduled)
        self.assertEqual(seen, ["Give me a moment to think that through."])
        self.assertEqual(
            assistant.sessions.state[session_id]["scheduled_tts"],
            1,
        )

    def test_fast_first_response_text_uses_router_generated_speech(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.router_generated_fast_speech_enabled = True

        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(route="chat", intent="general_conversation", language="en-US"),
                "Hello, how are you?",
            )
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="chat",
                    intent="general_conversation",
                    language="en-US",
                    fast_speech={
                        "text": "Let me answer that.",
                        "purpose": "acknowledge",
                        "commitment": "prelude_only",
                    },
                ),
                "Hello, how are you?",
            ),
            "Let me answer that.",
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="deep_thought",
                    intent="mixed_request",
                    language="en-US",
                    routes=[
                        {
                            "route": "chat",
                            "intent": "greeting",
                            "confidence": 0.95,
                            "lane": "immediate_speech",
                            "context_profile": "fast_minimal",
                            "direct_to_tts": True,
                            "text": "Hi, I'm here.",
                            "fast_speech": {
                                "text": "Hi, I'm here.",
                                "purpose": "acknowledge",
                                "commitment": "prelude_only",
                            },
                        },
                        {
                            "route": "deep_thought",
                            "intent": "plan_task",
                            "confidence": 0.8,
                            "lane": "deepthought",
                            "context_profile": "full_mind",
                            "requires_mind": True,
                        },
                    ],
                ),
                "Hi, think about tomorrow.",
            ),
            "Hi, I'm here.",
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(route="chat", intent="fact_question", language="en-US"),
                "What is 2 plus 2?",
            )
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="tool",
                    intent="weather_query",
                    language="zh-CN",
                    metadata={
                        "tool_name": "weather",
                        "weather_query": {"location": "重庆", "date": "today"},
                    },
                ),
                "重庆今天天气怎么样？",
            )
        )
        assistant.fast_first_tool_response_enabled = True
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="tool",
                    intent="weather_query",
                    language="zh-CN",
                    fast_speech={
                        "text": "好的，我查一下重庆今天的天气。",
                        "purpose": "acknowledge_and_check",
                        "commitment": "checking_only",
                    },
                    metadata={
                        "tool_name": "weather",
                        "weather_query": {"location": "重庆", "date": "today"},
                    },
                ),
                "重庆今天天气怎么样？",
            ),
            "好的，我查一下重庆今天的天气。",
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="tool",
                    intent="weather_query",
                    language="en-US",
                    fast_speech={
                        "text": "OK, I’ll check Chongqing’s weather today.",
                        "purpose": "acknowledge_and_check",
                        "commitment": "checking_only",
                    },
                    metadata={
                        "tool_name": "weather",
                        "weather_query": {"location": "Chongqing", "date": "today"},
                    },
                ),
                "what's the weather today in chongqing",
            ),
            "OK, I’ll check Chongqing’s weather today.",
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(route="robot_action", intent="robot_action", language="en-US"),
                "Walk forward for 15 seconds.",
            )
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="robot_action",
                    intent="robot_action",
                    language="en-US",
                    fast_speech={
                        "text": "I’ll check whether I can do that safely.",
                        "purpose": "safety_prelude",
                        "commitment": "needs_confirmation",
                    },
                ),
                "Walk forward for 15 seconds.",
            ),
            "I’ll check whether I can do that safely.",
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="robot_action",
                    intent="robot_action",
                    language="en-US",
                    fast_speech={"text": "I am walking now."},
                ),
                "Walk forward for 15 seconds.",
            )
        )
        self.assertEqual(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="clarify",
                    intent="clarify_target_location",
                    language="en-US",
                    fast_speech={
                        "text": "Which location do you mean?",
                        "purpose": "clarify",
                        "commitment": "needs_confirmation",
                    },
                ),
                "Move over there.",
            ),
            "Which location do you mean?",
        )


    def test_tool_fast_first_response_is_opt_in(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.router_generated_fast_speech_enabled = True
        decision = RouteDecision(
            route="tool",
            intent="weather_query",
            language="zh-CN",
            fast_speech={
                "text": "好的，我查一下北京今天的天气。",
                "purpose": "acknowledge_and_check",
                "commitment": "checking_only",
            },
            metadata={
                "tool_name": "weather",
                "weather_query": {"location": "北京", "date": "today"},
            },
        )

        assistant.fast_first_tool_response_enabled = False
        self.assertIsNone(
            assistant._fast_first_response_text(
                decision,
                "今天北京天气怎么样？",
            )
        )

        assistant.fast_first_tool_response_enabled = True
        self.assertEqual(
            assistant._fast_first_response_text(
                decision,
                "今天北京天气怎么样？",
            ),
            "好的，我查一下北京今天的天气。",
        )

    def test_dynamic_fast_speech_is_default_off_and_requires_full_contract(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.fast_first_tool_response_enabled = True
        decision = RouteDecision(
            route="tool",
            intent="weather_query",
            fast_speech={
                "text": "Let me check the weather.",
                "purpose": "acknowledge_and_check",
                "commitment": "checking_only",
            },
        )

        self.assertIsNone(
            assistant._fast_first_response_text(decision, "What is the weather?")
        )

        assistant.router_generated_fast_speech_enabled = True
        self.assertEqual(
            assistant._fast_first_response_text(decision, "What is the weather?"),
            "Let me check the weather.",
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="tool",
                    intent="weather_query",
                    fast_speech="Let me check the weather.",
                ),
                "What is the weather?",
            )
        )

    def test_dynamic_fast_speech_rejects_terminal_claims(self) -> None:
        unsafe = (
            "I finished it.",
            "I've finished that.",
            "I already took care of it.",
            "That's taken care of.",
            "It is ready.",
            "任务办好了。",
            "处理好了。",
        )

        for text in unsafe:
            with self.subTest(text=text):
                self.assertIsNone(VoiceAssistant._safe_immediate_route_speech(text))

    def test_unsafe_deep_thought_speak_first_uses_trusted_ack(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.router_generated_fast_speech_enabled = True
        decision = RouteDecision(
            route="deep_thought",
            intent="plan_task",
            language="en-US",
            speak_first="That's taken care of.",
        )

        self.assertEqual(
            assistant._deep_thought_ack_text(decision, "Please make a plan."),
            "Okay, let me think about that.",
        )

    def test_incomplete_deep_thought_fast_speech_uses_trusted_ack(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.router_generated_fast_speech_enabled = True
        decision = RouteDecision(
            route="deep_thought",
            intent="plan_task",
            language="en-US",
            fast_speech={"text": "Let me think."},
        )

        self.assertEqual(
            assistant._deep_thought_ack_text(decision, "Please make a plan."),
            "Okay, let me think about that.",
        )

    def test_validated_response_plan_uses_structured_claims_not_phrase_blocking(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        decision = RouteDecision(
            route="deep_thought",
            intent="refine active task",
            language="zh-CN",
            metadata={
                "response_plan": {
                    "immediate": {
                        "text": "好的，我正在确认新的任务要求。",
                        "speech_act": "acknowledge",
                        "commitment_state": "evaluating",
                        "must_not_claim_completion": True,
                        "covers_task_ids": ["task-1"],
                    }
                }
            },
        )
        snapshots = [
            {
                "task_id": "task-1",
                "status": "planning",
                "semantic_goal": {
                    "description": "处理当前请求。",
                    "source_text": "请处理。",
                },
                "goal_version": 1,
                "plan_version": 0,
                "open_information_gaps": [],
                "commitment_state": "evaluating",
            }
        ]

        self.assertEqual(
            assistant._fast_first_response_text(
                decision,
                "改一下要求。",
                task_snapshots=snapshots,
            ),
            "好的，我正在确认新的任务要求。",
        )
        self.assertTrue(decision.metadata["response_plan_validation"]["accepted"])

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

        self.assertFalse(scheduled)
        self.assertEqual(seen, [])
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
        self.assertEqual(response.metadata["ability_status"], "known_missing")

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
            "I heard a movement request, but routing did not produce a valid motion result, so I will not move.",
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

    def test_direct_llm_prompt_uses_chromie_social_self_model(self) -> None:
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

        self.assertIn("Use the supplied owner-approved self model", prompt)
        self.assertIn('"entity_id":"chromie"', prompt)
        self.assertIn('"social_presentation"', prompt)
        self.assertIn('"self_reference":"Chromie"', prompt)
        self.assertNotIn('"kind":"embodied robot"', prompt)
        self.assertNotIn('"age_description"', prompt)
        self.assertIn('"component_id":"language_reasoner"', prompt)
        self.assertIn('"speaker_entity":false', prompt)
        self.assertNotIn("If the user asks who you are", prompt)
        self.assertNotIn("Never say you are text-based", prompt)
        self.assertIn("Direct fallback reason: agent_exception", prompt)
        self.assertIn("Route hint: robot_action", prompt)
        self.assertIn("Hello. I am listening.", prompt)
        self.assertIn("no valid motion result was produced", prompt)

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


    async def test_recoverable_body_failure_stages_confirmation_retry(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.confirmation_dialogue = orchestrator_module.ConfirmationDialogue(
            ttl_s=20.0
        )
        assistant.body_recovery_max_attempts = 1
        assistant.body_recovery_confirmation_ttl_s = 7.0
        execute_calls: list[InteractionResponse] = []
        pending_records: list[dict[str, Any]] = []
        agent_records: list[InteractionResponse] = []

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
            errors: list[str] | None = None,
        ) -> None:
            return None

        class _ConversationState:
            conversation_id = "conv-recovery"

            def update_pending_task_status_for_request_id(
                self,
                *,
                request_id: str | None,
                status: str,
            ) -> bool:
                return True

            def record_agent_result(
                self,
                sid: str | None,
                response: InteractionResponse,
            ) -> None:
                agent_records.append(response)

            def record_pending_task(
                self,
                *,
                sid: str | None,
                task_type: str,
                status: str,
                summary: str,
                metadata: dict[str, Any],
            ) -> None:
                pending_records.append(
                    {
                        "sid": sid,
                        "task_type": task_type,
                        "status": status,
                        "summary": summary,
                        "metadata": metadata,
                    }
                )

        class _Runtime:
            async def execute(
                self,
                response: InteractionResponse,
                *,
                session_id: str | None,
                confirmed_request_ids: set[str] | None = None,
            ) -> SkillRuntimeResult:
                del session_id, confirmed_request_ids
                execute_calls.append(response)
                if len(execute_calls) == 1:
                    return SkillRuntimeResult(
                        interaction_id=response.interaction_id,
                        status="failed",
                        results=[
                            SkillResult(
                                request_id="grasp-1",
                                skill_id="soridormi.grasp_object",
                                status="failed",
                                reason_code="execution_incomplete",
                                output={
                                    "completed": False,
                                    "recoverable": True,
                                    "user_message": "The object slipped.",
                                },
                            )
                        ],
                    )
                return SkillRuntimeResult(
                    interaction_id=response.interaction_id,
                    status="completed",
                )

        assistant.reset_playback_ordering = MethodType(reset_playback_ordering, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant._record_experience = MethodType(record_experience, assistant)
        assistant.conversation_state = _ConversationState()
        assistant.interaction_runtime = _Runtime()

        await assistant.execute_interaction_response(
            InteractionResponse(
                interaction_id="interaction-grasp",
                skills=[
                    {
                        "request_id": "grasp-1",
                        "skill_id": "soridormi.grasp_object",
                        "args": {"object": "cup"},
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id,
            reset_playback=False,
        )

        pending = assistant.confirmation_dialogue.pending
        assert pending is not None
        self.assertIn("recoverable movement issue", pending.prompt)
        self.assertIn("The object slipped", pending.prompt)
        self.assertEqual(
            pending.confirmed_request_ids,
            frozenset({"grasp-1_recovery1"}),
        )
        self.assertEqual(
            pending.response.skills[0].metadata["body_recovery_attempt"],
            1,
        )
        self.assertEqual(pending_records[0]["task_type"], "body_recovery_confirmation")
        self.assertEqual(
            pending_records[0]["metadata"]["retry_request_ids"],
            ["grasp-1_recovery1"],
        )
        self.assertEqual(agent_records[-1].metadata["source"], "host_body_recovery_confirmation")
        self.assertEqual(len(execute_calls), 2)
        self.assertEqual(execute_calls[-1].speech[0].metadata["source"], "host_body_recovery_confirmation")

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

    async def test_playback_barrier_timeout_cancels_all_late_audio_chunks(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.cancelled_playback_orders = set()
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 20
        assistant.tts_min_chunk_chars = 1
        assistant.tts_flush_chars = 160
        played: list[int] = []

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            sid: str | None,
            generation: int,
        ) -> None:
            del self, text, order, sid, generation

        async def play_audio(
            self: VoiceAssistant,
            audio: bytes,
            source_rate: int | None,
            generation: int,
            sid: str | None,
        ) -> None:
            del self, audio, source_rate, generation, sid
            played.append(1)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)
        assistant.play_audio = MethodType(play_audio, assistant)

        result = await assistant._schedule_interaction_speech(
            {
                "text": "First chunk. Second chunk. Third chunk.",
                "metadata": {
                    "session_id": session_id,
                    "wait_for_playback_start": True,
                    "playback_start_timeout_ms": 1,
                },
            }
        )
        pending = list(assistant.active_synthesis_tasks)
        if pending:
            await asyncio.gather(*pending)

        self.assertFalse(result["playback_started"])
        self.assertEqual(result["cancelled_orders"], result["orders"])
        self.assertEqual(
            assistant.sessions.state[session_id]["skipped_tts"],
            len(result["orders"]),
        )

        for order in result["orders"]:
            consumed = await assistant.play_one_order(
                result["generation"],
                order,
                b"\x00\x00" * 100,
                24000,
                session_id,
            )
            self.assertTrue(consumed)
        self.assertEqual(played, [])
        self.assertEqual(assistant.cancelled_playback_orders, set())

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

    def test_tts_splitter_chunks_long_chinese_weather_reply_for_earlier_audio(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 16
        assistant.tts_chunk_chars = 120
        assistant.tts_cjk_chunk_chars = 36
        assistant.tts_min_chunk_chars = 20
        assistant.tts_cjk_min_chunk_chars = 8
        assistant.tts_flush_chars = 160
        assistant.tts_max_text_chars = 220

        text = (
            "北京今天雷雨伴冰雹，当前约31℃，最高31℃、最低25℃，"
            "体感约37℃，降水概率最高约100%，风速约5公里每小时。"
        )
        chunks = assistant.split_tts_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 36 for chunk in chunks))
        self.assertEqual("".join(chunks), text)

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
