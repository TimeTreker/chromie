from __future__ import annotations

import asyncio
import unittest
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult
from shared.chromie_contracts.route import RouteDecision as SharedRouteDecision


class _Sessions:
    def __init__(self, session_id: str) -> None:
        self.state = {session_id: {"llm_done": False}}
        self.correlations: list[dict[str, Any]] = []

    def update_trace_correlations(
        self,
        session_id: str,
        **correlations: Any,
    ) -> None:
        self.correlations.append(
            {"session_id": session_id, **correlations}
        )


class _ConversationState:
    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.user_turns: list[dict[str, Any]] = []
        self.accepted_turns: list[dict[str, Any]] = []

    def prepare_for_user_text(
        self,
        user_text: str,
        sid: str,
    ) -> dict[str, Any]:
        del user_text, sid
        return {
            "conversation_id": self.conversation_id,
            "started_new": False,
        }

    def record_accepted_user_turn(
        self,
        sid: str,
        user_text: str,
        *,
        metadata: dict[str, Any],
    ) -> None:
        self.accepted_turns.append(
            {"sid": sid, "text": user_text, "metadata": metadata}
        )

    def record_user_turn(
        self,
        sid: str,
        user_text: str,
        *,
        route: str,
        intent: str,
        metadata: dict[str, Any],
    ) -> None:
        self.user_turns.append(
            {
                "sid": sid,
                "text": user_text,
                "route": route,
                "intent": intent,
                "metadata": metadata,
            }
        )


class CognitiveGatewayRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_deterministic_ignore_stays_suppressed_without_goal_interpreter_result(
        self,
    ) -> None:
        for core_mode in ("unavailable", "raises"):
            with self.subTest(core_mode=core_mode):
                session_id = f"turn-ignore-{core_mode}"
                assistant = VoiceAssistant.__new__(VoiceAssistant)
                assistant.cognitive_runtime_mode = "apply"
                assistant.conversation_state = _ConversationState(
                    "conversation-ignore"
                )
                assistant.sessions = _Sessions(session_id)
                assistant.active_llm_task = None
                model_calls: list[str] = []
                done_calls: list[str] = []

                class _CoreInterpreter:
                    async def interpret_turn(
                        self,
                        *args: Any,
                        **kwargs: Any,
                    ) -> RouteDecision:
                        del self, args, kwargs
                        raise RuntimeError("cognitive core unavailable")

                async def get_http_session(
                    self: VoiceAssistant,
                ) -> object:
                    del self
                    return object()

                async def confirmation_reply(
                    self: VoiceAssistant,
                    user_text: str,
                    sid: str,
                    **kwargs: Any,
                ) -> bool:
                    del self, user_text, sid, kwargs
                    return False

                async def process_llm_tts(
                    self: VoiceAssistant,
                    user_text: str,
                    sid: str,
                    **kwargs: Any,
                ) -> None:
                    del self, user_text, kwargs
                    model_calls.append(sid)

                def build_context(
                    self: VoiceAssistant,
                    sid: str,
                ) -> dict[str, Any]:
                    del self, sid
                    return {
                        "conversation_id": "conversation-ignore",
                        "history": [],
                    }

                def maybe_session_done(
                    self: VoiceAssistant,
                    sid: str,
                ) -> None:
                    del self
                    done_calls.append(sid)

                assistant.agent_client = _CoreInterpreter()
                assistant.get_http_session = MethodType(
                    get_http_session,
                    assistant,
                )
                assistant._handle_confirmation_reply = MethodType(
                    confirmation_reply,
                    assistant,
                )
                assistant.process_llm_tts = MethodType(
                    process_llm_tts,
                    assistant,
                )
                assistant.build_context = MethodType(build_context, assistant)
                assistant.maybe_session_done = MethodType(
                    maybe_session_done,
                    assistant,
                )
                assistant._cognitive_core_exception_safe_response = (
                    lambda *args, **kwargs: None
                )
                assistant.session_log = lambda *args, **kwargs: None

                await assistant.handle_routed_text(
                    "um",
                    session_id,
                    channel="voice",
                )
                await asyncio.sleep(0)

                self.assertEqual(model_calls, [])
                self.assertIsNone(assistant.active_llm_task)
                self.assertEqual(
                    assistant.sessions.state[session_id]["llm_done"],
                    True,
                )
                self.assertEqual(done_calls, [session_id])
                self.assertEqual(
                    len(assistant.conversation_state.user_turns),
                    1,
                )
                recorded = assistant.conversation_state.user_turns[0]
                self.assertEqual(recorded["route"], "ignore")
                envelope = recorded["metadata"]["user_turn_envelope"]
                self.assertEqual(envelope["admission"], "suppress")
                self.assertEqual(envelope["attention"]["disposition"], "suppress")
                self.assertEqual(envelope["reflex"]["action"], "ignore")
                self.assertEqual(
                    envelope["reflex"]["trigger"],
                    "noise_or_filler",
                )


if __name__ == "__main__":
    unittest.main()
