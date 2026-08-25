from __future__ import annotations

import unittest
from typing import Any

from agent.app.cognitive_gateway.attention_review import AttentionReviewer
from shared.chromie_contracts.user_turn import AttentionReviewRequest


class _Client:
    def __init__(
        self,
        result: Any = None,
        *,
        results: list[Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.results = list(results or [])
        self.error = error
        self.calls = 0

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return self.result


class CognitiveGatewayAttentionReviewTests(unittest.IsolatedAsyncioTestCase):
    def request(
        self,
        text: str,
        *,
        channel: str = "voice",
        active: bool = False,
        evidence: str | None = None,
        recent_dialogue: list[dict[str, str]] | None = None,
        gate_enabled: bool = True,
    ) -> AttentionReviewRequest:
        return AttentionReviewRequest(
            turn_id="turn-1",
            session_id="turn-1",
            context_digest="1" * 64,
            channel=channel,
            text=text,
            language="en-US",
            engagement={
                "gate_enabled": gate_enabled,
                "active": active,
                "evidence": evidence or ("active_task" if active else "none"),
            },
            recent_dialogue=list(recent_dialogue or []),
        )

    async def test_explicit_text_transport_admits_without_room_speech_review(self) -> None:
        client = _Client(
            {"addressed": False, "speech_act": "narration", "confidence": 0.99}
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(
            self.request("我有点累。", channel="text")
        )

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.source, "cognitive_gateway.explicit_text_transport")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(client.calls, 0)


    async def test_disabled_gate_admits_without_fabricating_review_confidence(self) -> None:
        client = _Client({"addressed": True, "speech_act": "greeting", "confidence": 1.0})
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("Hi.", gate_enabled=False))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "unclear")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.source, "cognitive_gateway.attention_policy_disabled")
        self.assertIn("not reviewed", result.reason)
        self.assertEqual(client.calls, 0)

    async def test_inactive_ambient_narration_can_be_suppressed(self) -> None:
        client = _Client(
            {
                "addressed": False,
                "speech_act": "narration",
                "confidence": 0.96,
            }
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(
            self.request("She said the model runs locally.")
        )

        self.assertEqual(result.disposition, "suppress")
        self.assertEqual(result.speech_act, "narration")
        self.assertEqual(result.turn_id, "turn-1")
        self.assertEqual(result.session_id, "turn-1")
        self.assertEqual(result.context_digest, "1" * 64)
        self.assertEqual(result.source, "cognitive_gateway.attention_review_model")
        self.assertEqual(client.calls, 1)

    async def test_direct_question_is_admitted_in_one_model_call(self) -> None:
        client = _Client(
            {
                "addressed": True,
                "speech_act": "question",
                "confidence": 0.99,
            }
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("Is it hot today?"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "question")
        self.assertEqual(result.source, "cognitive_gateway.attention_review_model")
        self.assertEqual(client.calls, 1)

    async def test_direct_greeting_is_admitted_and_preserves_speech_act(self) -> None:
        client = _Client(
            {
                "addressed": True,
                "speech_act": "greeting",
                "confidence": 0.99,
            }
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("Hi, Chromie!"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "greeting")
        self.assertEqual(result.confidence, 0.99)
        self.assertEqual(result.source, "cognitive_gateway.attention_review_model")
        self.assertEqual(client.calls, 1)

    async def test_bare_chinese_greeting_primary_false_negative_is_repaired(self) -> None:
        client = _Client(
            results=[
                {
                    "addressed": False,
                    "speech_act": "reply",
                    "confidence": 0.98,
                },
                {
                    "addressed": True,
                    "speech_act": "greeting",
                    "confidence": 0.99,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("你好。"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "greeting")
        self.assertEqual(result.source, "cognitive_gateway.attention_review_model_repair")
        self.assertEqual(client.calls, 2)

    async def test_bare_chinese_greeting_fails_open_if_repair_remains_wrong(self) -> None:
        wrong = {
            "addressed": False,
            "speech_act": "ambient_report",
            "confidence": 0.98,
        }
        client = _Client(results=[wrong, wrong])
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("你好。"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "greeting")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.source, "cognitive_gateway.attention_review_fail_open")
        self.assertIn("surface_direct_address:bare_greeting", result.reason)
        self.assertEqual(client.calls, 2)

    async def test_question_form_false_ambient_label_is_repaired(self) -> None:
        client = _Client(
            results=[
                {
                    "addressed": False,
                    "speech_act": "ambient_report",
                    "confidence": 0.97,
                },
                {
                    "addressed": True,
                    "speech_act": "question",
                    "confidence": 0.99,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("今天热吗？"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "question")
        self.assertEqual(result.source, "cognitive_gateway.attention_review_model_repair")
        self.assertEqual(client.calls, 2)

    async def test_high_confidence_unaddressed_unclear_fragment_repairs_then_fails_open(
        self,
    ) -> None:
        client = _Client(
            results=[
                {
                    "addressed": False,
                    "speech_act": "unclear",
                    "confidence": 0.90,
                },
                {
                    "addressed": False,
                    "speech_act": "unclear",
                    "confidence": 0.93,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("The."))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "unclear")
        self.assertEqual(result.source, "cognitive_gateway.attention_review_fail_open")
        self.assertIn("after one repair", result.reason)
        self.assertEqual(client.calls, 2)

    async def test_recent_exchange_with_temporary_address_rule_is_reviewed_once(self) -> None:
        client = _Client(
            {
                "addressed": False,
                "speech_act": "ambient_report",
                "confidence": 0.98,
            }
        )
        reviewer = AttentionReviewer(client)
        request = self.request(
            "The budget slide needs one more number.",
            active=True,
            evidence="recent_exchange",
            recent_dialogue=[
                {
                    "role": "user",
                    "text": "I'm starting a video call. Please wait until I say Chromie before responding.",
                },
                {"role": "assistant", "text": "Okay."},
            ],
        )

        result = await reviewer.review(request)

        self.assertEqual(result.disposition, "suppress")
        self.assertEqual(client.calls, 1)
        prompt = client.result  # keep fake result untouched; inspect generated prompt below
        del prompt

    async def test_active_task_is_context_not_automatic_semantic_admission(self) -> None:
        client = _Client(
            {
                "addressed": False,
                "speech_act": "narration",
                "confidence": 0.97,
            }
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(
            self.request(
                "She said the meeting moved to three.",
                active=True,
                evidence="active_task",
            )
        )

        self.assertEqual(result.disposition, "suppress")
        self.assertEqual(client.calls, 1)

    async def test_active_exchange_reply_cannot_be_marked_unaddressed(self) -> None:
        client = _Client(
            {
                "addressed": False,
                "speech_act": "reply",
                "confidence": 0.9,
            }
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(
            self.request(
                "Continue the previous thing.",
                active=True,
                evidence="active_task",
                recent_dialogue=[
                    {"role": "assistant", "text": "I will walk forward."}
                ],
            )
        )

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.source, "cognitive_gateway.attention_review_fail_open")
        self.assertEqual(client.calls, 2)

    async def test_model_failure_is_fail_open(self) -> None:
        reviewer = AttentionReviewer(_Client(error=TimeoutError("slow")))

        result = await reviewer.review(self.request("Maybe this is for Chromie"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "unclear")
        self.assertIn("failed open", result.reason)

    def test_attention_prompt_preserves_pro_drop_and_temporary_rules(self) -> None:
        prompt = AttentionReviewer._system_prompt()
        request = self.request(
            "The budget slide needs one more number.",
            active=True,
            evidence="recent_exchange",
            recent_dialogue=[
                {
                    "role": "user",
                    "text": "Please wait until I say Chromie before responding.",
                }
            ],
        )
        user_prompt = AttentionReviewer._prompt(request)
        self.assertIn("pro-drop languages", prompt)
        self.assertIn("'你好'", prompt)
        self.assertIn("third-person beneficiary or recipient", prompt)
        self.assertIn("temporary interaction rule", prompt)
        self.assertIn("continue, resume, change, stop, or cancel", prompt)
        self.assertIn("Please wait until I say Chromie", user_prompt)

    def test_decoder_schema_requires_directed_speech_to_be_addressed(self) -> None:
        schema = AttentionReviewer._response_schema()
        directed_rule = schema["allOf"][0]

        self.assertEqual(
            set(directed_rule["if"]["properties"]["speech_act"]["enum"]),
            {"question", "request", "imperative", "greeting"},
        )
        self.assertTrue(
            directed_rule["then"]["properties"]["addressed"]["const"]
        )

        active_schema = AttentionReviewer._response_schema(active_engagement=True)
        self.assertIn(
            "reply",
            active_schema["allOf"][0]["if"]["properties"]["speech_act"]["enum"],
        )



if __name__ == "__main__":
    unittest.main()
