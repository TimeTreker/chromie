from __future__ import annotations

import unittest

from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    SemanticRouteRepairOutput,
    _payload_message_texts,
    _validate_missing_ability_output_against_catalog,
)
from agent.app.cognitive_core.goal_interpreter.schema import (
    RouteDecision,
    RouteRequest,
)


class MissingAbilitySemanticReviewTests(unittest.TestCase):
    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            review_model="review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

    def test_semantic_repair_uses_mind_and_child_warmth_contract(self) -> None:
        request = RouteRequest(
            sid="restaurant-tone",
            text="你能帮我看看龙兴天街附近有什么好吃的吗？",
            language="zh-CN",
            context={
                "mind": {
                    "profile_id": "chromie_default_mind",
                    "self_model": {
                        "speaker_entity": {
                            "name": "Chromie",
                            "age_description": "six-year-old child",
                        }
                    },
                    "prompt_summary": "warm, natural, and family-like",
                },
                "prompt_capabilities_common": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "description": "Look up current weather for a location.",
                        "route": "tool",
                        "interaction_executable": True,
                    }
                ],
            },
        )
        payload = self._interpreter().build_semantic_route_repair_payload(
            request,
            RouteDecision(
                route="chat",
                intent="recommendation_request",
                confidence=0.95,
            ),
            reason="generic_chat_capability_review",
        )

        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn("Global Context Group", system_text)
        self.assertIn("six-year-old child", system_text)
        self.assertIn("warm, natural, and family-like", system_text)
        self.assertIn("A bare location", system_text)
        self.assertIn("must not equal or reuse any capability_id", system_text)
        self.assertIn("must not ask a follow-up question", system_text)
        self.assertIn("我现在还没学会这个呢", system_text)
        self.assertIn("我无法直接查询", system_text)
        self.assertIn("must not claim that learning has started", system_text)

    def test_missing_ability_id_cannot_reuse_available_weather_capability(self) -> None:
        request = RouteRequest(
            sid="restaurant-grounding",
            text="帮我推荐附近好吃的地方。",
            language="zh-CN",
            context={
                "prompt_capabilities_common": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "description": "Look up current weather for a location.",
                        "route": "tool",
                        "interaction_executable": True,
                    }
                ]
            },
        )
        output = SemanticRouteRepairOutput.model_validate(
            {
                "route": "clarify",
                "intent": "missing_or_unsupported_ability",
                "confidence": 1.0,
                "speak_first": "这个我还没学会呢，希望以后能学会再帮你。",
                "metadata": {
                    "desired_abilities": [
                        {
                            "ability_id": "chromie.weather.lookup",
                            "intent": "推荐用户附近好吃的餐厅",
                            "status": "missing_ability",
                            "confidence": 1.0,
                            "reason": "当前没有餐厅或本地商家搜索能力。",
                        }
                    ]
                },
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "not reuse an available capability_id",
        ):
            _validate_missing_ability_output_against_catalog(output, request)

        assert output.metadata is not None
        valid = output.model_copy(
            update={
                "metadata": output.metadata.model_copy(
                    update={
                        "desired_abilities": [
                            output.metadata.desired_abilities[0].model_copy(
                                update={
                                    "ability_id": "local.restaurant_recommendation"
                                }
                            )
                        ]
                    }
                )
            }
        )
        _validate_missing_ability_output_against_catalog(valid, request)


if __name__ == "__main__":
    unittest.main()
