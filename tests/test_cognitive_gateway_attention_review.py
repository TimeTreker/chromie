from __future__ import annotations

import unittest
from typing import Any

from agent.app.cognitive_gateway.attention_review import AttentionReviewer
from shared.chromie_contracts.user_turn import AttentionReviewRequest


class _Client:
    def __init__(self, result: Any = None, *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.calls += 1
        if self.error is not None:
            raise self.error
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
        self.assertEqual(client.calls, 1)

    async def test_direct_question_fails_open_even_if_model_says_unaddressed(self) -> None:
        client = _Client(
            {
                "addressed": False,
                "speech_act": "reply",
                "confidence": 0.98,
            }
        )
        reviewer = AttentionReviewer(client)

        result = await reviewer.review(self.request("Is it hot today?"))

        self.assertEqual(result.disposition, "admit")
        self.assertIn("direct_question_form", result.reason)

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


if __name__ == "__main__":
    unittest.main()
