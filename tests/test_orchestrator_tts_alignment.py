from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from orchestrator.runtime.interaction_coordinator import CapabilityInteractionDispatch
from orchestrator.runtime.host_settings import HostSettingsSnapshot
from orchestrator.runtime.mind import MindManager
from orchestrator.runtime.session import SessionTracker
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from orchestrator.schemas.route import RouteDecision
from agent.app.cognitive_core.goal_interpreter.schema import RouteDecision as AgentRouteDecision
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.interaction import InteractionResponse, CapabilityResult


class OrchestratorTtsAlignmentTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _configure_model_generation(assistant: VoiceAssistant) -> None:
        assistant.host_settings = HostSettingsSnapshot.from_env(
            project_root=Path("/tmp"),
            environ={},
        )

    async def test_fast_first_speech_enters_current_turn_context_only_after_playback(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_start_waiters = {}
        assistant._turn_speech_events = {}
        assistant._turn_speech_event_by_playback_key = {}
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: " ".join(str(text).strip().split()),
            assistant,
        )
        assistant.session_log = MethodType(
            lambda self, sid, message, *args: None,
            assistant,
        )
        key = assistant.playback_start_key(3, 7, "sid-fast")
        assistant.playback_start_waiters[key] = asyncio.get_running_loop().create_future()

        event = assistant._register_turn_speech_event(
            session_id="sid-fast",
            generation=3,
            orders=[7],
            text="好呀，我帮你看看。",
            stage="fast_first",
            purpose="acknowledge_and_check",
            route="tool",
            intent="capability:chromie.weather.lookup",
            commitment="checking_only",
        )

        self.assertIsNotNone(event)
        self.assertEqual(assistant._delivered_turn_speech_events("sid-fast"), [])
        assistant.resolve_playback_start_waiter(
            3,
            7,
            "sid-fast",
            started=True,
            reason="playback_start",
        )
        delivered = assistant._delivered_turn_speech_events("sid-fast")
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["status"], "playback_started")
        self.assertEqual(delivered[0]["text"], "好呀，我帮你看看。")

    async def test_failure_experience_recovers_user_text_from_accepted_dialogue(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.conversation_state = ConversationStateManager(enabled=True)
        assistant.conversation_state.record_accepted_user_turn(
            "sid-failure",
            "帮我找重庆龙兴天街附近好吃的地方。",
            metadata={"source": "cognitive_gateway_admitted_dialogue"},
        )
        captured: list[InteractionResponse] = []

        class Recorder:
            def record_interaction(self, *, response, **kwargs):
                del kwargs
                captured.append(response)
                return None

        assistant.experience = Recorder()
        assistant.episode_recorder = Recorder()
        assistant.mind = types.SimpleNamespace(profile=default_mind_profile())
        assistant.sessions = types.SimpleNamespace(
            interaction_session_capture_reference=lambda sid: None,
            update_trace_correlations=lambda *args, **kwargs: None,
            attach_episode_evidence=lambda *args, **kwargs: None,
        )
        assistant.session_log = MethodType(
            lambda self, sid, message, *args: None,
            assistant,
        )
        response = InteractionResponse(
            status="error",
            speech=[],
            capabilities=[],
            metadata={"source": "test_failure"},
        )

        assistant._record_experience(
            response=response,
            execution=None,
            session_id="sid-failure",
            errors=["semantic failure"],
        )

        self.assertEqual(len(captured), 2)
        for recorded in captured:
            context = recorded.metadata["experience_context"]
            self.assertEqual(
                context["user_text"],
                "帮我找重庆龙兴天街附近好吃的地方。",
            )
            self.assertEqual(context["route_source"], "cognitive_gateway_admitted_dialogue")
            self.assertEqual(
                context["conversation_id"],
                assistant.conversation_state.conversation_id,
            )

    def test_runtime_ready_greeting_prompt_is_a_human_like_wake_up(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}',
            assistant,
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "warm, curious, and natural",
            assistant,
        )

        prompt = assistant._runtime_ready_greeting_prompt(
            local_now=datetime(
                2026,
                8,
                1,
                7,
                30,
                tzinfo=timezone(timedelta(hours=8)),
            )
        )

        self.assertIn("has just woken up", prompt)
        self.assertIn("naturally says after waking up", prompt)
        self.assertIn('"local_period":"morning"', prompt)
        self.assertIn('"utc_offset":"+08:00"', prompt)
        self.assertIn("Do not quote the exact clock time", prompt)
        self.assertIn("quiet grounding", prompt)
        self.assertIn("Speak only in zh-CN", prompt)
        self.assertIn("not a device or an adult professional", prompt)
        self.assertIn("family's six-year-old secretary", prompt)
        self.assertIn("Use no vocative, addressee noun", prompt)
        self.assertIn("spontaneous first-person delight", prompt)
        self.assertIn("Do not default to a formal morning, afternoon, or evening salutation", prompt)
        self.assertIn("a cheerful first-person wake-up line is preferred", prompt)
        self.assertNotIn("greet the room with only a general or time-of-day greeting", prompt)
        self.assertIn("Return only a JSON object", prompt)
        self.assertIn("Do not explain the task", prompt)

    def test_runtime_ready_greeting_prompt_changes_with_grounded_local_period(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}',
            assistant,
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "warm, curious, and natural",
            assistant,
        )
        local_tz = timezone(timedelta(hours=8))

        morning = assistant._runtime_ready_greeting_prompt(
            local_now=datetime(2026, 8, 1, 8, 0, tzinfo=local_tz)
        )
        evening = assistant._runtime_ready_greeting_prompt(
            local_now=datetime(2026, 8, 1, 19, 0, tzinfo=local_tz)
        )

        self.assertIn('"local_period":"morning"', morning)
        self.assertIn('"local_period":"evening"', evening)
        self.assertNotEqual(morning, evening)

    async def test_runtime_ready_greeting_uses_llm_text_before_live_microphone_turns(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.runtime_ready_greeting_enabled = True
        assistant.runtime_ready_greeting_speech_enabled = True
        assistant.runtime_ready_greeting_text = ""
        assistant.runtime_ready_greeting_timeout_ms = 1000
        assistant.audio_input_mode = "device"
        assistant.audio_output_mode = "device"
        assistant.playback_start_waiters = {}
        assistant.next_playback_order = 0
        scheduled_texts: list[tuple[str, str | None]] = []

        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(),
            assistant,
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()),
            assistant,
        )

        async def generate_runtime_ready_greeting(
            self: VoiceAssistant,
        ) -> tuple[str, str]:
            del self
            return "嗨，我醒啦！", "llm:qwen3:4b"

        assistant._generate_runtime_ready_greeting = MethodType(
            generate_runtime_ready_greeting,
            assistant,
        )

        async def schedule_tts_text(
            self: VoiceAssistant,
            text: str,
            session_id: str | None,
        ) -> dict[str, Any]:
            scheduled_texts.append((text, session_id))
            key = self.playback_start_key(0, 0, session_id)
            waiter = asyncio.get_running_loop().create_future()
            self.playback_start_waiters[key] = waiter

            async def complete() -> None:
                await asyncio.sleep(0)
                waiter.set_result(True)
                self.next_playback_order = 1

            asyncio.create_task(complete())
            return {
                "scheduled": True,
                "generation": 0,
                "order": 0,
                "last_order": 0,
            }

        assistant.schedule_tts_text = MethodType(schedule_tts_text, assistant)

        await assistant._announce_runtime_ready()

        self.assertEqual(
            scheduled_texts,
            [("嗨，我醒啦！", None)],
        )
        self.assertEqual(assistant.next_playback_order, 1)

    async def test_runtime_ready_greeting_generation_uses_python_310_compatible_timeout(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.runtime_ready_greeting_text = ""
        assistant.runtime_ready_greeting_fallback_text = "我醒啦，今天也一起开心吧！"
        assistant.runtime_ready_greeting_model = "qwen3:4b"
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant.runtime_ready_greeting_num_predict = 32
        assistant.runtime_ready_greeting_generation_timeout_ms = 1000
        assistant.ollama_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(),
            assistant,
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()),
            assistant,
        )
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}',
            assistant,
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "warm and curious",
            assistant,
        )

        class FakeResponse:
            status = 200

            async def __aenter__(self) -> "FakeResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                return json.dumps({"response": json.dumps({"text": "早上好，我醒啦！"}), "done_reason": "stop"})

        class FakeSession:
            def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
                self.url = url
                self.payload = json
                return FakeResponse()

        session = FakeSession()

        async def get_http_session(self: VoiceAssistant) -> FakeSession:
            del self
            return session

        assistant.get_http_session = MethodType(get_http_session, assistant)

        original_timeout = getattr(asyncio, "timeout", None)
        if hasattr(asyncio, "timeout"):
            delattr(asyncio, "timeout")
        try:
            text, source = await assistant._generate_runtime_ready_greeting()
        finally:
            if original_timeout is not None:
                asyncio.timeout = original_timeout

        self.assertEqual(text, "早上好，我醒啦！")
        self.assertEqual(source, "llm:qwen3:4b")
        self.assertEqual(session.url, assistant.llm_url)
        self.assertEqual(session.payload["model"], "qwen3:4b")
        self.assertIs(session.payload["think"], False)
        self.assertEqual(
            session.payload["format"],
            assistant._spoken_text_response_schema(max_chars=24),
        )
        self.assertEqual(session.payload["options"]["num_predict"], 32)


    async def test_runtime_ready_greeting_rejects_reasoning_prose_and_falls_back(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.runtime_ready_greeting_text = ""
        assistant.runtime_ready_greeting_fallback_text = "我醒啦，今天也一起开心吧！"
        assistant.runtime_ready_greeting_model = "qwen3:4b"
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant.runtime_ready_greeting_num_predict = 32
        assistant.runtime_ready_greeting_generation_timeout_ms = 1000
        assistant.ollama_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}',
            assistant,
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "warm and curious",
            assistant,
        )

        class FakeResponse:
            status = 200

            async def __aenter__(self) -> "FakeResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                return json.dumps(
                    {
                        "response": (
                            "First, the user wants me to write a greeting. "
                            "I need to make sure it sounds natural."
                        ),
                        "done_reason": "length",
                    }
                )

        class FakeSession:
            def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
                del url, json
                return FakeResponse()

        async def get_http_session(self: VoiceAssistant) -> FakeSession:
            del self
            return FakeSession()

        assistant.get_http_session = MethodType(get_http_session, assistant)

        text, source = await assistant._generate_runtime_ready_greeting()

        self.assertEqual(text, "我醒啦，今天也一起开心吧！")
        self.assertEqual(source, "fallback")

    async def test_runtime_ready_greeting_suppresses_separate_thinking_field(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.runtime_ready_greeting_text = ""
        assistant.runtime_ready_greeting_fallback_text = "我醒啦，今天也一起开心吧！"
        assistant.runtime_ready_greeting_model = "qwen3:4b"
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant.runtime_ready_greeting_num_predict = 32
        assistant.runtime_ready_greeting_generation_timeout_ms = 1000
        assistant.ollama_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}',
            assistant,
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "warm and curious",
            assistant,
        )

        class FakeResponse:
            status = 200

            async def __aenter__(self) -> "FakeResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                return json.dumps(
                    {
                        "thinking": "I should produce a short childlike greeting.",
                        "response": json.dumps({"text": "早呀，我醒啦！"}),
                        "done_reason": "stop",
                    }
                )

        class FakeSession:
            def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
                del url, json
                return FakeResponse()

        async def get_http_session(self: VoiceAssistant) -> FakeSession:
            del self
            return FakeSession()

        assistant.get_http_session = MethodType(get_http_session, assistant)

        with self.assertLogs(level="WARNING") as warning_logs:
            text, source = await assistant._generate_runtime_ready_greeting()

        self.assertEqual(text, "早呀，我醒啦！")
        self.assertEqual(source, "llm:qwen3:4b")
        self.assertTrue(
            any("suppressed non-spoken model thinking" in line for line in warning_logs.output)
        )

    async def test_runtime_ready_greeting_generation_timeout_falls_back(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.runtime_ready_greeting_text = ""
        assistant.runtime_ready_greeting_fallback_text = "我醒啦，今天也一起开心吧！"
        assistant.runtime_ready_greeting_model = "qwen3:4b"
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant.runtime_ready_greeting_num_predict = 32
        assistant.runtime_ready_greeting_generation_timeout_ms = 1
        assistant.ollama_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(),
            assistant,
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()),
            assistant,
        )
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}',
            assistant,
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "warm and curious",
            assistant,
        )

        class SlowResponse:
            status = 200

            async def __aenter__(self) -> "SlowResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                await asyncio.sleep(1)
                return json.dumps({"response": json.dumps({"text": "不应该返回"}), "done_reason": "stop"})

        class SlowSession:
            def post(self, url: str, json: dict[str, Any]) -> SlowResponse:
                del url, json
                return SlowResponse()

        async def get_http_session(self: VoiceAssistant) -> SlowSession:
            del self
            return SlowSession()

        assistant.get_http_session = MethodType(get_http_session, assistant)

        text, source = await assistant._generate_runtime_ready_greeting()

        self.assertEqual(text, "我醒啦，今天也一起开心吧！")
        self.assertEqual(source, "fallback")

    async def test_runtime_ready_greeting_falls_back_when_generation_fails(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.runtime_ready_greeting_text = ""
        assistant.runtime_ready_greeting_fallback_text = "我醒啦，今天也一起开心吧！"
        assistant.runtime_ready_greeting_model = "qwen3:4b"
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant.runtime_ready_greeting_num_predict = 32
        assistant.runtime_ready_greeting_generation_timeout_ms = 1000
        assistant.ollama_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(),
            assistant,
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()),
            assistant,
        )
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}',
            assistant,
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "warm and curious",
            assistant,
        )

        async def get_http_session(self: VoiceAssistant) -> Any:
            del self
            raise RuntimeError("Ollama unavailable")

        assistant.get_http_session = MethodType(get_http_session, assistant)

        text, source = await assistant._generate_runtime_ready_greeting()

        self.assertEqual(text, "我醒啦，今天也一起开心吧！")
        self.assertEqual(source, "fallback")

    async def test_runtime_ready_greeting_is_skipped_for_injected_audio(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.runtime_ready_greeting_enabled = True
        assistant.runtime_ready_greeting_speech_enabled = True
        assistant.runtime_ready_greeting_text = ""
        assistant.runtime_ready_greeting_timeout_ms = 1000
        assistant.audio_input_mode = "stdin"
        assistant.audio_output_mode = "discard"
        scheduled = False
        generated = False

        async def generate_runtime_ready_greeting(
            self: VoiceAssistant,
        ) -> tuple[str, str]:
            del self
            nonlocal generated
            generated = True
            return "嗨，我醒啦！", "llm:qwen3:4b"

        async def schedule_tts_text(
            self: VoiceAssistant,
            text: str,
            session_id: str | None,
        ) -> dict[str, Any]:
            del self, text, session_id
            nonlocal scheduled
            scheduled = True
            return {"scheduled": True}

        assistant._generate_runtime_ready_greeting = MethodType(
            generate_runtime_ready_greeting,
            assistant,
        )
        assistant.schedule_tts_text = MethodType(schedule_tts_text, assistant)

        await assistant._announce_runtime_ready()

        self.assertFalse(generated)
        self.assertFalse(scheduled)

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
                return {request.request_id for request in response.capabilities}


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
        async def resolve_confirmation(
            self: VoiceAssistant,
            user_text: str,
            *,
            session_id: str,
            pending: Any,
        ) -> str:
            del self, user_text, session_id, pending
            return "reject"

        assistant._resolve_pending_confirmation_meaning = MethodType(
            resolve_confirmation,
            assistant,
        )
        natural_prompt = (
            "I can't do those actions together yet, but I can walk first and "
            "blink next. Is that okay? Say “yes” and I’ll get started!"
        )
        response = InteractionResponse(
            interaction_id="interaction-confirm-denied",
            capabilities=[
                {
                    "request_id": "walk-1",
                    "capability_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "blink-1",
                    "capability_id": "soridormi.blink_eyes",
                    "metadata": {"source_goal_ids": ["goal-blink"]},
                },
            ],
            metadata={
                "planning_result": "composed_plan",
                "semantic_plan_confirmation_required": True,
                "confirmation_prompt": natural_prompt,
            },
        )

        self.assertTrue(
            await assistant._stage_interaction_confirmation(
                response,
                "sid-confirm",
                language="en-US",
            )
        )
        pending = assistant.confirmation_dialogue.pending
        assert pending is not None
        self.assertEqual(pending.prompt, natural_prompt)
        self.assertEqual(launched[0][0].speech[0].text, natural_prompt)
        self.assertEqual(
            [
                item["work_status"]
                for item in assistant.conversation_state.active_goal_snapshots()
            ],
            ["awaiting_confirmation", "awaiting_confirmation"],
        )
        self.assertTrue(
            await assistant._handle_confirmation_reply("no", "sid-confirm")
        )
        self.assertEqual(
            [
                item["responsibility_status"]
                for item in assistant.conversation_state.active_goal_snapshots()
            ],
            ["open", "open"],
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
                return {request.request_id for request in response.capabilities}


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
        async def resolve_confirmation(
            self: VoiceAssistant,
            user_text: str,
            *,
            session_id: str,
            pending: Any,
        ) -> str:
            del self, user_text, session_id, pending
            return "confirm"

        assistant._resolve_pending_confirmation_meaning = MethodType(
            resolve_confirmation,
            assistant,
        )
        response = InteractionResponse(
            interaction_id="interaction-confirm-approved",
            capabilities=[
                {
                    "request_id": "walk-1",
                    "capability_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "blink-1",
                    "capability_id": "soridormi.blink_eyes",
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
                item["work_status"]
                for item in assistant.conversation_state.active_goal_snapshots()
            ],
            ["scheduled", "scheduled"],
        )
        self.assertEqual(len(launched), 2)
        self.assertEqual(launched[-1][1], {"walk-1", "blink-1"})

    async def test_model_authored_deep_thought_ack_is_scheduled(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.core_generated_fast_speech_enabled = True
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
            fast_speech={
                "text": "我想一下。",
                "purpose": "thinking",
                "commitment": "prelude_only",
                "must_not_claim_completion": True,
            },
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
        self.assertEqual(seen, [(0, "我想一下。")])
        self.assertEqual(
            assistant.sessions.state[session_id]["scheduled_tts"],
            1,
        )

    async def test_stale_session_cannot_reserve_a_playback_order(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        stale_session_id = assistant.sessions.create()
        current_session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 1
        assistant.playback_generation = 7
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant._tts_text_by_generation = {}
        scheduled: list[tuple[int, str | None, str]] = []

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            del self, generation
            scheduled.append((order, session_id, text))

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)
        assistant.ensure_playback_worker = MethodType(
            lambda self: None,
            assistant,
        )

        stale = await assistant.schedule_tts_sentence(
            "late speech from the old turn",
            stale_session_id,
        )
        current = await assistant.schedule_tts_sentence(
            "current turn speech",
            current_session_id,
        )
        pending = list(assistant.active_synthesis_tasks)
        if pending:
            await asyncio.gather(*pending)

        self.assertEqual(stale, {"scheduled": False, "reason": "stale_playback"})
        self.assertTrue(current["scheduled"])
        self.assertEqual(current["order"], 1)
        self.assertEqual(assistant.synthesis_order, 2)
        self.assertEqual(
            scheduled,
            [(1, current_session_id, "current turn speech")],
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
        self.assertFalse(scheduled)
        self.assertEqual(seen, [])
        self.assertEqual(
            assistant.sessions.state[session_id]["scheduled_tts"],
            0,
        )

    async def test_low_confidence_deep_thought_schedules_model_speak_first(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.core_generated_fast_speech_enabled = True
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

    def test_fast_first_response_text_uses_goal_interpreter_generated_speech(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.core_generated_fast_speech_enabled = True

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
                RouteDecision(
                    route="tool",
                    intent="weather_query",
                    language="zh-CN",
                    fast_speech={
                        "text": "好的，我马上查北京今天的天气。",
                        "purpose": "acknowledge",
                        "commitment": "checking_only",
                    },
                ),
                "今天北京下雨了没有？",
            )
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
                        "text": "Hmm, let me think about that.",
                        "purpose": "acknowledge",
                        "commitment": "prelude_only",
                        "claim_state": "none",
                        "claimed_capability_ids": [],
                        "claimed_goal_ids": [],
                    },
                ),
                "Walk forward for 15 seconds.",
            ),
            "Hmm, let me think about that.",
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="robot_action",
                    intent="robot_action",
                    language="en-US",
                    fast_speech={
                        "text": "I will handle that.",
                        "purpose": "acknowledge_and_check",
                        "commitment": "checking_only",
                    },
                ),
                "Walk forward for 15 seconds.",
            )
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


    def test_tool_fast_first_response_uses_general_enablement_and_typed_contract(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.core_generated_fast_speech_enabled = True
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

        self.assertEqual(
            assistant._fast_first_response_text(
                decision,
                "今天北京天气怎么样？",
            ),
            "好的，我查一下北京今天的天气。",
        )

        assistant.fast_first_response_enabled = False
        self.assertIsNone(
            assistant._fast_first_response_text(
                decision,
                "今天北京天气怎么样？",
            )
        )

    def test_dynamic_fast_speech_is_default_off_and_requires_full_contract(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        decision = RouteDecision(
            route="robot_action",
            intent="capability:soridormi.walk_forward",
            fast_speech={
                "text": "I will get ready.",
                "purpose": "acknowledge",
                "commitment": "prelude_only",
            },
        )

        self.assertIsNone(
            assistant._fast_first_response_text(decision, "Move forward.")
        )

        assistant.core_generated_fast_speech_enabled = True
        self.assertEqual(
            assistant._fast_first_response_text(decision, "Move forward."),
            "I will get ready.",
        )
        self.assertIsNone(
            assistant._fast_first_response_text(
                RouteDecision(
                    route="robot_action",
                    intent="capability:soridormi.walk_forward",
                    fast_speech="I will get ready.",
                ),
                "Move forward.",
            )
        )

    def test_chat_framed_bare_fast_speech_gets_generic_progress_contract(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.core_generated_fast_speech_enabled = True
        agent_decision = AgentRouteDecision.model_validate(
            {
                "route": "chat",
                "intent": "native_response",
                "confidence": 0.95,
                "fast_speech": "嗯，我先看看能不能找到水瓶，然后帮你拿一杯水！",
                "responsibilities": [
                    {
                        "local_ref": "water",
                        "outcome": "拿一杯水",
                        "bindings": {"resource": "水"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                ],
                "progress": [],
            }
        )
        self.assertIsNotNone(agent_decision.fast_speech)
        assert agent_decision.fast_speech is not None
        self.assertEqual(agent_decision.fast_speech.purpose, "acknowledge")
        self.assertEqual(agent_decision.fast_speech.commitment, "prelude_only")

        # HTTP/compatibility serialization preserves the typed claim envelope, so
        # the Host still receives a complete FastSpeech contract and can play it.
        decision = RouteDecision.model_validate(
            agent_decision.model_dump(mode="json", exclude_none=True)
        )
        self.assertEqual(
            assistant._fast_first_response_text(decision, "帮我拿杯水。"),
            "嗯，我先看看能不能找到水瓶，然后帮你拿一杯水！",
        )

    def test_dynamic_fast_speech_uses_typed_claim_authority_not_wording_rules(self) -> None:
        # The Host applies transport checks only; semantic wording is reviewed
        # by the Cognitive Core and represented by typed claim provenance.
        self.assertEqual(
            VoiceAssistant._safe_immediate_route_speech("I finished it."),
            "I finished it.",
        )
        self.assertIsNone(
            VoiceAssistant._validated_fast_speech_payload_text(
                {
                    "text": "I finished it.",
                    "purpose": "acknowledge",
                    "commitment": "prelude_only",
                    "claim_state": "completed",
                    "claimed_capability_ids": [],
                    "claimed_goal_ids": [],
                    "must_not_claim_completion": True,
                },
                route="robot_action",
            )
        )
        self.assertIsNone(
            VoiceAssistant._validated_fast_speech_payload_text(
                {
                    "text": "I can do that.",
                    "purpose": "acknowledge",
                    "commitment": "prelude_only",
                    "claim_state": "none",
                    "claimed_capability_ids": ["soridormi.walk_forward"],
                    "claimed_goal_ids": [],
                    "must_not_claim_completion": True,
                },
                route="robot_action",
            )
        )

    def test_memory_fast_speech_accepts_typed_precommit_acknowledgement(self) -> None:
        self.assertEqual(
            VoiceAssistant._validated_fast_speech_payload_text(
                {
                    "text": "Okay, I will remember it.",
                    "purpose": "acknowledge",
                    "commitment": "prelude_only",
                    "claim_state": "none",
                    "claimed_capability_ids": [],
                    "claimed_goal_ids": [],
                    "must_not_claim_completion": True,
                },
                route="memory",
            ),
            "Okay, I will remember it.",
        )

    def test_tool_fast_speech_accepts_typed_pre_result_acknowledgement(self) -> None:
        self.assertEqual(
            VoiceAssistant._validated_fast_speech_payload_text(
                {
                    "text": "Let me check the weather.",
                    "purpose": "acknowledge_and_check",
                    "commitment": "checking_only",
                    "claim_state": "none",
                    "claimed_capability_ids": [],
                    "claimed_goal_ids": [],
                    "must_not_claim_completion": True,
                },
                route="tool",
            ),
            "Let me check the weather.",
        )

    def test_unsafe_deep_thought_speak_first_does_not_trigger_host_wording(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.core_generated_fast_speech_enabled = True
        decision = RouteDecision(
            route="deep_thought",
            intent="plan_task",
            language="en-US",
            speak_first="That's taken care of.",
        )

        self.assertIsNone(
            assistant._deep_thought_ack_text(decision, "Please make a plan.")
        )

    def test_incomplete_deep_thought_fast_speech_fails_closed(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.core_generated_fast_speech_enabled = True
        decision = RouteDecision(
            route="deep_thought",
            intent="plan_task",
            language="en-US",
            fast_speech={"text": "Let me think."},
        )

        self.assertIsNone(
            assistant._deep_thought_ack_text(decision, "Please make a plan.")
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
        workflow_messages = [
            str(item.get("message") or "")
            for item in assistant.sessions.state[session_id]["workflow_events"]
            if isinstance(item, dict)
        ]
        self.assertTrue(
            any(
                "reason=goal_interpreter_no_fast_speech" in message
                for message in workflow_messages
            )
        )


    async def test_fast_first_delivery_prefers_dynamic_speech_then_cache_fallback(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        calls: list[str] = []

        async def schedule_dynamic(
            self: VoiceAssistant,
            decision: RouteDecision,
            user_text: str,
            session_id: str,
        ) -> bool:
            del decision, user_text, session_id
            calls.append("dynamic")
            return True

        def start_hedge(
            self: VoiceAssistant,
            decision: RouteDecision,
            user_text: str,
            session_id: str,
        ) -> None:
            del decision, user_text, session_id
            calls.append("cache")
            return None

        assistant._schedule_fast_first_response = MethodType(
            schedule_dynamic, assistant
        )
        assistant._start_fast_first_audio_hedge = MethodType(
            start_hedge, assistant
        )
        decision = RouteDecision(
            route="tool",
            intent="capability:chromie.weather.lookup",
            language="zh-CN",
        )

        scheduled, hedge = await orchestrator_module._start_fast_first_delivery(
            assistant,
            decision,
            "帮我查重庆明天的天气。",
            "sid-dynamic",
        )

        self.assertTrue(scheduled)
        self.assertIsNone(hedge)
        self.assertEqual(calls, ["dynamic"])

        async def miss_dynamic(
            self: VoiceAssistant,
            decision: RouteDecision,
            user_text: str,
            session_id: str,
        ) -> bool:
            del self, decision, user_text, session_id
            calls.append("dynamic-miss")
            return False

        sentinel = object()

        def fallback_hedge(
            self: VoiceAssistant,
            decision: RouteDecision,
            user_text: str,
            session_id: str,
        ) -> object:
            del self, decision, user_text, session_id
            calls.append("cache-fallback")
            return sentinel

        assistant._schedule_fast_first_response = MethodType(
            miss_dynamic, assistant
        )
        assistant._start_fast_first_audio_hedge = MethodType(
            fallback_hedge, assistant
        )
        scheduled, hedge = await orchestrator_module._start_fast_first_delivery(
            assistant,
            decision,
            "帮我查重庆明天的天气。",
            "sid-fallback",
        )

        self.assertFalse(scheduled)
        self.assertIs(hedge, sentinel)
        self.assertEqual(calls[-2:], ["dynamic-miss", "cache-fallback"])

    def test_scheduled_fast_speech_is_projected_for_downstream_deduplication(self) -> None:
        decision = RouteDecision(
            route="tool",
            intent="capability:chromie.weather.lookup",
            language="zh-CN",
            fast_speech={
                "text": "好嘛，我帮你看看重庆明天的天气。",
                "purpose": "acknowledge_and_check",
                "commitment": "checking_only",
                "must_not_claim_completion": True,
            },
            metadata={
                "fast_first_response": {
                    "text": "好嘛，我帮你看看重庆明天的天气。",
                    "generation": 4,
                    "orders": [9],
                    "speech_event_id": "speech_event_weather",
                }
            },
        )

        context = orchestrator_module._context_with_scheduled_fast_speech(
            {"history": []},
            decision,
            scheduled=True,
        )

        self.assertEqual(len(context["scheduled_turn_speech"]), 1)
        item = context["scheduled_turn_speech"][0]
        self.assertEqual(item["status"], "scheduled")
        self.assertEqual(item["orders"], [9])
        self.assertFalse(item["external_fact_evidence"])
        self.assertFalse(item["completion_evidence"])

    async def test_interaction_speech_reuses_fast_first_audio_without_resynthesis(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_start_waiters = {}
        assistant._turn_speech_events = {}
        assistant._turn_speech_event_by_playback_key = {}
        assistant.session_log = MethodType(
            lambda self, sid, message, *args: None,
            assistant,
        )
        event = assistant._register_turn_speech_event(
            session_id="sid-reuse",
            generation=2,
            orders=[5],
            text="好，我帮你查一下。",
            stage="fast_first",
            purpose="acknowledge_and_check",
            route="tool",
            intent="capability:chromie.weather.lookup",
            commitment="checking_only",
        )
        self.assertIsNotNone(event)
        assert event is not None
        event["status"] = "playback_started"

        async def fail_if_resynthesized(
            self: VoiceAssistant, text: str, session_id: str | None
        ) -> dict[str, Any]:
            del self, text, session_id
            raise AssertionError("reused speech must not schedule TTS again")

        assistant.schedule_tts_text = MethodType(
            fail_if_resynthesized,
            assistant,
        )
        result = await assistant._schedule_interaction_speech(
            {
                "text": "好，我帮你查一下。",
                "metadata": {
                    "session_id": "sid-reuse",
                    "reuse_current_turn_speech": True,
                    "reused_speech_event_id": event["event_id"],
                    "reused_speech_generation": 2,
                    "reused_speech_orders": [5],
                    "wait_for_playback_start": True,
                },
            }
        )

        self.assertTrue(result["scheduled"])
        self.assertTrue(result["reused"])
        self.assertTrue(result["playback_started"])
        self.assertEqual(result["order"], 5)

    async def test_undelivered_fast_speech_is_fulfilled_once_by_reused_stage(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_start_waiters = {}
        assistant._turn_speech_events = {}
        assistant._turn_speech_event_by_playback_key = {}
        assistant.session_log = MethodType(
            lambda self, sid, message, *args: None,
            assistant,
        )
        event = assistant._register_turn_speech_event(
            session_id="sid-fallback",
            generation=2,
            orders=[5],
            text="好，我帮你查一下。",
            stage="fast_first",
            purpose="acknowledge_and_check",
            route="tool",
            intent="capability:chromie.weather.lookup",
            commitment="checking_only",
        )
        self.assertIsNotNone(event)
        assert event is not None
        event["status"] = "not_delivered"
        scheduled_texts: list[str] = []

        async def schedule_fallback(
            self: VoiceAssistant, text: str, session_id: str | None
        ) -> dict[str, Any]:
            scheduled_texts.append(text)
            key = self.playback_start_key(3, 6, session_id)
            waiter = asyncio.get_running_loop().create_future()
            waiter.set_result(True)
            self.playback_start_waiters[key] = waiter
            return {
                "scheduled": True,
                "generation": 3,
                "order": 6,
                "orders": [6],
            }

        assistant.schedule_tts_text = MethodType(schedule_fallback, assistant)
        result = await assistant._schedule_interaction_speech(
            {
                "text": "好，我帮你查一下。",
                "metadata": {
                    "session_id": "sid-fallback",
                    "phase": "immediate",
                    "speech_act": "acknowledge_and_check",
                    "commitment_state": "evaluating",
                    "reuse_current_turn_speech": True,
                    "reused_speech_event_id": event["event_id"],
                    "reused_speech_generation": 2,
                    "reused_speech_orders": [5],
                    "wait_for_playback_start": True,
                },
            }
        )

        self.assertEqual(scheduled_texts, ["好，我帮你查一下。"])
        self.assertTrue(result["scheduled"])
        self.assertFalse(result["reused"])
        self.assertTrue(result["playback_started"])
        self.assertEqual(
            result["fallback_for_undelivered_speech_event_id"],
            event["event_id"],
        )

    def test_cognitive_core_exception_does_not_semantically_classify_embodied_text(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        response = assistant._cognitive_core_exception_safe_response(
            "Please walk ahead quickly for 10 minutes.",
            context={},
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(
            response.speech[0].text,
            "Sorry, I got stuck for a moment and haven't done anything yet. Can you say it again?",
        )
        self.assertEqual(
            response.metadata["source"],
            "host_cognitive_core_exception_safe_fallback",
        )

    def test_cognitive_core_exception_on_plain_text_does_not_create_second_semantic_authority(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        response = assistant._cognitive_core_exception_safe_response(
            "Tell me a quick joke.",
            context={},
        )

        self.assertEqual(
            response.speech[0].text,
            "Sorry, I got stuck for a moment and haven't done anything yet. Can you say it again?",
        )
        self.assertEqual(response.metadata["effect_execution"], "not_authorized")
        self.assertFalse(response.metadata["semantic_fallback"])

    def test_cognitive_core_exception_chinese_fallback_is_natural_and_fail_closed(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        response = assistant._cognitive_core_exception_safe_response(
            "前面有一瓶水，你帮我拿过来好吗？",
            context={},
        )

        self.assertEqual(
            response.speech[0].text,
            "对不起，我刚才卡住了，什么都还没做呢。你再说一遍好吗？",
        )
        self.assertNotIn("执行任何操作", response.speech[0].text)
        self.assertNotIn("处理好你的请求", response.speech[0].text)
        self.assertEqual(response.metadata["effect_execution"], "not_authorized")
        self.assertFalse(response.metadata["semantic_fallback"])

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

        self.assertIn("Use the supplied owner-approved identity and self model", prompt)
        self.assertIn('"entity_id":"chromie"', prompt)
        self.assertIn('"social_presentation"', prompt)
        self.assertIn('"self_reference":"Chromie"', prompt)
        self.assertIn('"kind":"human child"', prompt)
        self.assertIn("Personality expression JSON", prompt)
        self.assertIn('"answer_style"', prompt)
        self.assertIn('"age_description":"6 years old"', prompt)
        self.assertIn('"family_role":"the family\'s secretary"', prompt)
        self.assertNotIn('"internal_components"', prompt)
        self.assertIn("identity.identity_answer_guidance", prompt)
        self.assertNotIn("Never say you are text-based", prompt)
        self.assertIn("Direct fallback reason: agent_exception", prompt)
        self.assertIn("Route hint: robot_action", prompt)
        self.assertIn("Hello. I am listening.", prompt)
        self.assertIn("no valid motion result was produced", prompt)
        self.assertTrue(prompt.endswith("Chromie:"))

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
            async def submit_response(
                self,
                response: InteractionResponse,
                *,
                session_id: str | None,
                confirmed_request_ids: set[str] | None = None,
            ) -> CapabilityInteractionDispatch:
                del session_id, confirmed_request_ids
                execution = CapabilityRuntimeResult(
                    interaction_id=response.interaction_id,
                    status="completed",
                )
                return CapabilityInteractionDispatch(
                    source_response=response,
                    runtime_response=response,
                    receipt=None,
                    immediate_execution=execution,
                    preexecuted_results=[],
                    preexecuted_traces=[],
                )

            async def wait_dispatch(
                self,
                dispatch: CapabilityInteractionDispatch,
            ) -> CapabilityRuntimeResult:
                assert dispatch.immediate_execution is not None
                return dispatch.immediate_execution

        async def consume_non_cognitive(
            self: VoiceAssistant,
            dispatch: CapabilityInteractionDispatch,
            **kwargs: Any,
        ) -> CapabilityRuntimeResult:
            del kwargs
            return await self.interaction_runtime.wait_dispatch(dispatch)

        assistant.reset_playback_ordering = MethodType(reset_playback_ordering, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant.interaction_runtime = _Runtime()
        assistant.playback_generation = 0
        assistant.active_capability_result_tasks = {}
        assistant._consume_detached_non_cognitive_dispatch = MethodType(
            consume_non_cognitive, assistant
        )
        response = InteractionResponse(speech=[{"text": "Here is the plan."}])

        await assistant._dispatch_detached_interaction(
            response, session_id, confirmed_request_ids=None,
            reset_playback=False, mark_session_done=True,
        )
        await asyncio.gather(*list(assistant.active_capability_result_tasks))
        await assistant._dispatch_detached_interaction(
            response, session_id, confirmed_request_ids=None,
            reset_playback=True, mark_session_done=True,
        )
        await asyncio.gather(*list(assistant.active_capability_result_tasks))

        self.assertEqual(reset_calls, 1)
        self.assertEqual(done_calls, 2)

    async def test_nonterminal_interaction_does_not_mark_session_done(self) -> None:
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
            async def submit_response(
                self,
                response: InteractionResponse,
                *,
                session_id: str | None,
                confirmed_request_ids: set[str] | None = None,
            ) -> CapabilityInteractionDispatch:
                del session_id, confirmed_request_ids
                execution = CapabilityRuntimeResult(
                    interaction_id=response.interaction_id,
                    status="completed",
                )
                return CapabilityInteractionDispatch(
                    source_response=response, runtime_response=response, receipt=None,
                    immediate_execution=execution, preexecuted_results=[], preexecuted_traces=[],
                )

            async def wait_dispatch(
                self, dispatch: CapabilityInteractionDispatch
            ) -> CapabilityRuntimeResult:
                assert dispatch.immediate_execution is not None
                return dispatch.immediate_execution

        async def consume_non_cognitive(
            self: VoiceAssistant, dispatch: CapabilityInteractionDispatch, **kwargs: Any
        ) -> CapabilityRuntimeResult:
            del kwargs
            return await self.interaction_runtime.wait_dispatch(dispatch)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant.interaction_runtime = _Runtime()
        assistant.playback_generation = 0
        assistant.active_capability_result_tasks = {}
        assistant._consume_detached_non_cognitive_dispatch = MethodType(
            consume_non_cognitive, assistant
        )

        await assistant._dispatch_detached_interaction(
            InteractionResponse(
                capabilities=[{"capability_id": "soridormi.express_attention"}],
            ),
            session_id,
            confirmed_request_ids=None,
            reset_playback=False,
            mark_session_done=False,
        )
        await asyncio.gather(*list(assistant.active_capability_result_tasks))

        self.assertEqual(done_calls, 0)
        self.assertFalse(assistant.sessions.state[session_id]["llm_done"])

    async def test_scheduled_confirmation_without_playback_is_not_history(
        self,
    ) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        recorded: list[InteractionResponse] = []

        class _ConversationState:
            def record_agent_result(
                self,
                sid: str | None,
                response: InteractionResponse,
            ) -> None:
                del sid
                recorded.append(response)

        assistant.conversation_state = _ConversationState()
        assistant.session_log = lambda *args, **kwargs: None
        response = assistant._host_speech_response(
            "Please confirm.",
            style="confirm",
        )
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            results=[
                CapabilityResult(
                    request_id=response.speech[0].id,
                    capability_id="chromie.speak",
                    status="completed",
                    output={"scheduled": True},
                )
            ],
        )

        delivered = assistant._record_successfully_delivered_speech(
            response,
            execution,
            session_id="sid-confirmation-failed",
            log_event="test_confirmation_history",
        )

        self.assertEqual(delivered, 0)
        self.assertEqual(recorded, [])

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

    async def test_interaction_speech_registers_delivered_turn_evidence(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_start_waiters = {}
        assistant._turn_speech_events = {}
        assistant._turn_speech_event_by_playback_key = {}
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: " ".join(str(text).strip().split()),
            assistant,
        )
        assistant.session_log = MethodType(
            lambda self, sid, message, *args: None,
            assistant,
        )

        async def schedule(
            self: VoiceAssistant,
            text: str,
            session_id: str | None,
        ) -> dict[str, Any]:
            self.playback_start_waiters[
                self.playback_start_key(4, 9, session_id)
            ] = asyncio.get_running_loop().create_future()
            return {
                "scheduled": True,
                "generation": 4,
                "order": 9,
                "orders": [9],
                "chunks": 1,
            }

        assistant.schedule_tts_text = MethodType(schedule, assistant)
        result = await assistant._schedule_interaction_speech(
            {
                "text": "The Moon reflects sunlight.",
                "metadata": {
                    "session_id": "sid-final",
                    "turn_id": "turn-final",
                    "phase": "final",
                    "speech_act": "result",
                    "delivery_role": "response",
                    "commitment_state": "completed",
                    "source_goal_ids": ["goal-moon"],
                    "canonical_plan_id": "plan-moon",
                    "canonical_plan_fingerprint": "fingerprint-moon",
                    "claims": ["result"],
                    "must_not_claim_completion": False,
                },
            }
        )

        self.assertIsNotNone(result.get("speech_event_id"))
        self.assertEqual(assistant._delivered_turn_speech_events("sid-final"), [])
        assistant.resolve_playback_start_waiter(
            4,
            9,
            "sid-final",
            started=True,
            reason="playback_start",
        )
        delivered = assistant._delivered_turn_speech_events("sid-final")
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["text"], "The Moon reflects sunlight.")
        self.assertEqual(delivered[0]["stage"], "final")
        self.assertEqual(delivered[0]["purpose"], "result")
        self.assertEqual(delivered[0]["commitment"], "completed")
        self.assertEqual(delivered[0]["turn_id"], "turn-final")
        self.assertEqual(delivered[0]["source_goal_ids"], ["goal-moon"])
        self.assertEqual(delivered[0]["canonical_plan_id"], "plan-moon")
        self.assertEqual(
            delivered[0]["canonical_plan_fingerprint"],
            "fingerprint-moon",
        )
        self.assertEqual(delivered[0]["claims"], ["result"])
        self.assertFalse(delivered[0]["must_not_claim_completion"])

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

    async def test_provider_pcm_starts_playback_before_stream_end(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.playback_generation = 0
        assistant.playback_start_waiters = {}
        assistant.active_synthesis_tasks = set()
        assistant.playback_queue = asyncio.Queue()
        assistant.playback_task = None
        assistant.pending_audio = {}
        assistant.next_playback_order = 0
        assistant.synthesis_semaphore = asyncio.Semaphore(1)
        assistant.tts_url = "ws://tts"
        assistant.speaker_id = "default"
        assistant.tts_ws_retries = 1
        assistant.tts_ws_retry_delay_ms = 0
        assistant.default_tts_rate = 24000
        assistant.output_rate = 24000
        assistant.is_playing_audio = False
        assistant.save_audio_enabled = False

        playback_started = asyncio.Event()
        provider_allowed_to_end = asyncio.Event()
        played_chunks: list[bytes] = []

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
            del self, source_rate, generation, sid
            played_chunks.append(audio_bytes)
            playback_started.set()
            provider_allowed_to_end.set()

        class _StreamingTtsWebSocket:
            def __init__(self) -> None:
                self._index = 0

            async def send(self, payload: str) -> None:
                del payload

            def __aiter__(self) -> "_StreamingTtsWebSocket":
                return self

            async def __anext__(self) -> str | bytes:
                self._index += 1
                if self._index == 1:
                    return json.dumps({"type": "start", "sample_rate": 24000})
                if self._index == 2:
                    return b"\x01\x00" * 240
                if self._index == 3:
                    await asyncio.wait_for(provider_allowed_to_end.wait(), timeout=1.0)
                    return b"\x02\x00" * 240
                if self._index == 4:
                    return json.dumps({"type": "end"})
                raise StopAsyncIteration

        class _FakeConnect:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                del args, kwargs
                self.ws = _StreamingTtsWebSocket()

            async def __aenter__(self) -> _StreamingTtsWebSocket:
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

        assistant.ensure_playback_worker()
        synthesis = asyncio.create_task(
            assistant.synthesize_one("Stream this sentence.", 0, session_id, 0)
        )
        try:
            await asyncio.wait_for(playback_started.wait(), timeout=1.0)
            self.assertFalse(synthesis.done())
            await asyncio.wait_for(synthesis, timeout=1.0)
            await assistant.playback_queue.put((None, None, None, None, None, None))
            if assistant.playback_task is not None:
                await asyncio.wait_for(assistant.playback_task, timeout=1.0)
        finally:
            if original_connect is None:
                delattr(orchestrator_module.websockets, "connect")
            else:
                orchestrator_module.websockets.connect = original_connect

        self.assertEqual(len(played_chunks), 2)
        self.assertEqual(
            assistant.sessions.state[session_id]["played_tts"],
            1,
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

    def test_tts_splitter_keeps_compact_chinese_weather_answer_in_one_request(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_first_chunk_chars = 16
        assistant.tts_chunk_chars = 120
        assistant.tts_cjk_chunk_chars = 36
        assistant.tts_min_chunk_chars = 20
        assistant.tts_cjk_min_chunk_chars = 8
        assistant.tts_flush_chars = 160
        assistant.tts_max_text_chars = 220

        text = "很热，重庆现在约37℃，体感42℃，最高39℃。"

        self.assertEqual(assistant.split_tts_text(text), [text])

    def test_failure_speech_contract_rejects_incomplete_sentence(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: " ".join(str(text).strip().split()),
            assistant,
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()),
            assistant,
        )

        with self.assertRaisesRegex(RuntimeError, "incomplete sentence"):
            assistant._validate_spoken_text_contract(
                "I understood what you need, but I couldn't get it ready this",
                purpose="cognitive failure response",
                max_chars=72,
                one_sentence=True,
                require_terminal_punctuation=True,
                language="en-US",
            )

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
