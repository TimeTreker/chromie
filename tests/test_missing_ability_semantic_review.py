from __future__ import annotations

import unittest

from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    _payload_message_texts,
)
from agent.app.cognitive_core.goal_interpreter.schema import (
    RouteRequest,
    annotate_pipeline_stage_outputs,
)


class MissingAbilityPrimaryInterpretationTests(unittest.IsolatedAsyncioTestCase):
    """Missing abilities are primary semantic output, not a repair workflow."""

    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

    def test_primary_prompt_uses_mind_and_missing_ability_contract(self) -> None:
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

        payload = self._interpreter().build_payload(request)
        system_text, user_text, _ = _payload_message_texts(payload)

        self.assertIn("fast Goal Interpretation model", system_text)
        self.assertIn("Missing abilities may appear only as non-executable metadata", system_text)
        self.assertIn("Responsibility evidence for Goal Association", system_text)
        self.assertIn("chromie_default_mind", user_text)
        self.assertIn("owner-approved mind profile", user_text)
        self.assertIn("child/family first-person speech", user_text)
        self.assertIn("chromie.weather.lookup", user_text)

    async def test_primary_missing_ability_is_terminal_after_one_model_call(self) -> None:
        class MissingAbilityInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                self.stages.append(stage)
                return {
                    "message": {
                        "content": (
                            '{"route":"clarify",'
                            '"intent":"missing_or_unsupported_ability",'
                            '"confidence":0.96,"fast_speech":'
                            '"我知道你想找附近好吃的地方，不过这个我现在还不会查。",'
                            '"progress":[],"metadata":{"desired_abilities":[{'
                            '"ability_id":"local.restaurant_recommendation",'
                            '"intent":"推荐用户附近的餐厅",'
                            '"status":"missing_ability","confidence":0.96,'
                            '"reason":"当前能力目录没有本地商家搜索能力。"}]}}'
                        )
                    }
                }

        interpreter = MissingAbilityInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="帮我推荐附近好吃的地方。",
                language="zh-CN",
                context={
                    "gateway_admission_complete": True,
                    "prompt_capabilities_common": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "interaction_executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(interpreter.stages, ["quick_intent"])
        self.assertEqual(decision.route, "clarify")
        self.assertEqual(
            decision.metadata["desired_abilities"][0]["ability_id"],
            "local.restaurant_recommendation",
        )
        transaction = decision.metadata["goal_interpreter_transaction"]
        self.assertEqual(transaction["logical_invocation_count"], 1)
        self.assertFalse(transaction["semantic_repair_attempted"])

        annotated = annotate_pipeline_stage_outputs(decision)
        ability_proposals = [
            item
            for item in annotated.metadata["task_proposals"]
            if item.get("proposal_kind") == "ability"
        ]
        self.assertEqual(len(ability_proposals), 1)
        self.assertEqual(ability_proposals[0]["state"], "missing_ability")
        self.assertFalse(ability_proposals[0]["effectful"])


if __name__ == "__main__":
    unittest.main()
