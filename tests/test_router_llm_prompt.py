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
        self.assertIn("Emergency filter", prompt)
        self.assertIn("Quick intent router", prompt)
        self.assertIn("Route taxonomy", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("candidate_capabilities", prompt)
        self.assertIn("available abilities", prompt)
        self.assertIn("Memory and context are hints, not authorization", prompt)
        self.assertIn("voice and/or", prompt)
        self.assertIn("body action", prompt)
        self.assertIn("creative speech-only requests as chat", prompt)
        self.assertIn("go ahead", prompt)
        self.assertIn("not physical movement", prompt)
        self.assertIn("you look beautiful", prompt)
        self.assertIn("appearance statements", prompt)
        self.assertIn("deepthinking_agent", prompt)
        self.assertIn("body commands", prompt)
        self.assertIn("robot_action", prompt)

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
        self.assertIn("Routing stages", prompt)
        self.assertIn("emergency filter", prompt)
        self.assertIn("quick intent-and-meaning router", prompt)
        self.assertIn("Use route deep_thought", prompt)
        self.assertIn("deepthinking_agent", prompt)
        self.assertIn("return calibrated low confidence", prompt)
        self.assertIn("Available abilities / candidate capabilities JSON", prompt)
        self.assertIn("Bounded memory and world context JSON", prompt)
        self.assertIn("soridormi.walk_velocity", prompt)
        self.assertIn("robot_state", prompt)
        self.assertIn("position", prompt)
        self.assertIn("last_task", prompt)
        self.assertIn("never as authorization", prompt)
        self.assertIn("creative speech-only requests", prompt)
        self.assertIn("'go ahead'", prompt)
        self.assertIn("you look beautiful", prompt)
        self.assertIn("Do not return interrupt or ignore", prompt)
        self.assertIn("blinking", prompt)

    def test_payload_disables_qwen_thinking_and_supports_relaxed_json_retry(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Go ahead and sing a song for me.")

        payload = router.build_payload(request)
        relaxed = router.build_payload(request, relaxed_json=True)

        self.assertIs(payload["think"], False)
        self.assertIs(relaxed["think"], False)
        self.assertIsInstance(payload["format"], dict)
        self.assertEqual(relaxed["format"], "json")
        self.assertIn("Go ahead and sing a song for me.", payload["messages"][1]["content"])

    def test_route_only_json_response_gets_default_llm_confidence(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Go ahead and sing a song for me.")

        decision = router._decision_from_response(
            request,
            {"message": {"content": '{"route":"chat"}'}},
        )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertGreaterEqual(decision.confidence, 0.72)
        self.assertIn("default confidence", decision.reason or "")

    def test_llm_router_accepts_deep_thought_route(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Let's design the session memory architecture carefully.")

        decision = router._decision_from_response(
            request,
            {"message": {"content": '{"route":"deep_thought","confidence":0.88}'}},
        )

        self.assertEqual(decision.route, "deep_thought")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertNotIn("conversation_agent", decision.agents)
        self.assertIn("speaker_agent", decision.agents)
        self.assertTrue(decision.needs_agent)

    def test_low_confidence_decision_becomes_deep_thought_handoff(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Please figure out how to do this unclear task.")
        quick_decision = router._decision_from_response(
            request,
            {
                "message": {
                    "content": (
                        '{"route":"robot_action","intent":"unknown",'
                        '"confidence":0.42,"reason":"not sure"}'
                    )
                }
            },
        )

        handoff = router._low_confidence_deep_thought_decision(request, quick_decision)

        self.assertEqual(handoff.source, "llm")
        self.assertEqual(handoff.route, "deep_thought")
        self.assertEqual(handoff.intent, "deep_thought_low_confidence")
        self.assertEqual(handoff.confidence, 0.42)
        self.assertIn("quick router confidence", handoff.reason or "")
        self.assertIn("quick_route=robot_action", handoff.reason or "")
        self.assertIn("deepthinking_agent", handoff.agents)


class RouterLlmReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_interrupt_output_is_returned_for_pipeline_recovery(self) -> None:
        class InterruptRouter(OllamaLLMRouter):
            async def _chat(self, payload: dict) -> dict:
                del payload
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"interrupted"}'
                        )
                    }
                }

        router = InterruptRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="please walk forward for 10 seconds",
            context={
                "candidate_capabilities": [
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "interaction_executable": True,
                    }
                ]
            },
        )

        decision = await router.route(request)

        self.assertEqual(decision.route, "interrupt")
        self.assertEqual(decision.intent, "interrupt")
        self.assertTrue(decision.interrupt_current)
        self.assertFalse(decision.needs_agent)
        self.assertEqual(decision.reason, "interrupted")

    async def test_review_model_overrides_underspecified_robot_action(self) -> None:
        class ReviewRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    review_model="review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.payloads: list[dict] = []

            async def _chat(self, payload: dict) -> dict:
                self.payloads.append(payload)
                if payload["model"] == "review-model":
                    return {"message": {"content": '{"intent":"chat"}'}}
                return {"message": {"content": '{"route":"robot_action"}'}}

        router = ReviewRouter()
        request = RouteRequest(text="Go ahead and sing a song for me.")

        decision = await router.route(request)

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertIn("intent-only route JSON", decision.reason or "")
        self.assertIn("review_model:review-model", decision.reason or "")
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model", "review-model"])
        self.assertTrue(all(payload["think"] is False for payload in router.payloads))


if __name__ == "__main__":
    unittest.main()
