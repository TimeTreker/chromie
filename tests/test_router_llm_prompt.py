from __future__ import annotations

import unittest

from router.app.llm_router import OllamaLLMRouter
from router.app.schema import RouteRequest


class RouterLlmPromptTests(unittest.TestCase):
    def test_system_prompt_names_router_role_and_context_boundaries(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        prompt = router.load_system_prompt()

        self.assertIn("robot-brain router", prompt)
        self.assertIn("Quick response lane", prompt)
        self.assertIn("Deep reasoning lane", prompt)
        self.assertIn("Route taxonomy", prompt)
        self.assertIn("candidate_capabilities", prompt)
        self.assertIn("available abilities", prompt)
        self.assertIn("Memory and context are hints, not authorization", prompt)
        self.assertIn("voice and/or", prompt)
        self.assertIn("body action", prompt)
        self.assertIn("creative speech-only requests as chat", prompt)
        self.assertIn("go ahead", prompt)
        self.assertIn("not physical movement", prompt)

    def test_user_prompt_includes_abilities_and_bounded_context(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="s1",
            text="continue walking there",
            language="en-US",
            context={
                "candidate_capabilities": [
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "interaction_executable": True,
                    }
                ],
                "robot_state": {"position": {"x": 1.0, "y": 2.0}},
                "memory": {"last_task": "walk"},
            },
        )

        prompt = router.build_user_prompt(request)

        self.assertIn("robot-brain router", prompt)
        self.assertIn("Routing lanes", prompt)
        self.assertIn("quick deterministic controls", prompt)
        self.assertIn("deep reasoning lane", prompt)
        self.assertIn("before non-urgent semantic fallback", prompt)
        self.assertIn("Available abilities / candidate capabilities JSON", prompt)
        self.assertIn("Bounded memory and world context JSON", prompt)
        self.assertIn("soridormi.walk_velocity", prompt)
        self.assertIn("robot_state", prompt)
        self.assertIn("position", prompt)
        self.assertIn("last_task", prompt)
        self.assertIn("never as authorization", prompt)
        self.assertIn("creative speech-only requests", prompt)
        self.assertIn("'go ahead'", prompt)


if __name__ == "__main__":
    unittest.main()
