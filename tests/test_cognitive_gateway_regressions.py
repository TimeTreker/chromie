from __future__ import annotations

import asyncio
import unittest
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult
from shared.chromie_contracts.user_turn import (
    AttentionReviewRequest,
    AttentionReviewResult,
)
from tests.voice_assistant_test_support import bare_voice_assistant


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
        metadata: dict[str, Any],
    ) -> None:
        self.user_turns.append(
            {
                "sid": sid,
                "text": user_text,
                "metadata": metadata,
            }
        )


class CognitiveGatewayRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_deterministic_ignore_stays_suppressed_without_user_meaning_interpreter_result(
        self,
    ) -> None:
        for core_mode in ("unavailable", "raises"):
            with self.subTest(core_mode=core_mode):
                session_id = f"turn-ignore-{core_mode}"
                assistant = bare_voice_assistant()
                assistant.cognitive_runtime_mode = "apply"
                assistant.conversation_state = _ConversationState(
                    "conversation-ignore"
                )
                assistant.sessions = _Sessions(session_id)
                model_calls: list[str] = []
                done_calls: list[str] = []
                confirmation_calls: list[str] = []

                class _CoreInterpreter:
                    async def interpret_turn(
                        self,
                        *args: Any,
                        **kwargs: Any,
                    ) -> CoreInterpretationResult:
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
                    del self, sid, kwargs
                    confirmation_calls.append(user_text)
                    return True

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
                # Ignored noise/filler never reaches pending-confirmation
                # resolution, which would make a model call.
                self.assertEqual(confirmation_calls, [])
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
                envelope = recorded["metadata"]["user_turn_envelope"]
                self.assertEqual(envelope["admission"], "suppress")
                self.assertEqual(envelope["attention"]["disposition"], "suppress")
                self.assertEqual(envelope["reflex"]["action"], "ignore")
                self.assertEqual(
                    envelope["reflex"]["trigger"],
                    "noise_or_filler",
                )

    async def _route_with_pending_confirmation(
        self,
        text: str,
        *,
        disposition: str,
        channel: str = "voice",
    ) -> dict[str, Any]:
        session_id = f"turn-confirm-{disposition}-{channel}"
        assistant = bare_voice_assistant()
        assistant.cognitive_runtime_mode = "apply"
        assistant.conversation_state = _ConversationState("conversation-confirm")
        assistant.sessions = _Sessions(session_id)
        calls: dict[str, Any] = {
            "attention": 0,
            "confirmation": [],
            "core": 0,
            "done": [],
        }

        class _AgentClient:
            async def review_attention(
                self,
                session: object,
                *,
                request: AttentionReviewRequest,
            ) -> AttentionReviewResult:
                del self, session
                calls["attention"] += 1
                return AttentionReviewResult(
                    turn_id=request.turn_id,
                    session_id=request.session_id,
                    context_digest=request.context_digest,
                    disposition=disposition,
                    speech_act=(
                        "ambient_report" if disposition == "suppress" else "reply"
                    ),
                    confidence=0.95,
                    source="cognitive_gateway.attention_review_model",
                    reason="controlled attention result",
                )

            async def interpret_turn(self, *args: Any, **kwargs: Any) -> None:
                del self, args, kwargs
                calls["core"] += 1
                raise AssertionError("confirmation reply must not enter the Core")

        async def get_http_session(self: VoiceAssistant) -> object:
            del self
            return object()

        async def confirmation_reply(
            self: VoiceAssistant,
            user_text: str,
            sid: str,
            *,
            turn_envelope: Any = None,
        ) -> bool:
            del self, sid
            calls["confirmation"].append(
                {"text": user_text, "envelope": turn_envelope}
            )
            return True

        def build_context(self: VoiceAssistant, sid: str) -> dict[str, Any]:
            del self, sid
            return {"conversation_id": "conversation-confirm", "history": []}

        def maybe_session_done(self: VoiceAssistant, sid: str) -> None:
            del self
            calls["done"].append(sid)

        assistant.agent_client = _AgentClient()
        assistant.get_http_session = MethodType(get_http_session, assistant)
        assistant._handle_confirmation_reply = MethodType(
            confirmation_reply,
            assistant,
        )
        assistant.build_context = MethodType(build_context, assistant)
        assistant.maybe_session_done = MethodType(maybe_session_done, assistant)
        assistant._log_goal_list = lambda *args, **kwargs: None
        assistant.session_log = lambda *args, **kwargs: None

        await assistant.handle_routed_text(text, session_id, channel=channel)
        return calls

    async def test_attention_suppressed_turn_cannot_resolve_pending_confirmation(
        self,
    ) -> None:
        calls = await self._route_with_pending_confirmation(
            "The delivery truck is outside.",
            disposition="suppress",
        )

        self.assertEqual(calls["attention"], 1)
        self.assertEqual(calls["confirmation"], [])
        self.assertEqual(calls["core"], 0)

    async def test_attention_admitted_reply_resolves_pending_confirmation(
        self,
    ) -> None:
        calls = await self._route_with_pending_confirmation(
            "Yes, go ahead.",
            disposition="admit",
        )

        self.assertEqual(calls["attention"], 1)
        self.assertEqual(len(calls["confirmation"]), 1)
        envelope = calls["confirmation"][0]["envelope"]
        self.assertEqual(envelope.admission, "admit")
        self.assertEqual(
            envelope.attention.source,
            "cognitive_gateway.attention_review_model",
        )
        self.assertEqual(calls["core"], 0)


if __name__ == "__main__":
    unittest.main()
