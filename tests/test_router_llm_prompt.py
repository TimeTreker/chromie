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
        self.assertIn("Generalization-first principle", prompt)
        self.assertIn("Prompt examples are guidance, not phrase", prompt)
        self.assertIn("Only the emergency filter may use phrase/pattern rules", prompt)
        self.assertIn("Emergency filter", prompt)
        self.assertIn("Quick intent router", prompt)
        self.assertIn("Route taxonomy", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("candidate_capabilities", prompt)
        self.assertIn("available abilities", prompt)
        self.assertIn("Use semantic understanding, not phrase lists", prompt)
        self.assertIn("Memory and context are hints, not authorization", prompt)
        self.assertIn("voice and/or", prompt)
        self.assertIn("body action", prompt)
        self.assertIn("creative speech-only requests as chat", prompt)
        self.assertIn("go ahead", prompt)
        self.assertIn("not physical movement", prompt)
        self.assertIn("you look beautiful", prompt)
        self.assertIn("appearance statements", prompt)
        self.assertIn("identity, name, age", prompt)
        self.assertIn("robot-status questions as chat", prompt)
        self.assertIn("deepthinking_agent", prompt)
        self.assertIn("body commands", prompt)
        self.assertIn("robot_action", prompt)
        self.assertIn("metadata.task_relation", prompt)
        self.assertIn("task_context_patch", prompt)
        self.assertIn("host task manager owns", prompt)

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
                "mind": {
                    "profile_id": "chromie_default_mind",
                    "prompt_summary": "Core principles: protect humans; owner-approved.",
                    "owner_approval_required_for_core_changes": True,
                },
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
        self.assertIn("Generalization-first principle", prompt)
        self.assertIn("not phrase rules", prompt)
        self.assertIn("do not require exact keyword matches", prompt)
        self.assertIn("Routing stages", prompt)
        self.assertIn("emergency filter", prompt)
        self.assertIn("quick intent-and-meaning router", prompt)
        self.assertIn("Use route deep_thought", prompt)
        self.assertIn("deepthinking_agent", prompt)
        self.assertIn("return calibrated low confidence", prompt)
        self.assertIn("Available abilities / candidate capabilities JSON", prompt)
        self.assertIn("Mind principles / long-term goals JSON", prompt)
        self.assertIn("Bounded memory and world context JSON", prompt)
        self.assertIn("chromie_default_mind", prompt)
        self.assertIn("owner-approved", prompt)
        self.assertIn("must not rewrite principles", prompt)
        self.assertIn("soridormi.walk_velocity", prompt)
        self.assertIn("robot_state", prompt)
        self.assertIn("position", prompt)
        self.assertIn("last_task", prompt)
        self.assertIn("never as authorization", prompt)
        self.assertIn("creative speech-only requests", prompt)
        self.assertIn("'go ahead'", prompt)
        self.assertIn("you look beautiful", prompt)
        self.assertIn("Identity, name, age", prompt)
        self.assertIn("robot-status questions are chat", prompt)
        self.assertIn("Do not return interrupt or ignore", prompt)
        self.assertIn("blinking", prompt)
        self.assertIn("metadata.task_relation", prompt)
        self.assertIn("target_task_id", prompt)
        self.assertIn("latest meaningful", prompt)

    def test_intent_review_prompt_uses_semantic_generalization(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        payload = router.build_intent_review_payload(
            RouteRequest(text="could you quickly go over there?")
        )
        system = payload["messages"][0]["content"]

        self.assertIn("Use semantic generalization", system)
        self.assertIn("examples are guidance, not keyword rules", system)
        self.assertIn("deterministic emergency/noise filter", system)

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
                        '"confidence":0.42,"reason":"not sure",'
                        '"metadata":{"task_relation":"continue_task","target_task_id":"task-1"}}'
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
        self.assertEqual(handoff.metadata["task_relation"], "continue_task")
        self.assertEqual(handoff.metadata["target_task_id"], "task-1")


class RouterLlmReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_router_returns_low_confidence_raw_for_pipeline_validation(self) -> None:
        class LowConfidenceRouter(OllamaLLMRouter):
            async def _chat(self, payload: dict) -> dict:
                del payload
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"unknown",'
                            '"confidence":0.0,"reason":"weak quick intent"}'
                        )
                    }
                }

        router = LowConfidenceRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        decision = await router.route(RouteRequest(text="Hello, how are you doing?"))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "unknown")
        self.assertEqual(decision.confidence, 0.0)
        self.assertNotEqual(decision.intent, "deep_thought_low_confidence")

    async def test_llm_interrupt_output_falls_back_to_chat(self) -> None:
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

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertFalse(decision.interrupt_current)
        self.assertTrue(decision.needs_agent)
        self.assertIn("conversation_agent", decision.agents)
        self.assertIn("deterministic-only route interrupt", decision.reason or "")

    async def test_deterministic_only_llm_mistake_skips_review_model(self) -> None:
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
                    return {"message": {"content": '{"route":"chat","intent":"identity_question"}'}}
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"interrupted"}'
                        )
                    }
                }

        router = ReviewRouter()
        decision = await router.route(RouteRequest(text="What's your name?"))

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertIn("deterministic-only route interrupt", decision.reason or "")
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model"])

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
