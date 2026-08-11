from __future__ import annotations

import unittest
from typing import Any

from agent.app.response_composer import ResponseComposerResolver
from agent.app.schema import AgentRunRequest
from shared.chromie_contracts.plan import CanonicalPlan


class _SequenceOllama:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.schemas: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        del prompt
        self.schemas.append(kwargs["response_format"])
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


def _response_output(*, include_social: bool) -> dict[str, Any]:
    output: dict[str, Any] = {
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
        "confidence": 0.95,
        "rationale": "A brief greeting is enough.",
    }
    if include_social:
        output["social_attention_plan"] = {
            "purpose": "acknowledge",
            "decision": "none",
            "reason": "Stillness is natural for this turn.",
        }
    return output


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
            "social_attention_policy": {
                "mode": "on",
                "planning_enabled": True,
                "execution_enabled": True,
                "embodiment_independent": True,
            },
            "social_attention_candidates": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "available": True,
                    "interaction_executable": True,
                }
            ],
            "social_attention_target_evidence": {"available": False},
        }
    )
    return request


def _allows_null(schema: Any) -> bool:
    if isinstance(schema, dict):
        if schema.get("type") == "null":
            return True
        return any(_allows_null(value) for value in schema.values())
    if isinstance(schema, list):
        return any(_allows_null(value) for value in schema)
    return False


class ResponseComposerSocialAttentionContractTests(
    unittest.IsolatedAsyncioTestCase
):
    def test_schema_requires_explicit_decision_when_candidates_exist(self) -> None:
        request = _request()
        schema = ResponseComposerResolver._response_schema(
            _respond_plan(),
            request.context,
        )

        self.assertIn("social_attention_plan", schema["required"])
        self.assertFalse(
            _allows_null(schema["properties"]["social_attention_plan"])
        )
        self.assertIn(
            "decision",
            schema["$defs"]["SocialAttentionPlan"]["required"],
        )
        self.assertEqual(
            schema["$defs"]["SocialAttentionBehavior"]["properties"]["capability_id"]["enum"],
            ["soridormi.blink_eyes"],
        )

    def test_schema_keeps_explicit_null_for_policy_off(self) -> None:
        schema = ResponseComposerResolver._response_schema(
            _respond_plan(),
            {
                "social_attention_policy": {"mode": "off"},
                "social_attention_candidates": [],
            },
        )

        self.assertNotIn(
            "social_attention_plan",
            schema.get("required", []),
        )
        self.assertTrue(
            _allows_null(schema["properties"]["social_attention_plan"])
        )
        self.assertNotIn(
            "decision",
            schema["$defs"]["SocialAttentionPlan"].get("required", []),
        )

    async def test_missing_decision_repairs_to_explicit_none(self) -> None:
        ollama = _SequenceOllama(
            [
                _response_output(include_social=False),
                _response_output(include_social=True),
            ]
        )
        resolution = await ResponseComposerResolver(  # type: ignore[arg-type]
            ollama
        ).resolve(_request())

        self.assertEqual(resolution.status, "resolved")
        self.assertIsNotNone(resolution.composition)
        composition = resolution.composition
        assert composition is not None
        self.assertIsNotNone(composition.social_attention_plan)
        assert composition.social_attention_plan is not None
        self.assertEqual(
            composition.social_attention_plan.decision,
            "none",
        )
        self.assertTrue(
            composition.metadata["social_attention_decision_required"]
        )
        self.assertEqual(
            composition.metadata["social_attention_candidate_count"],
            1,
        )
        self.assertEqual(
            composition.metadata["social_attention_model_decision"],
            "none",
        )
        self.assertEqual(len(ollama.schemas), 2)
        self.assertTrue(
            resolution.metadata["contract_repair_attempted"]
        )

    async def test_none_decision_discards_contradictory_optional_expression(self) -> None:
        output = _response_output(include_social=True)
        output["social_attention_plan"].update(  # type: ignore[index,union-attr]
            {
                "behaviors": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "coordination_id": "attention-blink",
                        "reason": "Optional acknowledgement.",
                    }
                ],
                "speech_expression": {"mode": "adapt", "style": "warm"},
            }
        )
        ollama = _SequenceOllama([output])

        resolution = await ResponseComposerResolver(  # type: ignore[arg-type]
            ollama
        ).resolve(_request())

        self.assertEqual(resolution.status, "resolved")
        assert resolution.composition is not None
        attention = resolution.composition.social_attention_plan
        assert attention is not None
        self.assertEqual(attention.decision, "none")
        self.assertEqual(attention.behaviors, [])
        self.assertEqual(attention.speech_expression.mode, "none")
        self.assertTrue(
            attention.metadata["canonicalized_conflicting_none_expression"]
        )
        self.assertFalse(resolution.metadata["contract_repair_attempted"])

    async def test_omitted_decision_with_behavior_requires_model_repair(self) -> None:
        incomplete = _response_output(include_social=True)
        social = incomplete["social_attention_plan"]
        assert isinstance(social, dict)
        social.pop("decision")
        social["behaviors"] = [
            {
                "capability_id": "soridormi.blink_eyes",
                "coordination_id": "attention-blink",
                "reason": "Optional acknowledgement.",
            }
        ]
        ollama = _SequenceOllama(
            [incomplete, _response_output(include_social=True)]
        )

        resolution = await ResponseComposerResolver(  # type: ignore[arg-type]
            ollama
        ).resolve(_request())

        self.assertEqual(resolution.status, "resolved")
        assert resolution.composition is not None
        attention = resolution.composition.social_attention_plan
        assert attention is not None
        self.assertEqual(attention.decision, "none")
        self.assertEqual(len(ollama.schemas), 2)
        self.assertTrue(resolution.metadata["contract_repair_attempted"])


if __name__ == "__main__":
    unittest.main()
