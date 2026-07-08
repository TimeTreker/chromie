from __future__ import annotations

import unittest

from router.app.llm_router import (
    OllamaLLMRouter,
    _catalog_observability_profile,
    _payload_message_texts,
    _prompt_feature_flags,
    _raw_router_output_summary,
)
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

        self.assertIn("AI robot-brain fast router", prompt)
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
        self.assertIn("fast lane splitter", prompt)
        self.assertIn("intent broadly", prompt)
        self.assertIn("Route Taxonomy", prompt)
        self.assertIn("current or changing information", prompt)
        self.assertIn("such as weather", prompt)
        self.assertIn("Tool Grounding", prompt)
        self.assertIn("intent=weather_query", prompt)
        self.assertIn("metadata.weather_query", prompt)
        self.assertIn("Do not answer the weather from memory", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("multi-step", prompt)
        self.assertIn("task creation", prompt)
        self.assertIn("Return one compatibility", prompt)
        self.assertIn("each item can follow its own policy", prompt)
        self.assertIn("separate task session", prompt)
        self.assertIn("worldview, lifeview, valueview", prompt)
        self.assertIn("context_profile=full_mind", prompt)
        self.assertIn("routes[]", prompt)
        self.assertIn("ordinary single-turn facts", prompt)
        self.assertIn("Multi-route Contract", prompt)
        self.assertIn("independent needs", prompt)
        self.assertIn("Do not collapse", prompt)
        self.assertIn("multi-lane work", prompt)
        self.assertIn("Uncertainty And Confirmation Acting Rule", prompt)
        self.assertIn("ask for confirmation or clarification", prompt)
        self.assertIn("weak lexical association", prompt)
        self.assertIn("do not substitute a similar skill", prompt)
        self.assertIn("Memory And Task Context", prompt)
        self.assertIn("Working memory, task context, and recent action history", prompt)
        self.assertIn("Metadata is optional", prompt)
        self.assertNotIn("thinking_mode", prompt)
        self.assertIn("session_action=none|continue_current|", prompt)
        self.assertIn("candidate_capabilities", prompt)
        self.assertIn("Affordance Grounding", prompt)
        self.assertIn("body/tool affordance", prompt)
        self.assertIn("not a phrase table", prompt)
        self.assertIn("downstream capability", prompt)
        self.assertIn("not authorization", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("robot_action", prompt)
        self.assertIn("placeholder capability IDs", prompt)
        self.assertIn("ordered actions array", prompt)
        self.assertIn("chromie.speak", prompt)
        self.assertIn("confidence", prompt)
        self.assertIn("agreement/disagreement", prompt)
        self.assertIn("weather_query", prompt)
        self.assertIn("Catalog entries", prompt)
        self.assertIn("not authorization", prompt)
        self.assertIn("metadata.desired_abilities", prompt)
        self.assertIn("status=missing_ability", prompt)
        self.assertIn("Return one compact JSON object", prompt)
        self.assertIn("compatibility keys are route, intent, and confidence", prompt)
        self.assertIn("Fast greeting/direct speech template", prompt)
        self.assertIn("Mixed route template", prompt)
        self.assertIn("direct_to_tts", prompt)
        self.assertIn("full_mind", prompt)
        self.assertIn("human-like social warmth", prompt)
        self.assertIn("not a program, programme", prompt)
        self.assertIn("Chat/fact/greeting template", prompt)
        self.assertIn("Single listed skill template", prompt)
        self.assertIn("Compound listed skill template", prompt)
        self.assertIn("Clarify / confirmation template", prompt)
        self.assertIn("too short, ambiguous", prompt)
        self.assertIn("Do not", prompt)
        self.assertIn("chain-of-thought", prompt)
        self.assertIn("progress text", prompt)


    def test_router_observability_profiles_prompt_and_raw_weather_output(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="weather-sid",
            text="今天重庆天气怎么样？",
            language="zh-CN",
            context={
                "prompt_capabilities_common": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "description": "Blink the robot eyes.",
                        "route": "robot_action",
                        "prompt_tier": "common",
                        "interaction_executable": True,
                    }
                ]
            },
        )

        payload = router.build_payload(request)
        system_text, user_text, all_text = _payload_message_texts(payload)
        flags = _prompt_feature_flags(all_text)
        catalog_profile = _catalog_observability_profile(request)
        raw_summary = _raw_router_output_summary(
            '{"route":"tool","intent":"weather_query","confidence":0.9,'
            '"fast_speech":{"text":"好的，我查一下重庆今天的天气。"},'
            '"metadata":{"tool_name":"weather","weather_query":{"location":"重庆","date":"today"}}}'
        )

        self.assertIn("Tool Grounding", system_text)
        self.assertIn("今天重庆天气怎么样？", user_text)
        self.assertTrue(flags["has_fast_speech_contract"])
        self.assertTrue(flags["has_tool_route_contract"])
        self.assertTrue(flags["has_weather_query_contract"])
        self.assertEqual(catalog_profile["common_ability_count"], 1)
        self.assertEqual(raw_summary["raw_route"], "tool")
        self.assertEqual(raw_summary["raw_intent"], "weather_query")
        self.assertTrue(raw_summary["raw_fast_speech_present"])
        self.assertTrue(raw_summary["raw_weather_query_present"])

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
                "prompt_capabilities_common": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "description": "Blink the simulated social eyes.",
                        "route": "robot_action",
                        "prompt_tier": "common",
                        "interaction_executable": True,
                        "effects": ["visual_expression"],
                        "safety_class": "low_risk_action",
                        "requires_confirmation": False,
                        "input_schema": {
                            "type": "object",
                            "required": ["count"],
                            "properties": {
                                "count": {
                                    "type": "number",
                                    "minimum": 1,
                                    "maximum": 6,
                                    "default": 2,
                                    "unit": "times",
                                    "description": "Number of visible eye blinks.",
                                }
                            },
                        },
                    }
                ],
                "robot_state": {"position": {"x": 1.0, "y": 2.0}},
                "memory": {"last_task": "walk"},
            },
        )

        prompt = router.build_user_prompt(request)

        self.assertIn("Global Context Group", prompt)
        self.assertIn("Fast Router Context", prompt)
        self.assertIn("full owner-approved mind profile", prompt)
        self.assertIn("context_profile", prompt)
        self.assertIn("fast_minimal", prompt)
        self.assertIn("capability_safety", prompt)
        self.assertIn("full_mind", prompt)
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
        self.assertIn("fast lane splitter", prompt)
        self.assertIn("the catalog constrains executable actions, not meaning", prompt)
        self.assertIn("Choose route deep_thought", prompt)
        self.assertIn("do not perform or reveal reasoning inside the router", prompt)
        self.assertIn("needs deeper thought, task-session creation, or task-session continuation", prompt)
        self.assertIn("Return calibrated low confidence", prompt)
        self.assertIn("Output Template Preview", prompt)
        self.assertIn("compatibility primary route", prompt)
        self.assertIn("Use routes[] for multiple independent policy lanes", prompt)
        self.assertIn("Multi-route contract", prompt)
        self.assertIn("separate routes[] items", prompt)
        self.assertIn("Do not collapse independent lanes into one route", prompt)
        self.assertIn("actions[] is only for ordered robot_action skills", prompt)
        self.assertIn("Uncertainty/confirmation rule", prompt)
        self.assertIn("insufficient to decide", prompt)
        self.assertIn("Short ASR fragments", prompt)
        self.assertIn("do not substitute a similar skill", prompt)
        self.assertIn("fast_speech", prompt)
        self.assertIn("process acknowledgement", prompt)
        self.assertIn("checking_only", prompt)
        self.assertIn("Tool/weather lookup", prompt)
        self.assertIn("OK, I’ll check the weather", prompt)
        self.assertIn("Single listed skill", prompt)
        self.assertIn("Multiple listed skills", prompt)
        self.assertIn("Mixed chat/memory/deepthought", prompt)
        self.assertIn("Common ability IDs", prompt)
        self.assertIn("Common Ability Catalog JSON", prompt)
        self.assertNotIn("not " + "recommendations", prompt)
        self.assertIn("metadata.desired_abilities", prompt)
        self.assertIn("Affordance Grounding", prompt)
        self.assertIn("compact body/tool affordance interface", prompt)
        self.assertIn("not a phrase table", prompt)
        self.assertIn("duration, distance, count, direction, speed", prompt)
        self.assertIn("single parameterized physical request", prompt)
        self.assertIn("downstream capability planner", prompt)
        self.assertIn("Do not choose a physical skill from isolated letters", prompt)
        self.assertIn("low-information ASR fragments", prompt)
        self.assertNotIn("Semantic Examples", prompt)
        self.assertNotIn("no executable blink skill is in the compact skill catalog", prompt)
        self.assertIn("Bounded session, memory, task, and robot/world context JSON", prompt)
        self.assertIn("chromie_default_mind", prompt)
        self.assertIn("Chromie", prompt)
        self.assertNotIn("6 years old in robot identity terms", prompt)
        self.assertNotIn("Protect humans first.", prompt)
        self.assertNotIn("Become a useful companion robot.", prompt)
        self.assertNotIn("soridormi.walk_velocity", prompt)
        self.assertIn("soridormi.blink_eyes", prompt)
        self.assertIn("count", prompt)
        self.assertIn("required_args", prompt)
        self.assertIn("Number of visible eye blinks", prompt)
        self.assertIn("times", prompt)
        self.assertIn("low_risk_action", prompt)
        self.assertIn("robot_state", prompt)
        self.assertIn("position", prompt)
        self.assertIn("last_task", prompt)
        self.assertIn("authorize side effects", prompt)
        self.assertIn("Speech-only conversation", prompt)
        self.assertIn("treat the speech as a skill task", prompt)
        self.assertIn("Do not return interrupt or ignore", prompt)
        self.assertIn("politeness", prompt)
        self.assertIn("working memory, current task context, and recent action history", prompt)
        self.assertIn("Required compatibility keys: route, intent, confidence", prompt)
        self.assertIn("routes[] item", prompt)
        self.assertIn("Allowed lanes", prompt)
        self.assertIn("Allowed context_profile values", prompt)
        self.assertIn("Omit agents, metadata", prompt)
        self.assertIn("non-executable ability proposals", prompt)
        self.assertIn("include actions as an ordered array", prompt)
        self.assertIn("\"confidence\":0.0", prompt)
        self.assertIn("downstream capability planner", prompt)
        self.assertIn("chain-of-thought", prompt)
        self.assertIn("progress text", prompt)
        self.assertIn("placeholder intents", prompt)
        self.assertIn("speak_first", prompt)
        self.assertIn("human-like social warmth", prompt)
        self.assertIn("not a program, programme", prompt)
        self.assertIn("Return one compact JSON object matching one of the templates", prompt)

    def test_fast_router_prompt_uses_common_ability_catalog_not_full_catalog(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Please blink twice.",
            language="en-US",
            context={
                "common_ability_catalog": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "description": "Blink the robot eyes visibly.",
                        "route": "robot_action",
                        "prompt_tier": "common",
                        "interaction_executable": True,
                    }
                ],
                "full_ability_catalog": [
                    {
                        "capability_id": "soridormi.motion.calibrate_floor",
                        "description": "Rare floor calibration workflow.",
                        "route": "robot_action",
                        "prompt_tier": "rare",
                        "interaction_executable": True,
                    }
                ],
                "prompt_capabilities_all": [
                    {
                        "capability_id": "soridormi.motion.calibrate_floor",
                        "description": "Rare floor calibration workflow.",
                        "route": "robot_action",
                        "prompt_tier": "rare",
                        "interaction_executable": True,
                    }
                ],
            },
        )

        prompt = router.build_user_prompt(request)

        self.assertIn("Common Ability Catalog JSON", prompt)
        self.assertIn("soridormi.blink_eyes", prompt)
        self.assertNotIn("soridormi.motion.calibrate_floor", prompt)

    def test_fast_router_prompt_excludes_locked_common_catalog_entries(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Run floor calibration.",
            language="en-US",
            context={
                "common_ability_catalog": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "description": "Blink the robot eyes visibly.",
                        "route": "robot_action",
                        "prompt_tier": "common",
                        "interaction_executable": True,
                    },
                    {
                        "capability_id": "soridormi.motion.calibrate_floor",
                        "description": "Locked safety-sensitive calibration workflow.",
                        "route": "robot_action",
                        "prompt_tier": "common",
                        "prompt_tier_locked": True,
                        "interaction_executable": True,
                    },
                ],
            },
        )

        prompt = router.build_user_prompt(request)

        self.assertIn("soridormi.blink_eyes", prompt)
        self.assertNotIn("soridormi.motion.calibrate_floor", prompt)

    def test_route_stage_preserves_missing_desired_ability_proposal(self) -> None:
        decision = RouteDecision(
            route="deep_thought",
            agents=["deepthinking_agent", "speaker_agent"],
            intent="deep_thought_missing_common_skill",
            confidence=0.61,
            language="en-US",
            source="llm",
            metadata={
                "desired_abilities": [
                    {
                        "ability_id": "social.blink_eyes",
                        "intent": "blink eyes",
                        "status": "missing_ability",
                        "confidence": 0.91,
                        "reason": "No executable blink skill is in the common catalog.",
                    }
                ]
            },
        )

        finalized = RouteDecision.model_validate(decision.model_dump())
        from router.app.schema import annotate_default_stage_output

        annotated = annotate_default_stage_output(finalized)
        proposals = [
            item for item in annotated.metadata["task_proposals"]
            if item.get("proposal_kind") == "ability"
        ]

        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal["state"], "missing_ability")
        self.assertEqual(proposal["ability_id"], "social.blink_eyes")
        self.assertEqual(proposal["metadata"]["confidence"], 0.91)
        self.assertFalse(proposal["effectful"])
        self.assertNotIn("social.blink_eyes", annotated.actions)

    def test_user_prompt_uses_extracted_memory_not_raw_history(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="s1",
            text="continue with that design",
            language="en-US",
            context={
                "history": [
                    {
                        "role": "user",
                        "text": "RAW_TRANSCRIPT_SHOULD_NOT_REACH_ROUTER_PROMPT",
                    }
                ],
                "conversation": {
                    "history": [
                        {
                            "role": "assistant",
                            "text": "RAW_CONVERSATION_SHOULD_NOT_REACH_ROUTER_PROMPT",
                        }
                    ]
                },
                "session_memory": {
                    "kind": "short_term_session_memory",
                    "conversation_id": "session",
                    "recent_user_request": "RAW_RECENT_USER_SHOULD_NOT_REACH_ROUTER_PROMPT",
                    "recent_assistant_response": "RAW_RECENT_ASSISTANT_SHOULD_NOT_REACH_ROUTER_PROMPT",
                    "memory_summary": "- Current task: design extracted prompt memory",
                    "extracted_memory": [
                        {
                            "scope": "task",
                            "kind": "goal",
                            "text": "Current task: design extracted prompt memory",
                            "confidence": 0.9,
                        }
                    ],
                },
            },
        )

        prompt = router.build_user_prompt(request)

        self.assertIn("Current task: design extracted prompt memory", prompt)
        self.assertNotIn("RAW_TRANSCRIPT_SHOULD_NOT_REACH_ROUTER_PROMPT", prompt)
        self.assertNotIn("RAW_CONVERSATION_SHOULD_NOT_REACH_ROUTER_PROMPT", prompt)
        self.assertNotIn("RAW_RECENT_USER_SHOULD_NOT_REACH_ROUTER_PROMPT", prompt)
        self.assertNotIn("RAW_RECENT_ASSISTANT_SHOULD_NOT_REACH_ROUTER_PROMPT", prompt)

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
                    "common_ability_catalog": [
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
        self.assertIn("Common ability catalog JSON", user)
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
                    "common_ability_catalog": [
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

    def test_intent_only_weather_capability_uses_tool_route(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="今天重庆天气怎么样？",
            language="zh-CN",
            context={
                "prompt_capabilities_common": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "description": "Read current weather or forecast for a city.",
                        "route": "tool",
                        "prompt_tier": "common",
                    }
                ]
            },
        )

        decision = router._decision_from_response(
            request,
            {"message": {"content": '{"intent":"capability:chromie.weather.lookup","confidence":0.9}'}},
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "capability:chromie.weather.lookup")
        self.assertIn("normalized capability route", decision.reason or "")

    def test_skill_id_route_weather_capability_uses_tool_route(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="今天重庆天气怎么样？",
            language="zh-CN",
            context={
                "prompt_capabilities_common": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "description": "Read current weather or forecast for a city.",
                        "route": "tool",
                        "prompt_tier": "common",
                    }
                ]
            },
        )

        decision = router._decision_from_response(
            request,
            {"message": {"content": '{"route":"chromie.weather.lookup","confidence":0.9}'}},
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "capability:chromie.weather.lookup")
        self.assertIn("normalized capability route", decision.reason or "")

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

    def test_llm_router_accepts_mixed_route_items_and_builds_task_proposals(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Hi, remember I like tea, and think through tomorrow.")

        decision = router._decision_from_response(
            request,
            {
                "message": {
                    "content": (
                        '{"route":"chat","intent":"mixed_request","confidence":0.82,'
                        '"routes":['
                        '{"route":"chat","intent":"greeting","confidence":0.95,'
                        '"lane":"immediate_speech","context_profile":"fast_minimal",'
                        '"direct_to_tts":true,"text":"Hi, I am here."},'
                        '{"route":"memory","intent":"remember_user_preference",'
                        '"confidence":0.86,"lane":"post_turn",'
                        '"context_profile":"session_compact"},'
                        '{"route":"deep_thought","intent":"plan_tomorrow",'
                        '"confidence":0.78,"lane":"deepthought",'
                        '"context_profile":"full_mind","requires_mind":true}'
                        ']}'
                    )
                }
            },
        )

        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(len(decision.routes), 3)
        self.assertEqual(decision.metadata["route_item_count"], 3)
        self.assertIn("dominant compatibility route", decision.reason or "")
        from router.app.schema import annotate_pipeline_stage_outputs

        annotated = annotate_pipeline_stage_outputs(decision)

        self.assertEqual(
            [item["task_type"] for item in annotated.metadata["task_list"]],
            [
                "speech.fast_reply",
                "memory.remember_session_context",
                "cognition.delegate_deep_thought",
                "cognition.deep_think",
            ],
        )
        proposals = annotated.metadata["task_proposals"]
        self.assertTrue(
            any(
                item["task_type"] == "speech.fast_reply"
                and item["metadata"]["direct_to_tts"] is True
                and item["metadata"]["context_profile"] == "fast_minimal"
                for item in proposals
            )
        )
        self.assertTrue(
            any(
                item["task_type"] == "cognition.deep_think"
                and item["metadata"]["requires_mind"] is True
                and item["metadata"]["context_profile"] == "full_mind"
                for item in proposals
            )
        )

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
                        '"speak_first":"Give me a moment to think about that.",'
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
        self.assertEqual(handoff.speak_first, "Give me a moment to think about that.")
        self.assertIn("quick router confidence", handoff.reason or "")
        self.assertIn("quick_route=robot_action", handoff.reason or "")
        self.assertIn("deepthinking_agent", handoff.agents)
        self.assertEqual(handoff.metadata["task_relation"], "continue_task")
        self.assertEqual(handoff.metadata["target_task_id"], "task-1")
        self.assertTrue(handoff.metadata["thinking_ack_allowed"])
        self.assertEqual(handoff.metadata["thinking_ack_source"], "quick_llm_speak_first")


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
                "common_ability_catalog": [
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
                    "common_ability_catalog": [
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
                "common_ability_catalog": [
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
                    "common_ability_catalog": [
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
                    "common_ability_catalog": [
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
                    "common_ability_catalog": [
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
                    "common_ability_catalog": [
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

    async def test_review_model_completes_underspecified_robot_action_with_exact_skill(self) -> None:
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
                                '"intent":"soridormi.walk_forward",'
                                '"confidence":0.92}'
                            )
                        }
                    }
                return {"message": {"content": '{"route":"robot_action","intent":"robot_action"}'}}

        router = ReviewRouter()
        request = RouteRequest(
            text="Walk forward for 15 seconds, please.",
            language="en-US",
            context={
                "prompt_capabilities_all": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "description": "Human-facing wrapper for natural walking requests.",
                        "interaction_executable": True,
                        "available": True,
                        "route": "robot_action",
                        "effects": ["physical_motion"],
                    }
                ]
            },
        )

        decision = await router.route(request)
        review_user = router.payloads[1]["messages"][1]["content"]

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "soridormi.walk_forward")
        self.assertIn("selected exact skill for underspecified robot_action", decision.reason or "")
        self.assertIn("soridormi.walk_forward", review_user)
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model", "review-model"])

    async def test_review_model_skill_id_route_is_normalized_to_robot_action(self) -> None:
        class ReviewRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    review_model="review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                    slow_review_recovery_enabled=True,
                )
                self.payloads: list[dict] = []

            async def _chat(self, payload: dict) -> dict:
                self.payloads.append(payload)
                if payload["model"] == "review-model":
                    return {
                        "message": {
                            "content": (
                                '{"route":"soridormi.blink_eyes",'
                                '"intent":"soridormi.blink_eyes",'
                                '"confidence":1.0}'
                            )
                        }
                    }
                return {"message": {"content": '{"route":"robot_action","intent":"robot_action"}'}}

        router = ReviewRouter()
        decision = await router.route(
            RouteRequest(
                text="眨两下眼睛。",
                language="zh-CN",
                context={
                    "prompt_capabilities_all": [
                        {
                            "capability_id": "soridormi.blink_eyes",
                            "description": "Blink the simulated social eyes.",
                            "interaction_executable": True,
                            "available": True,
                            "route": "robot_action",
                            "effects": ["visual_expression"],
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertIn("skill id in route field", decision.reason or "")
        self.assertIn("selected exact skill for underspecified robot_action", decision.reason or "")
        self.assertEqual([payload["model"] for payload in router.payloads], ["test-model", "review-model"])

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
                    "common_ability_catalog": [
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
                    "common_ability_catalog": [
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
                    "common_ability_catalog": [
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


    async def test_tool_route_missing_fast_speech_is_repaired_by_router_llm(self) -> None:
        class WeatherRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict) -> dict:
                system = str(payload["messages"][0].get("content") or "")
                stage = "fast_speech_repair" if "fast-speech repairer" in system else "primary_router"
                self.stages.append(stage)
                if stage == "fast_speech_repair":
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"好的，我查一下重庆今天的天气。",'
                                '"purpose":"acknowledge_and_check",'
                                '"commitment":"checking_only",'
                                '"must_not_claim_completion":true}}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"tool","intent":"weather_query","confidence":0.95,'
                            '"metadata":{"tool_name":"weather",'
                            '"weather_query":{"location":"重庆","date":"today","units":"metric"}}}'
                        )
                    }
                }

        router = WeatherRouter()
        decision = await router.route(
            RouteRequest(
                text="今天重庆天气怎么样？",
                language="zh-CN",
                context={
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "effects": ["external_read", "weather_lookup"],
                            "description": "Retrieve current weather or forecast for a city.",
                        }
                    ]
                },
            )
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "weather_query")
        self.assertIsNotNone(decision.fast_speech)
        self.assertEqual(decision.fast_speech.text, "好的，我查一下重庆今天的天气。")
        self.assertEqual(decision.fast_speech.commitment, "checking_only")
        self.assertIn("fast_speech_repair", decision.metadata)
        self.assertEqual(router.stages, ["primary_router", "fast_speech_repair"])

    async def test_tool_route_existing_fast_speech_does_not_repair(self) -> None:
        class WeatherRouter(OllamaLLMRouter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict) -> dict:
                self.stages.append("primary_router")
                return {
                    "message": {
                        "content": (
                            '{"route":"tool","intent":"weather_query","confidence":0.95,'
                            '"fast_speech":{"text":"好的，我查一下重庆今天的天气。",'
                            '"purpose":"acknowledge_and_check","commitment":"checking_only",'
                            '"must_not_claim_completion":true},'
                            '"metadata":{"tool_name":"weather",'
                            '"weather_query":{"location":"重庆","date":"today","units":"metric"}}}'
                        )
                    }
                }

        router = WeatherRouter()
        decision = await router.route(RouteRequest(text="今天重庆天气怎么样？", language="zh-CN"))

        self.assertEqual(decision.route, "tool")
        self.assertIsNotNone(decision.fast_speech)
        self.assertEqual(router.stages, ["primary_router"])

    def test_fast_speech_repair_payload_preserves_route_and_forbids_results(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="今天重庆天气怎么样？",
            language="zh-CN",
            context={
                "common_ability_catalog": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "route": "tool",
                        "effects": ["external_read", "weather_lookup"],
                        "description": "Retrieve current weather or forecast for a city.",
                    }
                ]
            },
        )
        decision = RouteDecision(
            route="tool",
            intent="weather_query",
            confidence=0.95,
            metadata={
                "tool_name": "weather",
                "weather_query": {"location": "重庆", "date": "today", "units": "metric"},
            },
        )

        payload = router.build_fast_speech_repair_payload(request, decision)
        rendered = "\n".join(str(message.get("content") or "") for message in payload["messages"])

        self.assertIn("fast-speech repairer", rendered)
        self.assertIn("Do not change route", rendered)
        self.assertIn("will check the requested location/date", rendered)
        self.assertIn("Never claim a tool result", rendered)
        self.assertIn("今天重庆天气怎么样", rendered)
        self.assertIn("weather_query", rendered)


if __name__ == "__main__":
    unittest.main()
