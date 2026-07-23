from __future__ import annotations

import asyncio
import unittest
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.schemas.route import RouteDecision


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
    async def test_post_interrupt_correction_carries_admitted_envelope_to_apply_core(
        self,
    ) -> None:
        session_id = "turn-post-interrupt"
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.enable_router = True
        assistant.enable_agent = True
        assistant.cognitive_runtime_mode = "apply"
        assistant.conversation_state = _ConversationState(
            "conversation-post-interrupt"
        )
        assistant.sessions = _Sessions(session_id)
        assistant.active_llm_task = None
        apply_calls: list[dict[str, Any]] = []

        routed_interrupt = RouteDecision(
            route="interrupt",
            agents=[],
            intent="stop_current_output",
            confidence=0.88,
            source="llm",
            language="en-US",
            interrupt_current=True,
            needs_agent=False,
            metadata={
                "post_interrupt_review": {"status": "corrected"},
                "post_interrupt_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "explain_stop_word",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                    "needs_agent": True,
                },
            },
        )

        class _Router:
            async def route(self, *args: Any, **kwargs: Any) -> RouteDecision:
                del args, kwargs
                return routed_interrupt

        async def get_http_session(self: VoiceAssistant) -> object:
            return object()

        async def confirmation_reply(
            self: VoiceAssistant,
            user_text: str,
            sid: str,
            **kwargs: Any,
        ) -> bool:
            del self, user_text, sid, kwargs
            return False

        async def interrupt(
            self: VoiceAssistant,
            new_session_id: str | None = None,
        ) -> None:
            del self
            self_interruption_ids.append(new_session_id)

        async def try_apply(
            self: VoiceAssistant,
            session: object,
            **kwargs: Any,
        ) -> tuple[bool, RouteDecision]:
            del self, session
            apply_calls.append(dict(kwargs))
            decision = kwargs["decision"]
            return decision.route != "interrupt", decision

        def build_context(
            self: VoiceAssistant,
            sid: str,
        ) -> dict[str, Any]:
            del self
            return {
                "conversation_id": "conversation-post-interrupt",
                "history": [],
                "sid": sid,
            }

        def conditional_policy(
            self: VoiceAssistant,
            decision: RouteDecision,
            **kwargs: Any,
        ) -> RouteDecision:
            del self, kwargs
            return decision

        self_interruption_ids: list[str | None] = []
        assistant.router_client = _Router()
        assistant.get_http_session = MethodType(get_http_session, assistant)
        assistant._handle_confirmation_reply = MethodType(
            confirmation_reply,
            assistant,
        )
        assistant.interrupt = MethodType(interrupt, assistant)
        assistant._try_apply_cognitive_runtime = MethodType(
            try_apply,
            assistant,
        )
        assistant.build_context = MethodType(build_context, assistant)
        assistant._apply_conditional_deepthinking_policy = MethodType(
            conditional_policy,
            assistant,
        )
        assistant.session_log = lambda *args, **kwargs: None

        await assistant.handle_routed_text(
            "Please explain the word stop.",
            session_id,
            channel="text",
        )
        self.assertIsNotNone(assistant.active_llm_task)
        assert assistant.active_llm_task is not None
        await assistant.active_llm_task

        self.assertEqual(self_interruption_ids, [session_id])
        self.assertEqual(
            [call["decision"].route for call in apply_calls],
            ["interrupt", "chat"],
        )
        admitted = apply_calls[0]["turn_envelope"]
        corrected = apply_calls[1].get("turn_envelope")
        self.assertIsNotNone(corrected)
        self.assertEqual(corrected, admitted)
        self.assertEqual(corrected.admission, "admit")
        self.assertEqual(corrected.turn_id, session_id)
        self.assertEqual(
            corrected.original_input.text,
            "Please explain the word stop.",
        )

    async def test_deterministic_ignore_stays_suppressed_without_router_result(
        self,
    ) -> None:
        for router_mode in ("disabled", "raises"):
            with self.subTest(router_mode=router_mode):
                session_id = f"turn-ignore-{router_mode}"
                assistant = VoiceAssistant.__new__(VoiceAssistant)
                assistant.enable_router = router_mode != "disabled"
                assistant.cognitive_runtime_mode = "apply"
                assistant.conversation_state = _ConversationState(
                    "conversation-ignore"
                )
                assistant.sessions = _Sessions(session_id)
                assistant.active_llm_task = None
                model_calls: list[str] = []
                done_calls: list[str] = []

                class _Router:
                    async def route(
                        self,
                        *args: Any,
                        **kwargs: Any,
                    ) -> RouteDecision:
                        del self, args, kwargs
                        raise RuntimeError("router unavailable")

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

                assistant.router_client = _Router()
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
                assistant._router_exception_safe_response = (
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
