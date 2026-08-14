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
    def request(self, text: str, *, active: bool = False) -> AttentionReviewRequest:
        return AttentionReviewRequest(
            turn_id="turn-1",
            session_id="turn-1",
            context_digest="1" * 64,
            text=text,
            language="en-US",
            engagement={
                "gate_enabled": True,
                "active": active,
                "evidence": "active_task" if active else "none",
            },
        )

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
        self.assertEqual(
            result.source,
            "cognitive_gateway.attention_review_model_confirmed",
        )
        self.assertEqual(client.calls, 2)

    async def test_false_question_suppression_is_reconsidered_by_model(self) -> None:
        client = _Client(
            results=[
                {
                    "addressed": False,
                    "speech_act": "reply",
                    "confidence": 0.98,
                },
                {
                    "addressed": True,
                    "speech_act": "question",
                    "confidence": 0.99,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("Is it hot today?"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "question")
        self.assertEqual(
            result.source,
            "cognitive_gateway.attention_review_model_reconsidered",
        )
        self.assertEqual(client.calls, 2)

    async def test_inconsistent_unaddressed_unclear_output_is_repaired(self) -> None:
        client = _Client(
            results=[
                {
                    "addressed": False,
                    "speech_act": "unclear",
                    "confidence": 0.90,
                },
                {
                    "addressed": False,
                    "speech_act": "ambient_report",
                    "confidence": 0.94,
                },
                {
                    "addressed": False,
                    "speech_act": "ambient_report",
                    "confidence": 0.93,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(
            self.request("The deployment pipeline completed before lunch.")
        )

        self.assertEqual(result.disposition, "suppress")
        self.assertEqual(result.speech_act, "ambient_report")
        self.assertEqual(
            result.source,
            "cognitive_gateway.attention_review_model_confirmed",
        )
        self.assertEqual(client.calls, 3)

    async def test_false_dictation_suppression_is_reconsidered_by_model(self) -> None:
        client = _Client(
            results=[
                {
                    "addressed": False,
                    "speech_act": "dictation",
                    "confidence": 0.95,
                },
                {
                    "addressed": True,
                    "speech_act": "imperative",
                    "confidence": 0.99,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(
            self.request("Open the door, wave twice, then come back.")
        )

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "imperative")
        self.assertEqual(
            result.source,
            "cognitive_gateway.attention_review_model_reconsidered",
        )
        self.assertIn("suppression review admitted", result.reason)
        self.assertEqual(client.calls, 2)

    async def test_invalid_suppression_reconsideration_fails_open(self) -> None:
        client = _Client(
            results=[
                {
                    "addressed": False,
                    "speech_act": "dictation",
                    "confidence": 0.95,
                },
                {
                    "addressed": False,
                    "speech_act": "imperative",
                    "confidence": 0.99,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(
            self.request("Open the door, wave twice, then come back.")
        )

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "unclear")
        self.assertEqual(
            result.source,
            "cognitive_gateway.attention_review_fail_open",
        )
        self.assertIn("suppression review failed open", result.reason)
        self.assertEqual(client.calls, 2)

    async def test_failed_semantic_repair_still_admits_uncertain_input(self) -> None:
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
                    "confidence": 0.91,
                },
            ]
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("Maybe this is for Chromie"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "unclear")
        self.assertIn("failed open", result.reason)
        self.assertEqual(client.calls, 2)

    async def test_active_exchange_bypasses_model_and_is_admitted(self) -> None:
        client = _Client(error=AssertionError("model must not run"))
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("Yes.", active=True))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(client.calls, 0)

    async def test_model_failure_is_fail_open(self) -> None:
        reviewer = AttentionReviewer(_Client(error=TimeoutError("slow")))

        result = await reviewer.review(self.request("Maybe this is for Chromie"))

        self.assertEqual(result.disposition, "admit")
        self.assertEqual(result.speech_act, "unclear")
        self.assertIn("failed open", result.reason)

    def test_attention_prompt_preserves_pro_drop_commands_as_addressed(self) -> None:
        prompt = AttentionReviewer._system_prompt()
        suppression_prompt = AttentionReviewer._suppression_review_prompt(
            self.request("A subject-omitted command."),
            initial_output={
                "addressed": False,
                "speech_act": "ambient_report",
                "confidence": 0.95,
            },
        )
        self.assertIn("pro-drop languages", prompt)
        self.assertIn("third-person beneficiary or recipient", prompt)
        self.assertIn("pro-drop language", suppression_prompt)


if __name__ == "__main__":
    unittest.main()
