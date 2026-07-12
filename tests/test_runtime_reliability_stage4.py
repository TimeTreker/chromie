from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.schemas.route import RouteDecision


class RuntimeReliabilityStage4Tests(unittest.TestCase):
    def test_agent_disconnect_on_robot_action_fails_closed_without_promising_execution(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        decision = RouteDecision(
            route="robot_action",
            intent="compound_common_catalog_task",
            confidence=0.95,
            actions=[
                {
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                }
            ],
            metadata={},
        )

        response = assistant._agent_exception_safe_response(
            decision,
            user_text="你点点头再眨两下眼睛。",
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.skills, [])
        spoken = " ".join(item.text for item in response.speech)
        self.assertIn("没有执行", spoken)
        self.assertNotIn("我会点头", spoken)
        self.assertNotIn("正在执行", spoken)

    def test_agent_disconnect_on_tool_route_refuses_to_invent_result(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        decision = RouteDecision(
            route="tool",
            intent="weather_query",
            confidence=0.95,
            metadata={"tool_name": "weather"},
        )

        response = assistant._agent_exception_safe_response(
            decision,
            user_text="北京天气怎么样？",
        )

        self.assertIsNotNone(response)
        assert response is not None
        spoken = " ".join(item.text for item in response.speech)
        self.assertIn("没有返回未经验证的结果", spoken)
        self.assertEqual(response.skills, [])

    def test_warmup_uses_a_one_token_non_thinking_generation(self) -> None:
        source = Path("scripts/warm_ollama.sh").read_text(encoding="utf-8")

        self.assertIn('NUM_PREDICT="${OLLAMA_WARM_NUM_PREDICT:-1}"', source)
        self.assertIn('"think": False', source)


if __name__ == "__main__":
    unittest.main()
