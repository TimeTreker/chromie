from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    SemanticRouteRepairOutput,
    _catalog_observability_profile,
    _payload_message_texts,
    _prompt_feature_flags,
    _raw_interpreter_output_summary,
    is_allowed_model_ignore,
)
from agent.app.cognitive_core.goal_interpreter.fallback import InterpretationUnavailableError
from agent.app.cognitive_core.goal_interpreter.schema import (
    FastSpeech,
    RouteDecision,
    RouteRequest,
)


class GoalInterpreterLlmPromptTests(unittest.TestCase):
    def test_semantic_repair_accepts_typed_catalog_action_proposals(self) -> None:
        output = SemanticRouteRepairOutput.model_validate(
            {
                "route": "robot_action",
                "intent": "compound_body_request",
                "confidence": 0.94,
                "actions": [
                    {
                        "capability_id": "soridormi.nod_head",
                        "args": {"count": 1},
                        "sequence": 0,
                        "timing": "sequential",
                        "confidence": 0.96,
                    },
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "sequence": 1,
                        "timing": "sequential",
                        "confidence": 0.95,
                    },
                ],
            }
        )

        self.assertEqual(
            [action.capability_id for action in output.actions],
            ["soridormi.nod_head", "soridormi.blink_eyes"],
        )
        self.assertEqual(output.actions[1].args, {"count": 2})

    def test_semantic_repair_rejects_actions_outside_robot_action_lane(self) -> None:
        with self.assertRaisesRegex(ValueError, "route=robot_action"):
            SemanticRouteRepairOutput.model_validate(
                {
                    "route": "chat",
                    "intent": "greeting",
                    "confidence": 0.9,
                    "actions": [
                        {
                            "capability_id": "soridormi.blink_eyes",
                            "args": {},
                            "confidence": 0.9,
                        }
                    ],
                }
            )

    def test_missing_ability_alias_is_canonicalized_before_branch_validation(self) -> None:
        output = SemanticRouteRepairOutput.model_validate(
            {
                "route": "clarify",
                "intent": "missing_or_supported_ability",
                "confidence": 1.0,
                "speak_first": (
                    "我明白你想找附近好玩的地方，不过我现在还没有本地地点搜索和推荐能力。"
                ),
                "metadata": {
                    "desired_abilities": [
                        {
                            "ability_id": "local.place_recommendation",
                            "intent": "推荐用户附近好玩的地方",
                            "status": "missing_ability",
                            "confidence": 1.0,
                            "reason": "当前能力目录没有本地地点搜索能力。",
                        }
                    ]
                },
            }
        )

        self.assertEqual(
            output.intent,
            "missing_or_unsupported_ability",
        )

    def test_system_prompt_names_goal_interpreter_role_and_context_boundaries(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        prompt = interpreter.load_system_prompt()

        self.assertIn("fast Goal Interpretation model", prompt)
        self.assertNotIn("robot-brain", prompt)
        self.assertIn("Prompt Architecture", prompt)
        self.assertIn("Global Context Group", prompt)
        self.assertIn("Session Context Group", prompt)
        self.assertIn("Current Job", prompt)
        self.assertIn("Task Context", prompt)
        self.assertIn("Output Contract", prompt)
        self.assertLess(prompt.index("Global Context Group"), prompt.index("Current Job"))
        self.assertLess(prompt.index("Current Job"), prompt.index("Task Context"))
        self.assertIn("Generalization-first principle", prompt)
        self.assertIn("Do not replace normal semantic interpretation", prompt)
        self.assertIn("Only deterministic", prompt)
        self.assertIn("emergency/noise controls", prompt)
        self.assertIn("phrase, pattern, regex", prompt)
        self.assertIn("interpret the user turn", prompt)
        self.assertIn("bounded semantic lanes", prompt)
        self.assertIn("cognitive evidence", prompt)
        self.assertIn("final plan", prompt)
        self.assertIn("Route Taxonomy", prompt)
        self.assertIn("Responsibility Before Framing", prompt)
        self.assertIn("substantive responsibility", prompt)
        self.assertIn("do not collapse", prompt)
        self.assertIn("trusted external or changing-fact lookup", prompt)
        self.assertIn("Tool And Affordance Proposal", prompt)
        self.assertIn("current external facts", prompt)
        self.assertIn("trusted lookup capability", prompt)
        self.assertIn("do not map a topic keyword", prompt)
        self.assertNotIn("weather lookup uses route=tool", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("complex reasoning", prompt)
        self.assertIn("task-session work", prompt)
        self.assertIn("separately validated", prompt)
        self.assertIn("long-horizon goals", prompt)
        self.assertIn("routes[]", prompt)
        self.assertIn("independent responsibilities", prompt)
        self.assertIn("Uncertainty And Confirmation Acting Rule", prompt)
        self.assertIn("clarification", prompt)
        self.assertIn("weak lexical or", prompt)
        self.assertIn("substitute a", prompt)
        self.assertNotIn("thinking_mode", prompt)
        self.assertIn("Tool And Affordance Proposal", prompt)
        self.assertIn("body/tool affordance", prompt)
        self.assertIn("not a phrase table", prompt)
        self.assertIn("CapabilityAgent", prompt)
        self.assertIn("candidate proposals", prompt)
        self.assertIn("not authoritative grounding", prompt)
        self.assertIn("deep_thought", prompt)
        self.assertIn("robot_action", prompt)
        self.assertIn("ordered actions[]", prompt)
        self.assertIn("confidence", prompt)
        self.assertIn("supplied-memory recall", prompt)
        self.assertIn("durable_with_explicit_consent", prompt)
        self.assertIn("explicit current-turn consent", prompt)
        self.assertIn("Memory writes", prompt)
        self.assertIn("Recall is chat", prompt)
        self.assertNotIn("intent=weather_query", prompt)
        self.assertIn("Catalog entries", prompt)
        self.assertIn("metadata.desired_abilities", prompt)
        self.assertIn("status=missing_ability", prompt)
        self.assertIn("Return one compact JSON object", prompt)
        self.assertIn("Required keys: route, intent, confidence", prompt)
        self.assertIn("direct_to_tts", prompt)
        self.assertIn("full_mind", prompt)
        self.assertIn("human-like", prompt)
        self.assertIn("not like a program", prompt)
        self.assertIn("Never output placeholder intents", prompt)
        self.assertIn("Do not", prompt)
        self.assertIn("chain-of-thought", prompt)
        self.assertIn("progress text", prompt)
        self.assertLess(len(prompt), 5200)


    def test_goal_interpreter_observability_profiles_prompt_and_raw_tool_output(self) -> None:
        interpreter = OllamaGoalInterpreter(
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

        payload = interpreter.build_payload(request)
        system_text, user_text, all_text = _payload_message_texts(payload)
        flags = _prompt_feature_flags(all_text)
        catalog_profile = _catalog_observability_profile(request)
        raw_summary = _raw_interpreter_output_summary(
            '{"route":"tool","intent":"weather_query","confidence":0.9,'
            '"fast_speech":{"text":"好的，我查一下重庆今天的天气。"},'
            '"metadata":{"tool_name":"weather","weather_query":{"location":"重庆","date":"today"}}}'
        )

        self.assertIn("Tool And Affordance Proposal", system_text)
        self.assertIn("今天重庆天气怎么样？", user_text)
        self.assertTrue(flags["has_fast_speech_contract"])
        self.assertTrue(flags["has_tool_route_contract"])
        self.assertTrue(flags["has_external_lookup_guidance"])
        self.assertTrue(flags["has_no_topic_mapping_guidance"])
        self.assertEqual(catalog_profile["common_ability_count"], 1)
        self.assertEqual(raw_summary["raw_route"], "tool")
        self.assertEqual(raw_summary["raw_intent"], "weather_query")
        self.assertTrue(raw_summary["raw_fast_speech_present"])
        self.assertTrue(raw_summary["raw_weather_query_present"])


    def test_interpreter_prompt_semantically_separates_capability_inquiry_from_execution(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        system = interpreter.load_system_prompt()
        self.assertIn("Capability Inquiry And Execution", system)
        self.assertIn("Availability questions stay chat", system)
        self.assertIn("execution requests use robot_action", system)
        self.assertIn("semantic distinction, not a phrase pattern", system)
        self.assertIn("technical discussion about another person", system)
        self.assertIn("Addressedness", system)

    def test_semantic_ignore_requires_inactive_host_engagement_evidence(self) -> None:
        inactive = RouteRequest(
            text="他们之后再把传感器结果合并。",
            context={
                "interaction_engagement": {
                    "gate_enabled": True,
                    "active": False,
                }
            },
        )
        decision = RouteDecision(
            route="ignore",
            intent="ambient_speech",
            confidence=0.91,
            metadata={
                "semantic_addressedness_gate": True,
                "addressedness_speech_act": "ambient_report",
            },
        )
        self.assertTrue(is_allowed_model_ignore(inactive, decision))

        directed = decision.model_copy(
            update={
                "metadata": {
                    "semantic_addressedness_gate": True,
                    "addressedness_speech_act": "question",
                }
            }
        )
        self.assertFalse(is_allowed_model_ignore(inactive, directed))

        active = inactive.model_copy(
            update={
                "context": {
                    "interaction_engagement": {
                        "gate_enabled": True,
                        "active": True,
                    }
                }
            }
        )
        self.assertFalse(is_allowed_model_ignore(active, decision))

    def test_user_prompt_includes_abilities_and_bounded_context(self) -> None:
        interpreter = OllamaGoalInterpreter(
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

        prompt = interpreter.build_user_prompt(request)
        contract_prompt = interpreter.load_system_prompt() + "\n" + prompt

        self.assertIn("Global Context Group", prompt)
        self.assertIn("Fast Goal Interpretation Context", prompt)
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
        self.assertIn("Decide from meaning, bounded context", prompt)
        self.assertIn("deterministic emergency/noise filter", prompt)
        self.assertIn("fast goal-interpretation and lane proposer", prompt)
        self.assertIn("bounded cognitive evidence", prompt)
        self.assertIn("not final goal meaning", prompt)
        self.assertIn("Return calibrated confidence", prompt)
        self.assertIn("fast_speech", prompt)
        self.assertIn("fast_speech acknowledgement", prompt)
        self.assertIn("Common ability IDs", prompt)
        self.assertIn("Common Ability Catalog JSON", prompt)
        self.assertNotIn("not " + "recommendations", prompt)
        self.assertIn("metadata.desired_abilities", prompt)
        self.assertIn("Capability Affordance Proposal", prompt)
        self.assertIn("not authoritative grounding", prompt)
        self.assertIn("compact body/tool affordance interface", prompt)
        self.assertIn("not a phrase table", prompt)
        self.assertIn("One parameterized capability", prompt)
        self.assertIn("CapabilityAgent", prompt)
        self.assertIn("Isolated letters", prompt)
        self.assertIn("low-information ASR fragments", prompt)
        self.assertNotIn("Semantic Examples", prompt)
        self.assertNotIn("no executable blink skill is in the compact skill catalog", prompt)
        self.assertIn("Bounded session, memory, task, and robot/world context JSON", prompt)
        self.assertIn("chromie_default_mind", prompt)
        self.assertIn("Chromie", prompt)
        self.assertIn("6 years old in robot identity terms", prompt)
        self.assertNotIn("Protect humans first.", prompt)
        self.assertNotIn("Become a useful companion robot.", prompt)
        self.assertNotIn("soridormi.walk_velocity", prompt)
        self.assertIn("soridormi.blink_eyes", prompt)
        self.assertIn("count", prompt)
        self.assertIn("required_args", prompt)
        self.assertIn("times", prompt)
        self.assertIn("low_risk_action", prompt)
        self.assertIn("robot_state", prompt)
        self.assertIn("position", prompt)
        self.assertIn("last_task", prompt)
        self.assertIn("authorize side effects", prompt)
        self.assertIn("Speech-only conversation", prompt)
        self.assertIn("Never return interrupt or ignore", prompt)
        self.assertIn("separate focused addressedness stage", prompt)
        self.assertIn("Required keys: route, intent, confidence", prompt)
        self.assertIn("routes[]", prompt)
        self.assertIn("Allowed lanes", contract_prompt)
        self.assertIn("Allowed context_profile", contract_prompt)
        self.assertIn("Omit agents, metadata", prompt)
        self.assertIn("non-executable ability proposals", prompt)
        self.assertIn("\"confidence\":0.0", prompt)
        self.assertIn("chain-of-thought", contract_prompt)
        self.assertIn("progress text", contract_prompt)
        self.assertIn("placeholder intents", contract_prompt)
        self.assertIn("speak_first", prompt)
        self.assertIn("human-like social warmth", prompt)
        self.assertIn("not a program, programme", prompt)
        self.assertIn("Return one compact JSON object", prompt)
        self.assertLess(len(prompt), 5200)

    def test_fast_interpreter_prompt_uses_common_ability_catalog_not_full_catalog(self) -> None:
        interpreter = OllamaGoalInterpreter(
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

        prompt = interpreter.build_user_prompt(request)

        self.assertIn("Common Ability Catalog JSON", prompt)
        self.assertIn("soridormi.blink_eyes", prompt)
        self.assertNotIn("soridormi.motion.calibrate_floor", prompt)

    def test_fast_interpreter_prompt_excludes_locked_common_catalog_entries(self) -> None:
        interpreter = OllamaGoalInterpreter(
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

        prompt = interpreter.build_user_prompt(request)

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
        from agent.app.cognitive_core.goal_interpreter.schema import annotate_default_stage_output

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
        interpreter = OllamaGoalInterpreter(
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
                        "text": "RAW_TRANSCRIPT_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT",
                    }
                ],
                "conversation": {
                    "history": [
                        {
                            "role": "assistant",
                            "text": "RAW_CONVERSATION_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT",
                        }
                    ]
                },
                "session_memory": {
                    "kind": "short_term_session_memory",
                    "conversation_id": "session",
                    "recent_user_request": "RAW_RECENT_USER_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT",
                    "recent_assistant_response": "RAW_RECENT_ASSISTANT_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT",
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

        prompt = interpreter.build_user_prompt(request)

        self.assertIn("Current task: design extracted prompt memory", prompt)
        self.assertNotIn("RAW_TRANSCRIPT_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)
        self.assertNotIn("RAW_CONVERSATION_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)
        self.assertNotIn("RAW_RECENT_USER_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)
        self.assertNotIn("RAW_RECENT_ASSISTANT_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)

    def test_user_and_repair_prompts_include_recent_terminal_goal_projection(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="s1",
            text="So what was the answer?",
            language="en-US",
            context={
                "recent_goal_snapshots": [
                    {
                        "goal_id": "goal-weather-complete",
                        "status": "done",
                        "commitment_state": "completed",
                        "last_user_update": "Check today's weather in Beijing.",
                        "goal": {
                            "goal_id": "goal-weather-complete",
                            "description": "Check today's weather in Beijing.",
                            "object": {
                                "bindings": {
                                    "location": {
                                        "name": "location",
                                        "entity_type": "place",
                                        "value": "Beijing",
                                        "confidence": 1.0,
                                    }
                                }
                            },
                        },
                    }
                ],
                "verified_tool_memory_index": [
                    {
                        "evidence_id": "evidence-weather-complete",
                        "tool_id": "chromie.weather.lookup",
                        "status": "completed",
                        "request_args": {"location": "Beijing", "date": "today"},
                        "age_ms": 1200,
                        "goal_ids": ["goal-weather-complete"],
                    }
                ],
            },
        )

        prompt = interpreter.build_user_prompt(request)
        repair = interpreter.build_semantic_route_repair_payload(
            request,
            RouteDecision(route="chat", intent="clarify", confidence=0.9),
            reason="route_name_intent_mismatch",
        )
        rendered_repair = json.dumps(repair, ensure_ascii=False)

        self.assertIn("Recent Terminal Goal Snapshot JSON", prompt)
        self.assertIn("goal-weather-complete", prompt)
        self.assertIn("goal-weather-complete", rendered_repair)
        self.assertIn("evidence-weather-complete", rendered_repair)
        self.assertIn("Verified completed tool-memory index JSON", rendered_repair)
        self.assertIn("A topical match to a Capability is not itself", rendered_repair)
        self.assertIn("Terminal references do not reopen Goals", prompt)

    def test_intent_review_prompt_uses_semantic_generalization(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        payload = interpreter.build_intent_review_payload(
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
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            review_model="review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        payload = interpreter.build_post_interrupt_review_payload(
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
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Go ahead and sing a song for me.")

        payload = interpreter.build_payload(request)
        relaxed = interpreter.build_payload(request, relaxed_json=True)

        self.assertIs(payload["think"], False)
        self.assertIs(relaxed["think"], False)
        self.assertIsInstance(payload["format"], dict)
        self.assertIsInstance(relaxed["format"], dict)
        self.assertEqual(
            payload["format"]["properties"]["route"]["enum"],
            ["chat", "deep_thought", "robot_action", "tool", "memory", "clarify", "interrupt", "ignore"],
        )
        self.assertEqual(payload["format"]["properties"]["source"]["const"], "llm")
        self.assertEqual(payload["options"]["num_predict"], 512)
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertIn("Go ahead and sing a song for me.", payload["messages"][1]["content"])

    def test_contract_repair_payload_includes_exact_error_without_weakening_memory(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        payload = interpreter.build_contract_repair_payload(
            RouteRequest(text="Remember that my test color is blue."),
            previous_content=(
                '{"route":"memory","memory_update":{"scope":"session",'
                '"retention_days":30}}'
            ),
            validation_error=ValueError(
                "session memory must not carry durable consent fields"
            ),
        )

        system = payload["messages"][0]["content"]
        user = payload["messages"][1]["content"]
        self.assertIn("Contract Repair", system)
        self.assertIn("Do not infer durable-memory consent", system)
        self.assertIn("must omit consent_basis and retention_days", system)
        self.assertIn("retention_days", user)
        self.assertIn("session memory must not carry", user)
        self.assertIsInstance(payload["format"], dict)

    def test_session_memory_contract_repair_can_only_reduce_persistence(self) -> None:
        class MemoryInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(
                self,
                payload: dict,
                *,
                stage: str = "unknown",
            ) -> dict:
                self.stages.append(stage)
                return {
                    "message": {
                        "content": (
                            '{"route":"memory","intent":"remember_session_fact",'
                            '"confidence":1.0,"memory_update":{"operation":"remember",'
                            '"scope":"session","kind":"fact","text":"test color is blue",'
                            '"persistence_policy":"ephemeral",'
                            '"retention_days":30}}'
                        )
                    }
                }

        interpreter = MemoryInterpreter()
        decision = asyncio.run(
            interpreter.route(
                RouteRequest(
                    text="Remember that my test color is blue.",
                    context={"gateway_admission_complete": True},
                )
            )
        )

        self.assertEqual(decision.route, "memory")
        self.assertIsNotNone(decision.memory_update)
        assert decision.memory_update is not None
        self.assertIsNone(decision.memory_update.retention_days)
        self.assertEqual(
            decision.metadata["contract_recovery"],
            {
                "strategy": "remove_durable_fields_from_explicit_session_memory",
                "recovered_paths": ["memory_update.retention_days"],
            },
        )
        self.assertEqual(
            interpreter.stages,
            ["quick_intent", "quick_intent_contract_repair"],
        )

    def test_session_memory_recovery_does_not_weaken_durable_or_forget_contracts(self) -> None:
        durable = {
            "memory_update": {
                "scope": "session",
                "operation": "remember",
                "kind": "fact",
                "text": "blue",
                "persistence_policy": "durable_with_explicit_consent",
                "consent_basis": "explicit_current_turn",
                "retention_days": 30,
            }
        }
        forget = {
            "memory_update": {
                "scope": "session",
                "operation": "forget",
                "kind": "fact",
                "text": "blue",
                "retention_days": 30,
            }
        }

        self.assertEqual(
            OllamaGoalInterpreter._remove_durable_fields_from_session_memory(durable),
            [],
        )
        self.assertEqual(
            OllamaGoalInterpreter._remove_durable_fields_from_session_memory(forget),
            [],
        )

    def test_route_only_json_response_gets_default_llm_confidence(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Go ahead and sing a song for me.")

        decision = interpreter._decision_from_response(
            request,
            {"message": {"content": '{"route":"chat"}'}},
        )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertGreaterEqual(decision.confidence, 0.72)
        self.assertIn("default confidence", decision.reason or "")

    def test_intent_only_weather_capability_uses_tool_route(self) -> None:
        interpreter = OllamaGoalInterpreter(
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

        decision = interpreter._decision_from_response(
            request,
            {"message": {"content": '{"intent":"capability:chromie.weather.lookup","confidence":0.9}'}},
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "capability:chromie.weather.lookup")
        self.assertIn("normalized capability route", decision.reason or "")

    def test_skill_id_route_weather_capability_uses_tool_route(self) -> None:
        interpreter = OllamaGoalInterpreter(
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

        decision = interpreter._decision_from_response(
            request,
            {"message": {"content": '{"route":"chromie.weather.lookup","confidence":0.9}'}},
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "capability:chromie.weather.lookup")
        self.assertIn("normalized capability route", decision.reason or "")

    def test_goal_interpreter_accepts_deep_thought_route(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Let's design the session memory architecture carefully.")

        decision = interpreter._decision_from_response(
            request,
            {"message": {"content": '{"route":"deep_thought","confidence":0.88}'}},
        )

        self.assertEqual(decision.route, "deep_thought")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertNotIn("conversation_agent", decision.agents)
        self.assertIn("speaker_agent", decision.agents)
        self.assertTrue(decision.needs_agent)

    def test_goal_interpreter_accepts_mixed_route_items_and_builds_task_proposals(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Hi, remember I like tea, and think through tomorrow.")

        decision = interpreter._decision_from_response(
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
        self.assertIn("dominant interpretation route", decision.reason or "")
        from agent.app.cognitive_core.goal_interpreter.schema import annotate_pipeline_stage_outputs

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
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Please figure out how to do this unclear task.")
        quick_decision = interpreter._decision_from_response(
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

        handoff = interpreter._low_confidence_deep_thought_decision(request, quick_decision)

        self.assertEqual(handoff.source, "llm")
        self.assertEqual(handoff.route, "deep_thought")
        self.assertEqual(handoff.intent, "deep_thought_low_confidence")
        self.assertEqual(handoff.confidence, 0.42)
        self.assertEqual(handoff.speak_first, "Give me a moment to think about that.")
        self.assertIn("fast goal interpreter confidence", handoff.reason or "")
        self.assertIn("quick_route=robot_action", handoff.reason or "")
        self.assertIn("deepthinking_agent", handoff.agents)
        self.assertEqual(handoff.metadata["task_relation"], "continue_task")
        self.assertEqual(handoff.metadata["target_task_id"], "task-1")
        self.assertTrue(handoff.metadata["thinking_ack_allowed"])
        self.assertEqual(handoff.metadata["thinking_ack_source"], "quick_llm_speak_first")


class InterpreterLlmReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_logged_call_retains_complete_messages_and_raw_output(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="qwen3:4b",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="daily-benchmark-identity-case",
            text="Who are you?",
            language="en-US",
            context={},
        )
        payload = interpreter.build_payload(request)
        raw_output = '{"route":"chat","intent":"identity","confidence":0.9}'
        response = {
            "model": "qwen3:4b",
            "message": {"content": raw_output},
            "done": True,
            "done_reason": "stop",
        }

        with mock.patch.object(
            interpreter,
            "_chat",
            new=mock.AsyncMock(return_value=response),
        ), self.assertLogs(
            "chromie.agent.goal_interpreter.llm", level="INFO"
        ) as logs:
            result = await interpreter._chat_logged(
                payload,
                stage="quick_intent",
                request=request,
            )

        self.assertEqual(result, response)
        evidence_line = next(
            line for line in logs.output if "llm_call_evidence " in line
        )
        record = json.loads(evidence_line.split("llm_call_evidence ", 1)[1])
        self.assertEqual(record["purpose"], "goal_interpreter")
        self.assertEqual(record["stage"], "quick_intent")
        self.assertEqual(record["request"]["messages"], payload["messages"])
        self.assertEqual(record["request"]["format"], payload["format"])
        self.assertEqual(record["response"]["raw_model_output"], raw_output)
        self.assertEqual(
            record["correlations"]["sid"], "daily-benchmark-identity-case"
        )

    async def test_direct_chat_rejects_declared_request_that_cannot_fit(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE": "4.0",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "256",
            },
            clear=False,
        ):
            interpreter = OllamaGoalInterpreter(
                ollama_url="http://example.invalid",
                model="test-model",
                timeout_ms=800,
                confidence_threshold=0.55,
                num_ctx=2048,
                num_predict=1024,
            )

        payload = {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "s" * 1000},
                {"role": "user", "content": "u" * 5000},
            ],
            "options": {"num_ctx": 2048, "num_predict": 1024},
        }
        with mock.patch(
            "agent.app.cognitive_core.goal_interpreter.model_interpreter.httpx.AsyncClient"
        ) as client_class:
            with self.assertRaises(OllamaGenerationError) as raised:
                await interpreter._chat(payload, stage="quick_intent")

        self.assertEqual(raised.exception.failure_class, "prompt_budget_exceeded")
        self.assertFalse(raised.exception.retryable)
        client_class.assert_not_called()

    async def test_direct_chat_rejects_truncated_completion_before_parsing(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
            num_ctx=32768,
            num_predict=512,
        )
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "message": {"content": '{"route":"tool"'},
            "done_reason": "length",
            "prompt_eval_count": 100,
            "eval_count": 512,
        }
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "weather"}],
            "options": {"num_ctx": 32768, "num_predict": 512},
        }

        with mock.patch(
            "agent.app.cognitive_core.goal_interpreter.model_interpreter.httpx.AsyncClient",
            return_value=context,
        ):
            with self.assertRaises(OllamaGenerationError) as raised:
                await interpreter._chat(payload, stage="semantic_route_repair")

        self.assertEqual(raised.exception.failure_class, "output_truncated")
        self.assertFalse(raised.exception.retryable)

    async def test_structured_generate_fallback_preserves_chat_request_contract(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
            num_ctx=8192,
            num_predict=512,
            keep_alive="10m",
        )
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": '{"route":"chat","intent":"greeting","confidence":1.0}',
            "done": True,
            "prompt_eval_count": 100,
            "eval_count": 20,
        }
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client
        schema = SemanticRouteRepairOutput.model_json_schema()
        payload = {
            "model": "test-model",
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": "10m",
            "messages": [
                {"role": "system", "content": "fixed contract"},
                {"role": "user", "content": "current turn"},
            ],
            "options": {
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": 512,
            },
        }

        with mock.patch(
            "agent.app.cognitive_core.goal_interpreter.model_interpreter.httpx.AsyncClient",
            return_value=context,
        ):
            result = await interpreter._structured_generate_from_chat_payload(
                payload,
                stage="semantic_route_repair",
            )

        called_url = http_client.post.await_args.args[0]
        called_payload = http_client.post.await_args.kwargs["json"]
        self.assertEqual(called_url, "http://example.invalid/api/generate")
        self.assertEqual(called_payload["model"], payload["model"])
        self.assertEqual(called_payload["format"], schema)
        self.assertEqual(called_payload["options"], payload["options"])
        self.assertEqual(called_payload["keep_alive"], "10m")
        self.assertEqual(called_payload["system"], "fixed contract")
        self.assertEqual(called_payload["prompt"], "User:\ncurrent turn")
        self.assertEqual(result["message"]["content"], response.json.return_value["response"])

    async def test_route_does_not_translate_budget_failure_into_chat_fallback(self) -> None:
        class BudgetFailureInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict, *, stage: str) -> dict:
                raise OllamaGenerationError(
                    "truncated",
                    failure_class="output_truncated",
                    failure_domain="llm_budget",
                    architecture_attribution="not_evaluated",
                    retryable=False,
                )

        interpreter = BudgetFailureInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        with self.assertRaises(OllamaGenerationError) as raised:
            await interpreter.route(RouteRequest(text="今天北京热不热？", language="zh-CN"))

        self.assertEqual(raised.exception.failure_domain, "llm_budget")
        self.assertEqual(raised.exception.failure_class, "output_truncated")

    async def test_semantic_repair_does_not_turn_budget_failure_into_user_clarification(self) -> None:
        class BudgetFailureInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict, *, stage: str) -> dict:
                raise OllamaGenerationError(
                    "prompt too large",
                    failure_class="prompt_budget_exceeded",
                    failure_domain="llm_budget",
                    architecture_attribution="not_evaluated",
                    retryable=False,
                )

        interpreter = BudgetFailureInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="今天北京热不热？", language="zh-CN")
        decision = RouteDecision(
            route="chat",
            intent="weather_inquiry",
            confidence=0.9,
            language="zh-CN",
            source="llm",
        )

        with self.assertRaises(OllamaGenerationError) as raised:
            await interpreter._repair_semantic_route(
                request,
                decision,
                reason="route_name_intent_mismatch",
            )

        self.assertEqual(raised.exception.failure_class, "prompt_budget_exceeded")

    async def test_inactive_direct_chinese_weather_question_fails_open_on_false_review(self) -> None:
        class WeatherAddressednessInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict) -> dict:
                system = str(payload["messages"][0].get("content") or "")
                if "You classify whether" in system:
                    self.stages.append("addressedness_review")
                    return {
                        "message": {
                            "content": (
                                '{"addressed":false,"speech_act":"question",'
                                '"confidence":0.95}'
                            )
                        }
                    }
                self.stages.append("quick_intent")
                return {
                    "message": {
                        "content": (
                            '{"route":"tool","intent":"weather_query",'
                            '"confidence":0.95,"metadata":{"tool_name":"weather",'
                            '"weather_query":{"location":"北京","date":"today",'
                            '"units":"metric"}}}'
                        )
                    }
                }

        interpreter = WeatherAddressednessInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="今天北京下雨了吗？",
                language="zh-CN",
                context={
                    "interaction_engagement": {
                        "gate_enabled": True,
                        "active": False,
                    },
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "effects": ["external_read", "weather_lookup"],
                            "description": "Retrieve current weather or forecast for a city.",
                        }
                    ],
                },
            )
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "weather_query")
        self.assertTrue(decision.should_speak)
        self.assertEqual(interpreter.stages, ["quick_intent", "addressedness_review"])

    async def test_inactive_direct_english_request_fails_open_on_false_review(self) -> None:
        class FalseRequestInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict) -> dict:
                del payload
                return {
                    "message": {
                        "content": (
                            '{"addressed":false,"speech_act":"request",'
                            '"confidence":0.97}'
                        )
                    }
                }

        interpreter = FalseRequestInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Please remember that my favorite color is blue.",
            context={
                "interaction_engagement": {
                    "gate_enabled": True,
                    "active": False,
                }
            },
        )
        original = RouteDecision(
            route="memory",
            intent="remember_preference",
            confidence=0.94,
        )

        reviewed = await interpreter._review_inactive_addressedness(request, original)

        self.assertIs(reviewed, original)

    async def test_inactive_question_form_fails_open_on_inconsistent_ambient_act(self) -> None:
        class FalseQuestionInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict) -> dict:
                del payload
                return {
                    "message": {
                        "content": (
                            '{"addressed":false,"speech_act":"ambient_report",'
                            '"confidence":0.97}'
                        )
                    }
                }

        interpreter = FalseQuestionInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Are you ready?",
            context={
                "interaction_engagement": {
                    "gate_enabled": True,
                    "active": False,
                }
            },
        )
        original = RouteDecision(route="chat", intent="status_question", confidence=0.91)

        reviewed = await interpreter._review_inactive_addressedness(request, original)

        self.assertIs(reviewed, original)

    async def test_inactive_malformed_addressedness_review_fails_open(self) -> None:
        class MalformedReviewInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict) -> dict:
                del payload
                return {
                    "message": {
                        "content": '{"addressed":false,"confidence":0.99}'
                    }
                }

        interpreter = MalformedReviewInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Please help me.",
            context={
                "interaction_engagement": {
                    "gate_enabled": True,
                    "active": False,
                }
            },
        )
        original = RouteDecision(route="chat", intent="request_help", confidence=0.9)

        reviewed = await interpreter._review_inactive_addressedness(request, original)

        self.assertIs(reviewed, original)

    async def test_inactive_mislabelled_chat_is_reviewed_to_ambient_ignore(self) -> None:
        class AddressednessInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.models: list[str] = []

            async def _chat(self, payload: dict) -> dict:
                self.models.append(payload["model"])
                if "You classify whether" in payload["messages"][0]["content"]:
                    return {
                        "message": {
                            "content": (
                                '{"addressed":false,"speech_act":"ambient_report",'
                                '"confidence":0.95}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"self-description",'
                            '"confidence":0.95}'
                        )
                    }
                }

        interpreter = AddressednessInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="之后融合输出一个，他自己回放训练。",
                language="zh-CN",
                context={
                    "interaction_engagement": {
                        "gate_enabled": True,
                        "active": False,
                    }
                },
            )
        )

        self.assertEqual(decision.route, "ignore")
        self.assertEqual(decision.intent, "ambient_speech")
        self.assertFalse(decision.should_speak)
        self.assertEqual(
            decision.metadata["addressedness_speech_act"],
            "ambient_report",
        )
        self.assertEqual(interpreter.models, ["quick-model", "quick-model"])

    async def test_inactive_contextless_reply_can_still_be_suppressed(self) -> None:
        class ContextlessReplyInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict) -> dict:
                del payload
                return {
                    "message": {
                        "content": (
                            '{"addressed":false,"speech_act":"reply",'
                            '"confidence":0.93}'
                        )
                    }
                }

        interpreter = ContextlessReplyInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Yeah.",
            context={
                "interaction_engagement": {
                    "gate_enabled": True,
                    "active": False,
                }
            },
        )
        original = RouteDecision(route="chat", intent="acknowledge", confidence=0.9)

        reviewed = await interpreter._review_inactive_addressedness(request, original)

        self.assertEqual(reviewed.route, "ignore")
        self.assertEqual(reviewed.intent, "ambient_speech")
        self.assertEqual(reviewed.metadata["addressedness_speech_act"], "reply")

    async def test_inactive_direct_request_preserves_original_action_route(self) -> None:
        class AddressedRequestInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict) -> dict:
                self.assert_payload = payload
                return {
                    "message": {
                        "content": (
                            '{"addressed":true,"speech_act":"request",'
                            '"confidence":0.99}'
                        )
                    }
                }

        interpreter = AddressedRequestInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Chromie, please blink twice.",
            context={
                "interaction_engagement": {
                    "gate_enabled": True,
                    "active": False,
                }
            },
        )
        original = RouteDecision(
            route="robot_action",
            intent="capability:soridormi.blink_eyes",
            confidence=0.93,
        )

        reviewed = await interpreter._review_inactive_addressedness(request, original)

        self.assertIs(reviewed, original)
        self.assertEqual(interpreter.assert_payload["model"], "quick-model")
        self.assertEqual(interpreter.assert_payload["options"]["num_ctx"], 4096)
        self.assertEqual(interpreter.assert_payload["options"]["num_predict"], 32)
        self.assertIn("speech_act", interpreter.assert_payload["format"]["required"])

    async def test_goal_interpreter_returns_low_confidence_raw_for_pipeline_validation(self) -> None:
        class LowConfidenceInterpreter(OllamaGoalInterpreter):
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

        interpreter = LowConfidenceInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        decision = await interpreter.route(RouteRequest(text="Hello, how are you doing?"))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "unknown")
        self.assertEqual(decision.confidence, 0.0)
        self.assertNotEqual(decision.intent, "deep_thought_low_confidence")

    async def test_llm_interrupt_output_reports_interpretation_unavailable(self) -> None:
        class InterruptInterpreter(OllamaGoalInterpreter):
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

        interpreter = InterruptInterpreter(
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

        with self.assertRaisesRegex(InterpretationUnavailableError, 'deterministic-only route interrupt'):
            await interpreter.route(request)

    async def test_deterministic_only_llm_mistake_uses_review_model(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        decision = await interpreter.route(RouteRequest(text="What's your name?"))

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "identity_question")
        self.assertIn("deterministic-only route interrupt", decision.reason or "")
        self.assertEqual([payload["model"] for payload in interpreter.payloads], ["test-model", "review-model"])

    async def test_slow_review_recovery_can_be_disabled_for_realtime_latency(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        with self.assertRaisesRegex(InterpretationUnavailableError, 'slow repair disabled'):
            await interpreter.route(RouteRequest(text="What's your name?"))
        self.assertEqual([payload["model"] for payload in interpreter.payloads], ["test-model"])

    async def test_review_model_can_recover_invalid_interrupt_to_robot_action(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        decision = await interpreter.route(
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
        self.assertEqual([payload["model"] for payload in interpreter.payloads], ["test-model", "review-model"])

    async def test_review_model_repairs_walk_command_misclassified_as_interrupt(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
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

        decision = await interpreter.route(request)
        review_user = interpreter.payloads[1]["messages"][1]["content"]

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "robot_action")
        self.assertIn("review_model:review-model recovered", decision.reason or "")
        self.assertIn("soridormi.walk_forward", review_user)
        self.assertNotIn("input_schema", review_user)

    async def test_review_failure_does_not_recover_invalid_interrupt_from_catalog_candidate(self) -> None:
        class ReviewFailureInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewFailureInterpreter()
        with self.assertRaisesRegex(InterpretationUnavailableError, 'deterministic-only route interrupt'):
            await interpreter.route(
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

    async def test_fast_repair_model_recovers_when_review_model_fails(self) -> None:
        class RepairInterpreter(OllamaGoalInterpreter):
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

        interpreter = RepairInterpreter()
        decision = await interpreter.route(
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
            [payload["model"] for payload in interpreter.payloads],
            ["test-model", "review-model", "test-model"],
        )

    async def test_review_model_recovers_primary_interpreter_timeout(self) -> None:
        class TimeoutInterpreter(OllamaGoalInterpreter):
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

        interpreter = TimeoutInterpreter()
        decision = await interpreter.route(
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
            [payload["model"] for payload in interpreter.payloads],
            ["test-model", "review-model"],
        )

    async def test_fast_repair_model_runs_after_low_confidence_review_recovery(self) -> None:
        class RepairInterpreter(OllamaGoalInterpreter):
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

        interpreter = RepairInterpreter()
        decision = await interpreter.route(
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
            [payload["model"] for payload in interpreter.payloads],
            ["test-model", "review-model", "test-model"],
        )

    async def test_review_model_overrides_underspecified_robot_action(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        request = RouteRequest(text="Go ahead and sing a song for me.")

        decision = await interpreter.route(request)

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertIn("intent-only route JSON", decision.reason or "")
        self.assertIn("review_model:review-model", decision.reason or "")
        self.assertEqual([payload["model"] for payload in interpreter.payloads], ["test-model", "review-model"])
        self.assertTrue(all(payload["think"] is False for payload in interpreter.payloads))

    async def test_review_model_completes_underspecified_robot_action_with_exact_skill(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
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

        decision = await interpreter.route(request)
        review_user = interpreter.payloads[1]["messages"][1]["content"]

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("selected exact skill for underspecified robot_action", decision.reason or "")
        self.assertIn("soridormi.walk_forward", review_user)
        self.assertEqual([payload["model"] for payload in interpreter.payloads], ["test-model", "review-model"])

    async def test_review_model_skill_id_route_is_normalized_to_robot_action(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        decision = await interpreter.route(
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
        self.assertEqual([payload["model"] for payload in interpreter.payloads], ["test-model", "review-model"])

    async def test_ambiguous_deep_thought_tries_review_then_clarifies(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        decision = await interpreter.route(
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

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "clarify")
        self.assertEqual(decision.intent, "clarify_uncertain_request")
        self.assertIn("semantically unresolved", decision.reason or "")
        self.assertEqual(
            [payload["model"] for payload in interpreter.payloads],
            ["test-model", "review-model", "review-model"],
        )

    async def test_ambiguous_deep_thought_review_recovers_chinese_walk_command(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        decision = await interpreter.route(
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
        review_prompt = interpreter.payloads[1]["messages"][1]["content"]
        self.assertIn("往前走个15秒", review_prompt)
        self.assertIn("soridormi.walk_forward", review_prompt)

    async def test_ambiguous_deep_thought_review_failure_clarifies(self) -> None:
        class ReviewInterpreter(OllamaGoalInterpreter):
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

        interpreter = ReviewInterpreter()
        decision = await interpreter.route(RouteRequest(text="Hello, how are you."))

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "clarify")
        self.assertEqual(decision.intent, "clarify_uncertain_request")
        self.assertIn("semantic repair failed", decision.reason or "")

    async def test_placeholder_capability_intent_is_repaired_before_agent(self) -> None:
        class PlaceholderInterpreter(OllamaGoalInterpreter):
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

        interpreter = PlaceholderInterpreter()
        decision = await interpreter.route(
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
        self.assertEqual(len(interpreter.payloads), 2)

    async def test_placeholder_capability_repair_failure_reports_unavailable(self) -> None:
        class PlaceholderInterpreter(OllamaGoalInterpreter):
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

        interpreter = PlaceholderInterpreter()
        with self.assertRaisesRegex(InterpretationUnavailableError, 'placeholder capability intent'):
            await interpreter.route(RouteRequest(text="Hello, how are you."))

    async def test_tool_route_missing_fast_speech_is_repaired_and_reviewed(self) -> None:
        class WeatherInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                    pending_work_fast_speech_repair_enabled=True,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict) -> dict:
                system = str(payload["messages"][0].get("content") or "")
                if "independent fast-speech semantic and style reviewer" in system:
                    stage = "fast_speech_semantic_review"
                elif "fast-speech repairer" in system:
                    stage = "fast_speech_repair"
                else:
                    stage = "primary_interpreter"
                self.stages.append(stage)
                if stage in {"fast_speech_repair", "fast_speech_semantic_review"}:
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"好的，我查一下重庆今天的天气。",'
                                '"purpose":"acknowledge_and_check",'
                                '"commitment":"checking_only",'
                                '"claim_state":"none",'
                                '"claimed_capability_ids":[],'
                                '"claimed_goal_ids":[],'
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

        interpreter = WeatherInterpreter()
        decision = await interpreter.route(
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
        assert decision.fast_speech is not None
        self.assertEqual(decision.fast_speech.text, "好的，我查一下重庆今天的天气。")
        self.assertEqual(decision.fast_speech.purpose, "acknowledge_and_check")
        self.assertEqual(decision.fast_speech.commitment, "checking_only")
        self.assertTrue(decision.fast_speech.must_not_claim_completion)
        self.assertTrue(decision.metadata["fast_speech_review"]["model_reviewed"])
        self.assertTrue(decision.metadata["fast_speech_review"]["speech_selected"])
        self.assertEqual(
            interpreter.stages,
            [
                "primary_interpreter",
                "fast_speech_repair",
                "fast_speech_semantic_review",
            ],
        )

    async def test_robot_action_fast_speech_repair_stays_generic_before_planning(self) -> None:
        class RobotInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                    pending_work_fast_speech_repair_enabled=True,
                )
                self.payloads: list[dict] = []

            async def _chat(self, payload: dict) -> dict:
                self.payloads.append(payload)
                system = str(payload["messages"][0].get("content") or "")
                if "independent fast-speech semantic and style reviewer" in system:
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"嗯，我想想怎么帮你。",'
                                '"purpose":"acknowledge",'
                                '"commitment":"prelude_only",'
                                '"claim_state":"none",'
                                '"claimed_capability_ids":[],'
                                '"claimed_goal_ids":[],'
                                '"must_not_claim_completion":true}}'
                            )
                        }
                    }
                if "fast-speech repairer" in system:
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"我这就去确认路径安全，然后帮你拿水。",'
                                '"purpose":"acknowledge",'
                                '"commitment":"prelude_only",'
                                '"claim_state":"none",'
                                '"claimed_capability_ids":[],'
                                '"claimed_goal_ids":[],'
                                '"must_not_claim_completion":true}}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action",'
                            '"intent":"capability:soridormi.walk_forward",'
                            '"confidence":0.95}'
                        )
                    }
                }

        interpreter = RobotInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="你能往前跑50米，帮我拿杯水，然后回来吗？",
                language="zh-CN",
            )
        )

        self.assertEqual(decision.route, "robot_action")
        self.assertIsNotNone(decision.fast_speech)
        assert decision.fast_speech is not None
        self.assertEqual(decision.fast_speech.text, "嗯，我想想怎么帮你。")
        self.assertEqual(decision.fast_speech.purpose, "acknowledge")
        self.assertEqual(decision.fast_speech.commitment, "prelude_only")
        repair_rendered = "\n".join(
            str(message.get("content") or "")
            for message in interpreter.payloads[1]["messages"]
        )
        review_rendered = "\n".join(
            str(message.get("content") or "")
            for message in interpreter.payloads[2]["messages"]
        )
        self.assertIn("Identity and personality shape voice only", repair_rendered)
        self.assertIn("Do not use a universal or canned acknowledgement", repair_rendered)
        self.assertIn("do not return null", repair_rendered)
        self.assertIn("claim_state=none", repair_rendered)
        self.assertIn("Review meaning, not keywords", review_rendered)
        self.assertIn("Preserve the valid acknowledgement", review_rendered)
        self.assertIn("the body action definitely has not started", review_rendered)
        self.assertIn("ordinary sentence meaning", review_rendered)
        self.assertIn("rewrite it prospectively", review_rendered)
        self.assertEqual(len(interpreter.payloads), 3)

    async def test_memory_fast_speech_review_keeps_commit_prospective(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        decision = RouteDecision(
            route="memory",
            intent="memory_update",
            confidence=0.95,
        )
        candidate = FastSpeech(
            text="Okay, I remember it now.",
            purpose="acknowledge",
            commitment="prelude_only",
            claim_state="none",
            claimed_capability_ids=[],
            claimed_goal_ids=[],
            must_not_claim_completion=True,
        )

        payload = interpreter.build_fast_speech_review_payload(
            RouteRequest(
                text="Remember that my test color is blue.",
                language="en-US",
            ),
            decision,
            candidate,
        )
        rendered = "\n".join(
            str(message.get("content") or "") for message in payload["messages"]
        )

        self.assertIn("memory update has not been committed", rendered)
        self.assertIn(
            "explicitly prospective or intentional grammatical construction",
            rendered,
        )
        self.assertIn(
            "already remembered, noted, recorded, stored, saved, or updated",
            rendered,
        )
        self.assertIn("rewrite them prospectively", rendered)
        self.assertEqual(payload["model"], "test-model")

    async def test_fast_speech_review_receives_advisory_ability_semantics(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        decision = RouteDecision(
            route="robot_action",
            intent="capability:soridormi.walk_forward",
            confidence=0.95,
        )
        candidate = FastSpeech(
            text="I'll pick up the red mug and bring it to you.",
            purpose="acknowledge",
            commitment="prelude_only",
            claim_state="none",
            claimed_capability_ids=[],
            claimed_goal_ids=[],
            must_not_claim_completion=True,
        )

        payload = interpreter.build_fast_speech_review_payload(
            RouteRequest(
                text="Pick up the red mug and bring it to me.",
                language="en-US",
                context={
                    "common_ability_catalog": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "route": "robot_action",
                            "description": "Walk forward for a bounded duration.",
                            "effects": ["locomotion"],
                        }
                    ]
                },
            ),
            decision,
            candidate,
        )
        rendered = "\n".join(
            str(message.get("content") or "") for message in payload["messages"]
        )

        self.assertIn("advisory pre-association hypothesis", rendered)
        self.assertIn("do not promise that outcome or a method", rendered)
        self.assertIn("soridormi.walk_forward", rendered)
        self.assertIn("Walk forward for a bounded duration", rendered)

    async def test_memory_fast_speech_fails_closed_until_commit(self) -> None:
        class MemoryInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                    pending_work_fast_speech_repair_enabled=True,
                )
                self.stages: list[str] = []

            async def _chat(
                self,
                payload: dict,
                *,
                stage: str = "unknown",
            ) -> dict:
                self.stages.append(stage)
                return {
                    "message": {
                        "content": (
                            '{"route":"memory","intent":"memory_update",'
                            '"confidence":1.0,"memory_update":{"operation":"remember",'
                            '"scope":"session","kind":"fact","text":"blue",'
                            '"persistence_policy":"ephemeral"},'
                            '"fast_speech":{"text":"Okay, I remembered it.",'
                            '"purpose":"acknowledge","commitment":"prelude_only",'
                            '"claim_state":"none","claimed_capability_ids":[],'
                            '"claimed_goal_ids":[],"must_not_claim_completion":true}}'
                        )
                    }
                }

        interpreter = MemoryInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="Remember that my test color is blue.",
                context={"gateway_admission_complete": True},
            )
        )

        self.assertIsNone(decision.fast_speech)
        self.assertEqual(interpreter.stages, ["quick_intent"])
        self.assertEqual(
            decision.metadata["fast_speech_review"],
            {
                "stage": "memory_preeffect_suppressed",
                "model_reviewed": False,
                "speech_selected": False,
                "policy": "memory_commit_required_before_speech",
            },
        )
        self.assertIn("authoritative result response required", decision.reason or "")

    async def test_fast_speech_review_failure_suppresses_dynamic_candidate(self) -> None:
        class RobotInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                    pending_work_fast_speech_repair_enabled=True,
                )

            async def _chat(self, payload: dict) -> dict:
                system = str(payload["messages"][0].get("content") or "")
                if "independent fast-speech semantic and style reviewer" in system:
                    return {"message": {"content": '{"fast_speech":null}'}}
                if "fast-speech repairer" in system:
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"嗯。",'
                                '"purpose":"acknowledge",'
                                '"commitment":"prelude_only",'
                                '"claim_state":"none",'
                                '"claimed_capability_ids":[],'
                                '"claimed_goal_ids":[],'
                                '"must_not_claim_completion":true}}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action",'
                            '"intent":"capability:soridormi.walk_forward",'
                            '"confidence":0.95}'
                        )
                    }
                }

        decision = await RobotInterpreter().route(
            RouteRequest(text="往前走。", language="zh-CN")
        )

        self.assertIsNone(decision.fast_speech)
        self.assertFalse(decision.metadata["fast_speech_review"]["speech_selected"])
        self.assertTrue(
            decision.metadata["fast_speech_review"][
                "fail_closed_to_cached_fallback"
            ]
        )

    async def test_tool_route_missing_fast_speech_does_not_add_interpreter_latency_by_default(self) -> None:
        class WeatherInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.calls = 0

            async def _chat(self, payload: dict) -> dict:
                self.calls += 1
                return {
                    "message": {
                        "content": (
                            '{"route":"tool","intent":"weather_query","confidence":0.95,'
                            '"metadata":{"tool_name":"weather",'
                            '"weather_query":{"location":"重庆","date":"today","units":"metric"}}}'
                        )
                    }
                }

        interpreter = WeatherInterpreter()
        decision = await interpreter.route(
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
        self.assertIsNone(decision.fast_speech)
        self.assertEqual(interpreter.calls, 1)

    async def test_tool_route_existing_fast_speech_is_semantically_reviewed(self) -> None:
        class WeatherInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="test-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                self.stages.append(stage)
                if stage == "fast_speech_semantic_review":
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"好呀，我只帮你查重庆今天的天气。",'
                                '"purpose":"acknowledge_and_check",'
                                '"commitment":"checking_only",'
                                '"claim_state":"none",'
                                '"claimed_capability_ids":[],'
                                '"claimed_goal_ids":[],'
                                '"must_not_claim_completion":true}}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"tool","intent":"weather_query","confidence":0.95,'
                            '"fast_speech":{"text":"今天应该挺暖和，我先去厨房看看有没有热汤。",'
                            '"purpose":"acknowledge_and_check","commitment":"checking_only",'
                            '"claim_state":"none","claimed_capability_ids":[],'
                            '"claimed_goal_ids":[],"must_not_claim_completion":true},'
                            '"metadata":{"tool_name":"weather",'
                            '"weather_query":{"location":"重庆","date":"today","units":"metric"}}}'
                        )
                    }
                }

        interpreter = WeatherInterpreter()
        decision = await interpreter.route(RouteRequest(text="今天重庆天气怎么样？", language="zh-CN"))

        self.assertEqual(decision.route, "tool")
        self.assertIsNotNone(decision.fast_speech)
        assert decision.fast_speech is not None
        self.assertEqual(
            decision.fast_speech.text,
            "好呀，我只帮你查重庆今天的天气。",
        )
        self.assertEqual(
            interpreter.stages,
            ["quick_intent", "fast_speech_semantic_review"],
        )


    async def test_exact_capability_with_fast_model_hint_skips_quality_intent_review(self) -> None:
        class ExactHintInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="quality-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                    pending_work_fast_speech_repair_enabled=True,
                )
                self.calls: list[tuple[str, str]] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                self.calls.append((stage, str(payload.get("model") or "")))
                if stage == "fast_speech_repair":
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"好呀，我先准备一下。",'
                                '"purpose":"acknowledge","commitment":"prelude_only",'
                                '"claim_state":"none","claimed_capability_ids":[],'
                                '"claimed_goal_ids":[],"must_not_claim_completion":true}}'
                            )
                        }
                    }
                if stage == "fast_speech_semantic_review":
                    return {
                        "message": {
                            "content": (
                                '{"fast_speech":{"text":"好呀，我先准备一下。",'
                                '"purpose":"acknowledge","commitment":"prelude_only",'
                                '"claim_state":"none","claimed_capability_ids":[],'
                                '"claimed_goal_ids":[],"must_not_claim_completion":true}}'
                            )
                        }
                    }
                if stage == "intent_review":
                    self.fail("an exact catalog capability must not require quality-model intent review")
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action",'
                            '"intent":"soridormi.walk_forward|speed=quick",'
                            '"confidence":0.95}'
                        )
                    }
                }

        interpreter = ExactHintInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="快点往前走。",
                language="zh-CN",
                context={
                    "gateway_admission_complete": True,
                    "common_ability_catalog": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "route": "robot_action",
                            "available": True,
                            "interaction_executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertEqual(
            decision.metadata["non_authoritative_capability_intent_hint"],
            "speed=quick",
        )
        self.assertIsNotNone(decision.fast_speech)
        self.assertNotIn("intent_review", [stage for stage, _ in interpreter.calls])
        stage_models = dict(interpreter.calls)
        self.assertEqual(stage_models["fast_speech_repair"], "quick-model")
        self.assertEqual(
            stage_models["fast_speech_semantic_review"],
            "quick-model",
        )

    def test_fast_speech_repair_payload_preserves_route_and_forbids_results(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="quality-model",
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

        payload = interpreter.build_fast_speech_repair_payload(request, decision)
        rendered = "\n".join(str(message.get("content") or "") for message in payload["messages"])

        self.assertIn("fast-speech repairer", rendered)
        self.assertIn("six-year-old child", rendered)
        self.assertIn("not customer service", rendered)
        self.assertIn("robot status system", rendered)
        self.assertIn("Do not announce her age or role", rendered)
        self.assertIn("Do not change route", rendered)
        self.assertIn("exact model-authored bindings", rendered)
        self.assertIn("must not semantically claim", rendered)
        self.assertIn("Goal Association and planning have not happened yet", rendered)
        self.assertIn("silence is not valid here", rendered)
        self.assertIn("never phrase matching", rendered)
        self.assertIn("purpose=acknowledge_and_check", rendered)
        self.assertIn("commitment=checking_only", rendered)
        speech_schema = payload["format"]["properties"]["fast_speech"]
        self.assertEqual(
            speech_schema["properties"]["purpose"]["enum"],
            ["acknowledge_and_check"],
        )
        self.assertEqual(speech_schema["properties"]["claim_state"]["const"], "none")
        self.assertEqual(
            speech_schema["properties"]["claimed_capability_ids"]["maxItems"],
            0,
        )
        self.assertEqual(payload["model"], "quick-model")
        self.assertIn("今天重庆天气怎么样", rendered)
        self.assertIn("weather_query", rendered)

    async def test_social_framing_chat_is_rechecked_on_review_model(self) -> None:
        class FramingInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="slow-review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.payloads: list[dict] = []

            async def _chat(self, payload: dict) -> dict:
                self.payloads.append(payload)
                if len(self.payloads) == 1:
                    return {
                        "message": {
                            "content": (
                                '{"route":"chat","intent":"user_question",'
                                '"confidence":0.95}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"tool",'
                            '"intent":"capability:chromie.weather.lookup",'
                            '"confidence":0.96}'
                        )
                    }
                }

        interpreter = FramingInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="你好，今天北京天气热不热？",
                language="zh-CN",
                context={
                    "gateway_admission_complete": True,
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "description": "Retrieve current weather for a place.",
                            "effects": ["external_read", "weather_lookup"],
                            "available": True,
                            "interaction_executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "capability:chromie.weather.lookup")
        self.assertEqual(
            decision.metadata["generic_chat_affordance_review"]["original_intent"],
            "user_question",
        )
        self.assertEqual(
            [payload["model"] for payload in interpreter.payloads],
            ["quick-model", "slow-review-model"],
        )

    def test_material_external_read_correction_review_forbids_relabeling_old_result(
        self,
    ) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="slow-review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="不是重庆，我说的是内乡。",
            language="zh-CN",
            context={
                "recent_goal_snapshots": [
                    {
                        "goal_id": "goal-weather",
                        "status": "completed",
                        "goal": {
                            "description": "Check whether Chongqing is hot.",
                            "object": {
                                "bindings": {
                                    "location": {
                                        "name": "location",
                                        "entity_type": "location",
                                        "value": "重庆",
                                    }
                                }
                            },
                        },
                    }
                ],
                "verified_tool_memory_index": [
                    {
                        "evidence_id": "weather-chongqing",
                        "tool_id": "chromie.weather.lookup",
                        "status": "completed",
                        "request_args": {"location": "重庆"},
                        "goal_ids": ["goal-weather"],
                    }
                ],
                "common_ability_catalog": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "route": "tool",
                        "description": "Retrieve current weather for a place.",
                        "effects": ["external_read", "weather_lookup"],
                        "available": True,
                        "interaction_executable": True,
                    }
                ],
            },
        )

        payload = interpreter.build_semantic_route_repair_payload(
            request,
            RouteDecision(route="chat", intent="correction", confidence=0.95),
            reason="chat_or_social_framing_requires_capability_grounding_review",
        )
        rendered = "\n".join(
            str(message.get("content") or "") for message in payload["messages"]
        )

        self.assertIn(
            "A material binding correction to an external-read Goal requires a "
            "new exact read",
            rendered,
        )
        self.assertIn(
            "Never relabel an older result with the corrected binding",
            rendered,
        )
        self.assertIn("provider canonicalization", rendered)
        self.assertIn("intent=clarify_uncertain_request", rendered)
        self.assertIn(
            "When the user supplies an exact replacement binding",
            interpreter.build_user_prompt(request),
        )

    def test_social_framing_review_keeps_trailing_tool_affordance(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="slow-review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        common_catalog = [
            {
                "capability_id": f"robot.common_{index:02d}",
                "route": "robot_action",
                "description": "Perform one bounded embodied interaction.",
                "available": True,
                "interaction_executable": True,
            }
            for index in range(14)
        ]
        common_catalog.append(
            {
                "capability_id": "chromie.external.lookup",
                "route": "tool",
                "description": "Retrieve a current external fact.",
                "effects": ["read_only", "external_read"],
                "available": True,
                "interaction_executable": True,
            }
        )
        request = RouteRequest(
            text="Hello, could you check the current value for me?",
            language="en",
            context={"common_ability_catalog": common_catalog},
        )

        payload = interpreter.build_semantic_route_repair_payload(
            request,
            RouteDecision(route="chat", intent="greeting", confidence=0.95),
            reason="chat_or_social_framing_requires_capability_grounding_review",
            model="quick-model",
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertIn("robot.common_00", rendered)
        self.assertIn("robot.common_13", rendered)
        self.assertIn("chromie.external.lookup", rendered)

    def test_semantic_repair_preserves_query_matches_and_full_catalog(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="slow-review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Walk forward for fifteen seconds.",
            language="en",
            context={
                "candidate_capabilities": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "route": "robot_action",
                        "description": "Walk forward for a bounded duration.",
                        "available": True,
                        "interaction_executable": True,
                    }
                ],
                "common_ability_catalog": [
                    {
                        "capability_id": "chromie.speak",
                        "route": "chat",
                        "description": "Speak to the user.",
                        "available": True,
                        "interaction_executable": True,
                    }
                ],
                "full_ability_catalog": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "route": "robot_action",
                        "description": "Blink the simulated eyes.",
                        "available": True,
                        "interaction_executable": True,
                    }
                ],
            },
        )

        payload = interpreter.build_semantic_route_repair_payload(
            request,
            RouteDecision(route="chat", intent="general_conversation", confidence=0.95),
            reason="chat_or_social_framing_requires_capability_grounding_review",
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertLess(
            rendered.index("soridormi.walk_forward"),
            rendered.index("chromie.speak"),
        )
        self.assertIn("soridormi.blink_eyes", rendered)

    def test_semantic_repair_preserves_optional_numeric_capability_contract(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="slow-review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="Walk forward for fifteen seconds.",
            language="en",
            context={
                "candidate_capabilities": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "route": "robot_action",
                        "description": "Narrow query match for walking.",
                        "available": True,
                        "interaction_executable": True,
                    }
                ],
                "full_ability_catalog": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "route": "robot_action",
                        "description": "Walk forward for a bounded duration.",
                        "available": True,
                        "interaction_executable": True,
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "speed": {
                                    "type": "string",
                                    "enum": ["slow", "normal", "quick"],
                                    "default": "normal",
                                },
                                "duration_s": {
                                    "type": "number",
                                    "minimum": 0.5,
                                    "maximum": 20.0,
                                    "default": 2.0,
                                },
                            },
                        },
                    }
                ],
            },
        )

        payload = interpreter.build_semantic_route_repair_payload(
            request,
            RouteDecision(route="chat", intent="general_conversation", confidence=0.95),
            reason="chat_or_social_framing_requires_capability_grounding_review",
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertIn(
            "duration_s:number:min=0.5:max=20.0:default=2.0",
            rendered,
        )

    async def test_semantic_repair_retries_schema_incompatible_chat_via_generate(self) -> None:
        class GenerateCompatibleInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict, *, stage: str) -> dict:
                return {"message": {"content": "I can help with that."}}

            async def _structured_generate_from_chat_payload(
                self,
                payload: dict,
                *,
                stage: str,
            ) -> dict:
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action",'
                            '"intent":"capability:soridormi.walk_forward",'
                            '"confidence":0.98,'
                            '"actions":[{"capability_id":"soridormi.walk_forward",'
                            '"args":{"duration_s":15},"sequence":0,'
                            '"timing":"sequential","confidence":0.98}]}'
                        )
                    }
                }

        interpreter = GenerateCompatibleInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="qwen35-chat-schema-incompatible",
            text="Walk forward for fifteen seconds.",
            language="en",
            context={
                "candidate_capabilities": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "route": "robot_action",
                        "description": "Walk forward for a bounded duration.",
                        "available": True,
                        "interaction_executable": True,
                    }
                ]
            },
        )

        reviewed = await interpreter._review_generic_chat_affordance(
            request,
            RouteDecision(
                route="chat",
                intent="general_conversation",
                confidence=0.95,
                source="llm",
            ),
        )

        self.assertEqual(reviewed.route, "robot_action")
        self.assertEqual(reviewed.intent, "capability:soridormi.walk_forward")
        self.assertEqual(
            reviewed.metadata["generic_chat_affordance_review"]["structured_transport"],
            "generate_compatibility_fallback",
        )

    async def test_failed_generic_chat_grounding_review_fails_closed(self) -> None:
        class InvalidReviewInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict, *, stage: str) -> dict:
                return {"message": {"content": "not structured output"}}

            async def _structured_generate_from_chat_payload(
                self,
                payload: dict,
                *,
                stage: str,
            ) -> dict:
                return {"message": {"content": "still not structured output"}}

        interpreter = InvalidReviewInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="invalid-capability-review",
            text="Please do the requested body action.",
            language="en",
            context={
                "candidate_capabilities": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "route": "robot_action",
                        "description": "Walk forward for a bounded duration.",
                        "available": True,
                        "interaction_executable": True,
                    }
                ]
            },
        )

        reviewed = await interpreter._review_generic_chat_affordance(
            request,
            RouteDecision(
                route="chat",
                intent="general_conversation",
                confidence=0.95,
                source="llm",
            ),
        )

        self.assertEqual(reviewed.route, "clarify")
        self.assertEqual(reviewed.intent, "clarify_uncertain_request")
        self.assertTrue(reviewed.metadata["llm_clarification_required"])

    async def test_generic_chat_review_emits_terminal_missing_ability(self) -> None:
        class RestaurantInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="slow-review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.calls = 0

            async def _chat(self, payload: dict) -> dict:
                self.calls += 1
                if self.calls == 1:
                    return {
                        "message": {
                            "content": (
                                '{"route":"chat","intent":"respond_to_user",'
                                '"confidence":0.95}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"clarify",'
                            '"intent":"missing_or_supported_ability",'
                            '"confidence":1.0,'
                            '"speak_first":"我明白你想找附近好吃的餐厅，不过我现在还没有餐厅搜索和推荐能力，所以这次不能给你可靠的推荐。",'
                            '"metadata":{"desired_abilities":[{'
                            '"ability_id":"local.restaurant_recommendation",'
                            '"intent":"查找并推荐用户附近的优质餐厅",'
                            '"status":"missing_ability",'
                            '"confidence":1.0,'
                            '"reason":"当前能力目录没有餐厅搜索或本地商家推荐能力。"}]}}'
                        )
                    }
                }

        interpreter = RestaurantInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="不知道该去什么地方吃饭，附近有啥好吃的？",
                language="zh-CN",
                context={
                    "gateway_admission_complete": True,
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "description": "Retrieve current weather for a place.",
                            "available": True,
                            "interaction_executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(decision.route, "clarify")
        self.assertEqual(decision.intent, "missing_or_unsupported_ability")
        self.assertTrue((decision.speak_first or "").startswith("对不起呀，"))
        self.assertIn("餐厅搜索和推荐能力", decision.speak_first or "")
        self.assertEqual(decision.actions, [])
        self.assertEqual(
            decision.metadata["desired_abilities"][0]["ability_id"],
            "local.restaurant_recommendation",
        )
        proposals = [
            item
            for item in decision.metadata["task_proposals"]
            if item.get("proposal_kind") == "ability"
        ]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["state"], "missing_ability")
        self.assertEqual(interpreter.calls, 2)

    async def test_generic_chat_review_adopts_same_route_intent_correction(self) -> None:
        class IntentCorrectionInterpreter(OllamaGoalInterpreter):
            async def _chat(self, payload: dict) -> dict:
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"user_statement",'
                            '"confidence":1.0}'
                        )
                    }
                }

        interpreter = IntentCorrectionInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="slow-review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="我在重庆两江新区龙兴天街。",
            language="zh-CN",
            context={
                "common_ability_catalog": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "route": "tool",
                        "description": "Retrieve current weather for a place.",
                        "available": True,
                        "interaction_executable": True,
                    }
                ]
            },
        )
        original = RouteDecision(
            route="chat",
            intent="respond_to_greeting",
            confidence=0.95,
            language="zh-CN",
            source="llm",
        )

        reviewed = await interpreter._review_generic_chat_affordance(
            request,
            original,
        )

        self.assertEqual(reviewed.route, "chat")
        self.assertEqual(reviewed.intent, "user_statement")
        self.assertEqual(
            reviewed.metadata["generic_chat_affordance_review"]["status"],
            "intent_corrected",
        )

    def test_semantic_repair_contract_distinguishes_missing_parameter_from_missing_ability(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="quick-model",
            review_model="slow-review-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        payload = interpreter.build_semantic_route_repair_payload(
            RouteRequest(
                text="Recommend a good restaurant nearby.",
                context={
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "description": "Retrieve current weather for a place.",
                        }
                    ]
                },
            ),
            RouteDecision(route="chat", intent="respond_to_user", confidence=0.9),
            reason="chat_or_social_framing_requires_capability_grounding_review",
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertIn("Never substitute the nearest topical Capability", rendered)
        self.assertIn("do not ask for parameters", rendered)
        self.assertIn("missing_or_unsupported_ability", rendered)
        self.assertIn(
            "desired_abilities",
            payload["format"]["$defs"]["SemanticRouteRepairMetadata"]["properties"],
        )
        self.assertIn("speak_first", payload["format"]["properties"])
        self.assertIn("limitation", payload["format"]["properties"])

    async def test_standalone_greeting_remains_chat_after_focused_review(self) -> None:
        class GreetingInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="slow-review-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.calls = 0

            async def _chat(self, payload: dict) -> dict:
                self.calls += 1
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"greeting",'
                            '"confidence":0.96}'
                        )
                    }
                }

        interpreter = GreetingInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="你好！",
                language="zh-CN",
                context={
                    "gateway_admission_complete": True,
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "description": "Retrieve current weather for a place.",
                            "available": True,
                            "interaction_executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "greeting")
        self.assertEqual(interpreter.calls, 2)


if __name__ == "__main__":
    unittest.main()
