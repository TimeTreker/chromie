from __future__ import annotations

import unittest
from typing import Any

from agent.app.response_composer import ResponseComposerResolver
from agent.app.schema import AgentRunRequest
from shared.chromie_contracts.plan import CanonicalPlan


class _SequenceOllama:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((prompt, kwargs))
        if not self.replies:
            raise AssertionError("unexpected Response Composer model call")
        return self.replies.pop(0)


def _respond_plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan_explicit_social_attention",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=0.95,
        goal_ids=["goal_greeting"],
        goal_summary="Acknowledge the greeting.",
        response_text="Hello!",
    )


def _response_output() -> dict[str, Any]:
    return {
        "response_plan": {
            "immediate": None,
            "pre_action": None,
            "progress": [],
            "final": {
                "text": "Hello!",
                "speech_act": "greet",
                "commitment_state": "completed",
                "must_not_claim_completion": False,
                "covers_task_ids": [],
                "covers_goal_ids": ["goal_greeting"],
                "claims": [],
                "metadata": {},
            },
        },
        "lane_coordination": [],
        "confidence": 0.95,
        "rationale": "A brief greeting is enough.",
    }


def _request() -> AgentRunRequest:
    request = AgentRunRequest.model_validate(
        {
            "sid": "response-composer-social-attention",
            "text": "Hello.",
            "language": "en-US",
            "route_decision": {
                "route": "chat",
                "intent": "greeting",
                "agents": [],
                "confidence": 0.99,
                "source": "llm",
            },
        }
    )
    request.context.update(
        {
            "canonical_plan_resolution": _respond_plan(),
            # These fields may exist elsewhere in one turn, but Response Composer
            # must not gain Social Attention semantic authority from them.
            "social_attention_policy": {"mode": "on"},
            "social_attention_candidates": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        }
    )
    return request


class ResponseComposerSocialAttentionContractTests(unittest.IsolatedAsyncioTestCase):
    def test_response_schema_has_no_social_attention_authoring_surface(self) -> None:
        schema = ResponseComposerResolver._response_schema(
            _respond_plan(),
            _request().context,
        )

        self.assertNotIn("social_attention_plan", schema.get("properties", {}))
        self.assertNotIn("SocialAttentionPlan", schema.get("$defs", {}))
        self.assertNotIn("SocialAttentionBehavior", schema.get("$defs", {}))

    def test_response_prompt_does_not_receive_social_attention_candidates(self) -> None:
        resolver = ResponseComposerResolver(_SequenceOllama([]))  # type: ignore[arg-type]
        request = _request()
        prompt = resolver._prompt(request, _respond_plan())

        self.assertIn("Social Attention is owned by its independent background cognition", prompt)
        self.assertNotIn("soridormi.blink_eyes", prompt)
        self.assertNotIn("Social-attention candidates JSON", prompt)

    async def test_legacy_social_field_is_only_a_dto_error_then_regenerated_once(self) -> None:
        legacy = _response_output()
        legacy["social_attention_plan"] = {
            "decision": "express",
            "behaviors": [{"capability_id": "soridormi.blink_eyes"}],
        }
        ollama = _SequenceOllama([legacy, _response_output()])

        resolution = await ResponseComposerResolver(ollama).resolve(_request())  # type: ignore[arg-type]

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(len(ollama.calls), 2)
        self.assertEqual(
            [call[1]["prompt_family"] for call in ollama.calls],
            ["response_composer.primary", "response_composer.dto_regeneration"],
        )
        assert resolution.composition is not None
        self.assertNotIn(
            "social_attention_plan",
            resolution.composition.model_dump(mode="json", exclude_none=True),
        )

    async def test_valid_response_is_complete_without_any_social_attention_decision(self) -> None:
        ollama = _SequenceOllama([_response_output()])

        resolution = await ResponseComposerResolver(ollama).resolve(_request())  # type: ignore[arg-type]

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(len(ollama.calls), 1)
        assert resolution.composition is not None
        self.assertNotIn(
            "social_attention_plan",
            resolution.composition.model_dump(mode="json", exclude_none=True),
        )


if __name__ == "__main__":
    unittest.main()
