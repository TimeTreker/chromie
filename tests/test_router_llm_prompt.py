from __future__ import annotations

import unittest

from router.app.llm_router import OllamaLLMRouter
from router.app.schema import RouteDecision, RouteRequest


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
        self.assertIn("Prompt Architecture", prompt)
        self.assertIn("Global Context Group", prompt)
        self.assertIn("Session Context Group", prompt)
        self.assertIn("Current Job", prompt)
        self.assertIn("Task Context", prompt)
        self.assertIn("Output Contract", prompt)
        self.assertLess(prompt.index("Global Context Group"), prompt.index("Current Job"))
        self.assertLess(prompt.index("Current Job"), prompt.index("Task Context"))
        self.assertIn("Generalization-first principle", prompt)
        self.assertIn("Do not replace normal routing", prompt)
        self.assertIn("Only deterministic", prompt)
        self.assertIn("emergency/noise controls", prompt)
        self.assertIn("phrase/pattern rules", prompt)
        self.assertIn("quick intent router", prompt)
        self.assertIn("Route Taxonomy", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("multi-step task creation", prompt)
        self.assertIn("requests that need a separate task session", prompt)
        self.assertIn("ordinary single-turn facts", prompt)
        self.assertIn("Memory And Task Context", prompt)
        self.assertIn("Working memory, task context, and recent action history", prompt)
        self.assertIn("Metadata is optional", prompt)
        self.assertNotIn("thinking_mode", prompt)
        self.assertIn("session_action=none|continue_current|", prompt)
        self.assertIn("candidate_capabilities", prompt)
        self.assertIn("not authorization", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("robot_action", prompt)
        self.assertIn("placeholder capability IDs", prompt)
        self.assertIn("agreement/disagreement", prompt)
        self.assertIn("Candidate capabilities are context, not authorization", prompt)
        self.assertIn("Return compact JSON only", prompt)
        self.assertIn("Do not output", prompt)
        self.assertIn("chain-of-thought", prompt)
        self.assertIn("progress text", prompt)

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
                    "identity": {
                        "name": "Chromie",
                        "age_description": "6 years old in robot identity terms",
                        "pronouns": ["she", "her"],
                    },
                    "core_principles": [
                        {
                            "id": "protect_humans",
                            "statement": "Protect humans first.",
                        }
                    ],
                    "long_term_goals": [
                        {
                            "id": "useful_companion_robot",
                            "statement": "Become a useful companion robot.",
                        }
                    ],
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

        self.assertIn("Global Context Group", prompt)
        self.assertIn("Robot Identity", prompt)
        self.assertIn("Worldview", prompt)
        self.assertIn("Lifeview", prompt)
        self.assertIn("Valueview", prompt)
        self.assertIn("Session Context Group", prompt)
        self.assertIn("Current Job", prompt)
        self.assertIn("Task Context Group", prompt)
        self.assertIn("Cost Function", prompt)
        self.assertIn("Output Contract", prompt)
        self.assertLess(prompt.index("Global Context Group"), prompt.index("Session Context Group"))
        self.assertLess(prompt.index("Session Context Group"), prompt.index("Current Job"))
        self.assertLess(prompt.index("Current Job"), prompt.index("Task Context Group"))
        self.assertLess(prompt.index("Task Context Group"), prompt.index("Output Contract"))
        self.assertIn("Infer from meaning/context/abilities/schemas", prompt)
        self.assertIn("not phrase rules", prompt)
        self.assertIn("deterministic emergency/noise filter", prompt)
        self.assertIn("quick intent router", prompt)
        self.assertIn("Choose route deep_thought", prompt)
        self.assertIn("do not perform or reveal reasoning inside the router", prompt)
        self.assertIn("needs deeper thought, task-session creation, or task-session continuation", prompt)
        self.assertIn("Return calibrated low confidence", prompt)
        self.assertIn("Available abilities / candidate_capabilities JSON", prompt)
        self.assertIn("Factual agreement/disagreement is chat", prompt)
        self.assertIn("Moon, Sun, shape, temperature", prompt)
        self.assertIn("not deep_thought or robot_action", prompt)
        self.assertIn("routes common-fact questions to chat", prompt)
        self.assertIn("Semantic Examples", prompt)
        self.assertIn("factual_agreement", prompt)
        self.assertIn("planning-only or weak background context", prompt)
        self.assertIn("Bounded session, memory, task, and robot/world context JSON", prompt)
        self.assertIn("chromie_default_mind", prompt)
        self.assertIn("Chromie", prompt)
        self.assertIn("6 years old in robot identity terms", prompt)
        self.assertIn("Protect humans first.", prompt)
        self.assertIn("Become a useful companion robot.", prompt)
        self.assertIn("owner-approved", prompt)
        self.assertIn("soridormi.walk_velocity", prompt)
        self.assertIn("robot_state", prompt)
        self.assertIn("position", prompt)
        self.assertIn("last_task", prompt)
        self.assertIn("authorize side effects", prompt)
        self.assertIn("Speech-only conversation", prompt)
        self.assertIn("Do not return interrupt or ignore", prompt)
        self.assertIn("polite ability-shaped request", prompt)
        self.assertIn("working memory, current task context, and recent action history", prompt)
        self.assertIn("Required keys: route, intent, confidence", prompt)
        self.assertIn("Omit agents, actions, metadata", prompt)
        self.assertIn("chain-of-thought", prompt)
        self.assertIn("progress text", prompt)
        self.assertIn("placeholder intents", prompt)
        self.assertIn("Return compact JSON only", prompt)

    def test_intent_review_prompt_uses_semantic_generalization(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        payload = router.build_intent_review_payload(
            RouteRequest(
                text="你能摇头吗",
                language="zh-CN",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.shake_no",
                            "interaction_executable": True,
                        }
                    ]
                },
            )
        )
        system = payload["messages"][0]["content"]
        user = payload["messages"][1]["content"]

        self.assertIn("Global Context Group", system)
        self.assertIn("Session Context Group", system)
        self.assertIn("Current Job", system)
        self.assertIn("Task Context Group", system)
        self.assertIn("Output Contract", system)
        self.assertIn("Use semantic generalization", system)
        self.assertIn("do not turn prompt wording into keyword rules", system)
        self.assertIn("deterministic emergency/noise filter", system)
        self.assertIn("pragmatically asking Chromie", system)
        self.assertIn("working memory, task context, and recent action history", system)
        self.assertIn("multi-step task-session work", system)
        self.assertIn("chain-of-thought", system)
        self.assertIn("progress text", system)
        self.assertIn("Candidate capabilities JSON", user)
        self.assertIn("soridormi.shake_no", user)
        self.assertIn("capability:<exact capability_id>", system)

    def test_post_interrupt_review_prompt_confirms_or_corrects_after_safety_stop(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            review_model="review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        payload = router.build_post_interrupt_review_payload(
            RouteRequest(
                text="Stop by the table means what?",
                language="en-US",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "interaction_executable": True,
                        }
                    ],
                    "asr_alternatives": ["What does stop by the table mean?"],
                },
            ),
            RouteDecision(
                route="interrupt",
                intent="stop_current_output",
                confidence=0.99,
                reason="deterministic stop phrase",
                source="rules",
            ),
        )
        system = payload["messages"][0]["content"]
        user = payload["messages"][1]["content"]

        self.assertEqual(payload["model"], "review-model")
        self.assertIn("post-interrupt semantic reviewer", system)
        self.assertIn("already applied the deterministic interrupt/cancel lane", system)
        self.assertIn("confirm that interpretation or propose the correct non-interrupt route", system)
        self.assertIn("do not create phrase rules", system)
        self.assertIn("Already-applied emergency-filter decision JSON", system)
        self.assertIn("speak_first may contain one brief apology/correction sentence", system)
        self.assertIn("must not claim a physical action or tool side effect has executed", system)
        self.assertIn("chain-of-thought", system)
        self.assertIn("progress text", system)
        self.assertIn("confidence >= 0.72", system)
        self.assertIn("Stop by the table means what?", user)
        self.assertIn("soridormi.walk_forward", user)

    def test_payload_disables_qwen_thinking_and_uses_compact_json_mode(self) -> None:
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
        self.assertEqual(payload["format"], "json")
        self.assertEqual(relaxed["format"], "json")
        self.assertEqual(payload["options"]["num_predict"], 192)
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

    async def test_deterministic_only_llm_mistake_uses_review_model(self) -> None:
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

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "identity_question")
        self.assertIn("deterministic-only route interrupt", decision.reason or "")
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model", "review-model"])

    async def test_slow_review_recovery_can_be_disabled_for_realtime_latency(self) -> None:
        class ReviewRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    review_model="review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                    slow_review_recovery_enabled=False,
                )
                self.payloads: list[dict] = []

            async def _chat(self, payload: dict) -> dict:
                self.payloads.append(payload)
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"bad quick route"}'
                        )
                    }
                }

        router = ReviewRouter()
        decision = await router.route(RouteRequest(text="What's your name?"))

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertIn("slow repair disabled", decision.reason or "")
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model"])

    async def test_review_model_can_recover_invalid_interrupt_to_robot_action(self) -> None:
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
                    return {"message": {"content": '{"route":"robot_action","intent":"robot_action","confidence":0.74}'}}
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"interrupted"}'
                        )
                    }
                }

        router = ReviewRouter()
        decision = await router.route(
            RouteRequest(
                text="你能摇头吗",
                language="zh-CN",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.shake_no",
                            "interaction_executable": True,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "robot_action")
        self.assertIn("review_model:review-model recovered", decision.reason or "")
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model", "review-model"])

    async def test_review_model_repairs_walk_command_misclassified_as_interrupt(self) -> None:
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
                    return {
                        "message": {
                            "content": (
                                '{"route":"robot_action","intent":"robot_action",'
                                '"confidence":0.95,"reason":"walking request"}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"interrupted"}'
                        )
                    }
                }

        router = ReviewRouter()
        request = RouteRequest(
            text="Okay, please walk ahead for a few seconds. Please. Quickly.",
            language="en-US",
            context={
                "candidate_capabilities": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "description": "Human-facing wrapper for natural requests like walk forward, walk slowly, and walk quickly.",
                        "interaction_executable": True,
                        "available": True,
                        "effects": ["physical_motion"],
                        "route": "robot_action",
                        "score": 0.38,
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "speed": {"type": "string", "enum": ["slow", "normal", "quick"]},
                                "duration_s": {"type": "number"},
                            },
                        },
                    }
                ]
            },
        )

        decision = await router.route(request)
        review_user = router.payloads[1]["messages"][1]["content"]

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "robot_action")
        self.assertIn("review_model:review-model recovered", decision.reason or "")
        self.assertIn("soridormi.walk_forward", review_user)
        self.assertNotIn("input_schema", review_user)

    async def test_review_failure_does_not_recover_invalid_interrupt_from_catalog_candidate(self) -> None:
        class ReviewFailureRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    review_model="review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )

            async def _chat(self, payload: dict) -> dict:
                if payload["model"] == "review-model":
                    return {"message": {"content": ""}}
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"interrupted"}'
                        )
                    }
                }

        router = ReviewFailureRouter()
        decision = await router.route(
            RouteRequest(
                text="你能摇头吗",
                language="zh-CN",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.shake_no",
                            "interaction_executable": True,
                            "available": True,
                            "score": 0.86,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertIn("deterministic-only route interrupt", decision.reason or "")

    async def test_fast_repair_model_recovers_when_review_model_fails(self) -> None:
        class RepairRouter(OllamaLLMRouter):
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
                    return {"message": {"content": ""}}
                system = payload["messages"][0]["content"]
                if "Repair a realtime robot route" in system:
                    return {
                        "message": {
                            "content": (
                                '{"route":"robot_action",'
                                '"intent":"capability:soridormi.walk_forward",'
                                '"confidence":0.74,'
                                '"reason":"semantic repair matched candidate"}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"interrupted"}'
                        )
                    }
                }

        router = RepairRouter()
        decision = await router.route(
            RouteRequest(
                text="Okay, please walk forward for 15 seconds, quickly, please.",
                language="en-US",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "description": "Human-facing wrapper for natural walking requests.",
                            "interaction_executable": True,
                            "available": True,
                            "effects": ["physical_motion"],
                            "route": "robot_action",
                            "score": 0.515,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("fast_model:test-model repaired", decision.reason or "")
        self.assertEqual(
            [payload["model"] for payload in router.payloads],
            ["test-model", "review-model", "test-model"],
        )

    async def test_review_model_recovers_primary_router_timeout(self) -> None:
        class TimeoutRouter(OllamaLLMRouter):
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
                    return {
                        "message": {
                            "content": (
                                '{"route":"robot_action",'
                                '"intent":"capability:soridormi.walk_forward",'
                                '"confidence":0.84,'
                                '"reason":"review matched walk capability"}'
                            )
                        }
                    }
                raise TimeoutError("quick model timed out")

        router = TimeoutRouter()
        decision = await router.route(
            RouteRequest(
                text="Please walk ahead for 15 seconds.",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "interaction_executable": True,
                            "available": True,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("review_model:review-model recovered route", decision.reason or "")
        self.assertEqual(
            [payload["model"] for payload in router.payloads],
            ["test-model", "review-model"],
        )

    async def test_fast_repair_model_runs_after_low_confidence_review_recovery(self) -> None:
        class RepairRouter(OllamaLLMRouter):
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
                    return {
                        "message": {
                            "content": (
                                '{"route":"robot_action",'
                                '"intent":"soridormi.motion.create_plan",'
                                '"confidence":0.27,'
                                '"reason":"uncertain planning intent"}'
                            )
                        }
                    }
                system = payload["messages"][0]["content"]
                if "Repair a realtime robot route" in system:
                    return {
                        "message": {
                            "content": (
                                '{"route":"robot_action",'
                                '"intent":"capability:soridormi.walk_forward",'
                                '"confidence":0.81,'
                                '"reason":"semantic repair matched executable candidate"}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"interrupt","intent":"interrupt",'
                            '"confidence":0.0,"reason":"interrupted"}'
                        )
                    }
                }

        router = RepairRouter()
        decision = await router.route(
            RouteRequest(
                text="Okay, please walk forward for 15 seconds, quickly, please.",
                language="en-US",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "description": "Human-facing wrapper for natural walking requests.",
                            "interaction_executable": True,
                            "available": True,
                            "effects": ["physical_motion"],
                            "route": "robot_action",
                            "score": 0.515,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("fast_model:test-model repaired", decision.reason or "")
        self.assertEqual(
            [payload["model"] for payload in router.payloads],
            ["test-model", "review-model", "test-model"],
        )

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

    async def test_ambiguous_deep_thought_tries_review_before_fallback(self) -> None:
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
                return {
                    "message": {
                        "content": (
                            '{"route":"deep_thought","intent":"unknown",'
                            '"confidence":0.85}'
                        )
                    }
                }

        router = ReviewRouter()
        decision = await router.route(
            RouteRequest(
                text="Hello, how are you.",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "interaction_executable": True,
                            "available": True,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertIn("ambiguous_llm_deep_thought", decision.reason or "")
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model", "review-model"])

    async def test_ambiguous_deep_thought_review_recovers_chinese_walk_command(self) -> None:
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
                    return {
                        "message": {
                            "content": (
                                '{"route":"robot_action",'
                                '"intent":"capability:soridormi.walk_forward",'
                                '"confidence":0.86,'
                                '"reason":"semantic review matched a walking request"}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"deep_thought","intent":"unknown",'
                            '"confidence":0.85}'
                        )
                    }
                }

        router = ReviewRouter()
        decision = await router.route(
            RouteRequest(
                text="往前走个15秒。",
                language="zh-CN",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "description": "Human-facing wrapper for natural walking requests.",
                            "interaction_executable": True,
                            "available": True,
                            "effects": ["physical_motion"],
                            "route": "robot_action",
                            "score": 0.0,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("review_model:review-model reviewed ambiguous deep_thought", decision.reason or "")
        review_prompt = router.payloads[1]["messages"][1]["content"]
        self.assertIn("往前走个15秒", review_prompt)
        self.assertIn("soridormi.walk_forward", review_prompt)

    async def test_ambiguous_deep_thought_review_failure_falls_back_to_chat(self) -> None:
        class ReviewRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    review_model="review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )

            async def _chat(self, payload: dict) -> dict:
                if payload["model"] == "review-model":
                    raise TimeoutError("review timed out")
                return {
                    "message": {
                        "content": (
                            '{"route":"deep_thought","intent":"unknown",'
                            '"confidence":0.85}'
                        )
                    }
                }

        router = ReviewRouter()
        decision = await router.route(RouteRequest(text="Hello, how are you."))

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertIn("ambiguous_llm_deep_thought", decision.reason or "")

    async def test_placeholder_capability_intent_is_repaired_before_agent(self) -> None:
        class PlaceholderRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.payloads: list[dict] = []

            async def _chat(self, payload: dict) -> dict:
                self.payloads.append(payload)
                system = payload["messages"][0]["content"]
                if "placeholder capability intent" in system:
                    return {
                        "message": {
                            "content": (
                                '{"route":"chat","intent":"greeting",'
                                '"confidence":0.93,"reason":"speech-only greeting"}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action","intent":"capability",'
                            '"confidence":1.0,"reason":"bad placeholder"}'
                        )
                    }
                }

        router = PlaceholderRouter()
        decision = await router.route(
            RouteRequest(
                text="Hello, how are you.",
                context={
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "interaction_executable": True,
                            "available": True,
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "greeting")
        self.assertIn("repaired placeholder capability intent", decision.reason or "")
        self.assertEqual(len(router.payloads), 2)

    async def test_placeholder_capability_repair_failure_falls_back_to_chat(self) -> None:
        class PlaceholderRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )

            async def _chat(self, payload: dict) -> dict:
                system = payload["messages"][0]["content"]
                if "placeholder capability intent" in system:
                    return {"message": {"content": '{"route":"robot_action","intent":"capability"}'}}
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action","intent":"capability",'
                            '"confidence":1.0,"reason":"bad placeholder"}'
                        )
                    }
                }

        router = PlaceholderRouter()
        decision = await router.route(RouteRequest(text="Hello, how are you."))

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertIn("placeholder capability intent", decision.reason or "")


if __name__ == "__main__":
    unittest.main()
