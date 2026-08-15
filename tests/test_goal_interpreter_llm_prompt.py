from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    _compact_prompt_capabilities,
    _compact_prompt_capability_lines,
    _catalog_observability_profile,
    _payload_message_texts,
    _prompt_feature_flags,
    _raw_interpreter_output_summary,
    _reject_planner_shaped_fast_output,
    is_allowed_model_ignore,
)
from agent.app.cognitive_core.goal_interpreter.fallback import InterpretationUnavailableError
from agent.app.cognitive_core.goal_interpreter.schema import (
    FastResponsibilityProposal,
    RouteDecision,
    RouteRequest,
)


class GoalInterpreterLlmPromptTests(unittest.TestCase):

    def test_fast_responsibility_rejects_planner_owned_bindings(self) -> None:
        with self.assertRaisesRegex(ValueError, "Planner-owned field"):
            FastResponsibilityProposal(
                local_ref="r1",
                outcome="provide today's Chongqing weather",
                bindings={
                    "location": "重庆",
                    "time": "today",
                    "capability_id": "chromie.weather.lookup",
                },
                completion_requires_work=True,
                completion_requires_fresh_evidence=True,
                confidence=0.95,
            )

    def test_fast_responsibility_rejects_activity_contract_bindings(self) -> None:
        with self.assertRaisesRegex(ValueError, "Planner-owned field"):
            FastResponsibilityProposal(
                local_ref="r1",
                outcome="greet Alice",
                bindings={
                    "person": "Alice",
                    "primary_activity": {
                        "activity_id": "activity-greet",
                        "realization": {"vocal_mode": "speech"},
                    },
                },
                completion_requires_work=True,
                confidence=0.95,
            )

    def test_planner_shaped_guard_rejects_activity_work_plan_contracts(self) -> None:
        request = RouteRequest(text="Greet Alice.")
        for field, value in (
            ("routes", []),
            ("activities", [{"summary": "greet Alice"}]),
            ("primary_activity", {"summary": "greet Alice"}),
            ("work_items", [{"summary": "say hello"}]),
            ("plan", {"steps": []}),
            ("execution_lane", "vocal"),
            ("realization", {"vocal_mode": "speech"}),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "downstream-owned contract field"):
                    _reject_planner_shaped_fast_output(
                        request,
                        {
                            "route": "chat",
                            "intent": "greet",
                            "confidence": 0.9,
                            "responsibilities": [],
                            "fast_speech": None,
                            "progress": [],
                            field: value,
                        },
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
        self.assertIn("Prompt Architecture", prompt)
        self.assertIn("Global Context Group", prompt)
        self.assertIn("Session Context Group", prompt)
        self.assertIn("Current Job", prompt)
        self.assertIn("Task Context", prompt)
        self.assertIn("Output Contract", prompt)
        self.assertLess(prompt.index("Global Context Group"), prompt.index("Current Job"))
        self.assertLess(prompt.index("Current Job"), prompt.index("Task Context"))
        self.assertIn("Generalization-first principle", prompt)
        self.assertIn("Responsibility Before Framing", prompt)
        self.assertIn("provider-neutral responsibilities", prompt)
        self.assertIn("Responsibility evidence for downstream cognition", prompt)
        self.assertIn("Fast Planner is the first HOW owner", prompt)
        self.assertIn("Goal Association alone owns canonical Goal continuity", prompt)
        self.assertIn("completion_requires_fresh_evidence", prompt)
        self.assertIn("Ability Awareness, Not Planning", prompt)
        self.assertIn("not a Fast-GI selection or Activity-definition surface", prompt)
        self.assertIn("Exact Work/Activity decomposition and Capability selection are Planner-owned", prompt)
        self.assertIn("Always return fast_speech=null and progress=[]", prompt)
        self.assertIn("Fast Planner receives the authoritative user input plus Responsibility evidence", prompt)
        self.assertIn("Current external facts", prompt)
        self.assertIn("provider-neutral information responsibility", prompt)
        self.assertIn("Uncertainty Boundary", prompt)
        self.assertIn("Capability Inquiry And Execution", prompt)
        self.assertIn("Availability questions stay chat", prompt)
        self.assertIn("Do not output routes[]", prompt)
        self.assertIn("Activity/Work/Plan contracts", prompt)
        self.assertIn("Never author Work, Primary Activities, response wording, Plan steps", prompt)
        self.assertIn("Missing abilities may appear only as non-executable metadata", prompt)
        self.assertIn(
            "return compact JSON with required route, intent, confidence, responsibilities, fast_speech, progress",
            prompt,
        )
        self.assertIn("requires fast_speech=null and progress=[]", prompt)
        self.assertIn("Do not output routes[]", prompt)
        self.assertIn("or intent=capability:<id>", prompt)
        self.assertIn("hidden reasoning", prompt)
        self.assertNotIn("Tool And Affordance Proposal", prompt)
        self.assertNotIn("CapabilityAgent", prompt)
        self.assertNotIn("intent=weather_query", prompt)
        self.assertNotIn("robot-brain", prompt)
        self.assertLess(len(prompt), 6000)


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

        self.assertIn("Ability Awareness, Not Planning", system_text)
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
        self.assertIn("robot_action/tool are compatibility framing only, never Activity/execution contracts", system)
        self.assertIn("Exact Work/Activity decomposition and Capability selection are Planner-owned", system)
        self.assertIn("Generalization-first principle", system)
        self.assertIn("technical discussion about another system", system)
        self.assertIn("Addressedness", system)

    def test_common_capability_projection_exposes_semantic_scope_and_negative_boundary(self) -> None:
        projected = _compact_prompt_capabilities(
            [
                {
                    "capability_id": "chromie.external_information.retrieve",
                    "route": "tool",
                    "description": "Retrieve grounded external information",
                    "effects": ["read_only", "external_read"],
                    "safety_class": "safe_read",
                    "input_schema": {"type": "object", "properties": {}, "required": []},
                    "hints": {
                        "semantic_scope": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kinds": ["information"],
                            "supported_request_kinds": ["fact_lookup", "news"],
                            "domain": "external_information",
                        },
                        "when_not_to_use": (
                            "Do not use for state mutation, reminders, lists, or local device state."
                        ),
                    },
                }
            ]
        )
        self.assertEqual(len(projected), 1)
        self.assertIn("supported_request_kinds=fact_lookup,news", projected[0]["scope"])
        self.assertIn("reminders", projected[0]["not_for"])
        line = _compact_prompt_capability_lines(projected)[0]
        self.assertIn("scope=", line)
        self.assertIn("not_for=", line)

    def test_user_prompt_requires_entailment_not_topical_capability_substitution(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        req = RouteRequest(
            text="Remind me tomorrow to bring my keys.",
            context={
                "prompt_capabilities_common": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "route": "tool",
                        "description": "Lookup weather",
                        "hints": {
                            "semantic_scope": {
                                "responsibility_type": "acquire_and_deliver_resource",
                                "resource_kinds": ["information"],
                                "domain": "weather_forecast",
                            },
                            "when_not_to_use": "Do not use outside weather/forecast questions.",
                        },
                    }
                ]
            },
        )
        prompt = interpreter.build_user_prompt(req)
        self.assertIn("awareness of supported outcome kinds", prompt)
        self.assertIn("never a Fast Goal Interpreter selection or Activity-definition surface", prompt)
        self.assertIn("Topical similarity is not support", prompt)
        self.assertIn("Topical similarity is not support", prompt)
        self.assertIn("Stable reasoning needing no fresh evidence", prompt)
        self.assertIn("Activity/Work/Plan contracts", prompt)
        self.assertIn("never author Work, Primary Activities, response wording, Plan steps", prompt)

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
                        "age_description": "6 years old",
                        "family_role": "the family's secretary",
                    },
                    "personality_expression": {
                        "owner_approved": True,
                        "spoken_style": "Short, natural, age-appropriate family conversation.",
                        "tool_use_style": "Say what you are checking in ordinary words.",
                        "maturity_boundary": "Be a smart six-year-old family secretary, never customer service.",
                    },
                    "core_principles": [{"id": "protect_humans", "statement": "Protect humans first."}],
                    "long_term_goals": [{"id": "useful_companion_robot", "statement": "Become a useful companion robot."}],
                    "owner_approval_required_for_core_changes": True,
                },
                "candidate_capabilities": [
                    {"capability_id": "soridormi.walk_velocity", "interaction_executable": True}
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
        self.assertIn("6 years old", prompt)
        self.assertIn("the family's secretary", prompt)
        self.assertIn("spoken_style", prompt)
        self.assertIn("full owner-approved mind profile", prompt)
        self.assertIn("context_profile", prompt)
        self.assertIn("fast_minimal", prompt)
        self.assertIn("capability_safety", prompt)
        self.assertIn("full_mind", prompt)
        self.assertIn("fast goal-interpretation and responsibility proposer", prompt)
        self.assertIn("Responsibility evidence for downstream cognition", prompt)
        self.assertIn("Fast Planner is the first HOW owner", prompt)
        self.assertIn("never author Work, Primary Activities, response wording, Plan steps", prompt)
        self.assertIn("Ability Awareness, Not Planning", prompt)
        self.assertIn("never a Fast Goal Interpreter selection or Activity-definition surface", prompt)
        self.assertIn("exact HOW belongs to Planner", prompt)
        self.assertIn("Do not output routes[], response wording, Activity/Work/Plan contracts", prompt)
        self.assertIn("exact HOW belongs to Planner", prompt)
        self.assertIn("responsibilities[]", prompt)
        self.assertIn("completion_requires_fresh_evidence", prompt)
        self.assertIn("for a greeting, emit the responsibility to socially reciprocate/acknowledge", prompt)
        self.assertIn("fast_speech=null and progress=[]", prompt)
        self.assertIn("Fast Planner owns the first HOW decision", prompt)
        self.assertIn("Common ability IDs", prompt)
        self.assertIn("Common Ability Catalog JSON", prompt)
        self.assertIn("soridormi.blink_eyes", prompt)
        self.assertNotIn("soridormi.walk_velocity", prompt)
        self.assertIn("count", prompt)
        self.assertIn("required_args", prompt)
        self.assertIn("times", prompt)
        self.assertIn("low_risk_action", prompt)
        self.assertIn("robot_state", prompt)
        self.assertIn("last_task", prompt)
        self.assertIn("Never return interrupt or ignore", prompt)
        self.assertIn(
            "Required keys: route, intent, confidence, responsibilities, fast_speech, progress",
            prompt,
        )
        self.assertIn("Omit agents, metadata, candidate_capabilities", prompt)
        self.assertIn("non-executable semantic metadata", prompt)
        self.assertNotIn("Capability Affordance Proposal", prompt)
        self.assertNotIn("CapabilityAgent", prompt)
        self.assertNotIn("Protect humans first.", prompt)
        self.assertNotIn("Become a useful companion robot.", prompt)
        self.assertIn("hidden reasoning", contract_prompt)
        self.assertIn("does not authorize Goal Interpretation to write a response", contract_prompt)
        self.assertLess(len(prompt), 5800)

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

    def test_user_prompt_uses_bounded_recent_dialogue_and_extracted_memory(self) -> None:
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
        self.assertIn("Recent Accepted Dialogue JSON", prompt)
        self.assertIn("RAW_TRANSCRIPT_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)
        self.assertNotIn("RAW_CONVERSATION_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)
        self.assertNotIn("RAW_RECENT_USER_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)
        self.assertNotIn("RAW_RECENT_ASSISTANT_SHOULD_NOT_REACH_AGENT_GOAL_INTERPRETER_PROMPT", prompt)

    def test_recent_failed_turn_status_is_projected_for_followup_salience(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            sid="s-follow",
            text="那你能找到啥呢？",
            language="zh-CN",
            context={
                "history": [
                    {
                        "role": "user",
                        "sid": "s-restaurants",
                        "text": "我在重庆龙兴天街，帮我找附近好吃的地方。",
                        "metadata": {
                            "semantic_status": "failed",
                            "semantic_failure_stage": "goal_association",
                            "canonical_goal_committed": False,
                        },
                    }
                ],
                "recent_goal_snapshots": [
                    {
                        "goal_id": "goal-older-weather",
                        "status": "done",
                        "goal": {
                            "goal_id": "goal-older-weather",
                            "description": "Check Shanghai weather.",
                            "object": {},
                        },
                    }
                ],
            },
        )

        prompt = interpreter.build_user_prompt(request)

        self.assertIn('"semantic_status":"failed"', prompt)
        self.assertIn('"canonical_goal_committed":false', prompt)
        self.assertIn("重庆龙兴天街", prompt)
        self.assertIn("Keep newer failed/goal-less dialogue salient", prompt)

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
        repair = interpreter.build_contract_repair_payload(
            request,
            previous_content='{"route":"chat"}',
            validation_error=ValueError("missing required confidence"),
        )
        rendered_repair = json.dumps(repair, ensure_ascii=False)

        self.assertIn("Recent Terminal Goal Snapshot JSON", prompt)
        self.assertIn("goal-weather-complete", prompt)
        self.assertIn("goal-weather-complete", rendered_repair)
        self.assertIn("evidence-weather-complete", rendered_repair)
        self.assertIn("verified_tool_memory_index", rendered_repair)
        self.assertIn("Terminal references do not reopen Goals", prompt)


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

    def test_repaired_response_discards_only_invalid_advisory_progress(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="去往前走个100米，帮我拿杯水过来。")
        response = {
            "message": {
                "content": (
                    '{"route":"robot_action","intent":"resource_delivery",'
                    '"confidence":0.95,"fast_speech":"好呀，我来啦！",'
                    '"progress":[{"kind":"native_response",'
                    '"speech_act":"好呀，我来啦！"}]}'
                )
            }
        }

        with self.assertRaises(ValueError):
            interpreter._decision_from_response(request, response)

        decision = interpreter._decision_from_response(
            request,
            response,
            stage="quick_intent_contract_repair",
            allow_bounded_contract_recovery=True,
        )

        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "resource_delivery")
        self.assertEqual(decision.progress, [])
        self.assertEqual(
            decision.metadata["contract_recovery"],
            {
                "strategy": "discard_invalid_advisory_progress",
                "recovered_paths": ["progress[0]"],
            },
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

    def test_intent_only_exact_capability_is_rejected_as_planner_owned(self) -> None:
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

        with self.assertRaisesRegex(ValueError, "Capability selection belongs to Planner"):
            interpreter._decision_from_response(
                request,
                {"message": {"content": '{"intent":"capability:chromie.weather.lookup","confidence":0.9}'}},
            )

    def test_exact_capability_in_route_field_is_rejected_as_planner_owned(self) -> None:
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

        with self.assertRaisesRegex(ValueError, "Capability selection belongs to Planner"):
            interpreter._decision_from_response(
                request,
                {"message": {"content": '{"route":"chromie.weather.lookup","confidence":0.9}'}},
            )

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

    def test_goal_interpreter_rejects_model_authored_route_item_decomposition(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(text="Hi, remember I like tea, and think through tomorrow.")

        with self.assertRaisesRegex(ValueError, "downstream-owned contract field routes"):
            interpreter._decision_from_response(
                request,
                {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"mixed_request","confidence":0.82,'
                            '"responsibilities":[],"fast_speech":null,"progress":[],'
                            '"routes":[{"route":"chat","intent":"greeting"},'
                            '{"route":"memory","intent":"remember_user_preference"},'
                            '{"route":"deep_thought","intent":"plan_tomorrow"}]}'
                        )
                    }
                },
            )



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
                await interpreter._chat(payload, stage="quick_intent")

        self.assertEqual(raised.exception.failure_class, "output_truncated")
        self.assertFalse(raised.exception.retryable)


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
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        with self.assertRaises(OllamaGenerationError) as raised:
            await interpreter.route(RouteRequest(text="今天北京热不热？", language="zh-CN"))

        self.assertEqual(raised.exception.failure_domain, "llm_budget")
        self.assertEqual(raised.exception.failure_class, "output_truncated")


    async def test_inactive_direct_chinese_weather_question_fails_open_on_false_review(self) -> None:
        class WeatherAddressednessInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
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

    async def test_inactive_addressedness_uses_typed_speech_act_not_punctuation(self) -> None:
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

        self.assertEqual(reviewed.route, "ignore")
        self.assertEqual(reviewed.intent, "ambient_speech")

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

        with self.assertRaisesRegex(
            InterpretationUnavailableError, r"deterministic-only route .interrupt."
        ):
            await interpreter.route(request)

















    def test_primary_prompt_hands_conversational_activity_wording_to_fast_planner(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="帮我看看这个问题。",
            language="zh-CN",
            context={"interaction_context": {"already_spoken": [], "pending_speech": []}},
        )

        system_prompt = interpreter.load_system_prompt()
        user_prompt = interpreter.build_user_prompt(request)

        for rendered in (system_prompt, user_prompt):
            self.assertIn("Responsibility", rendered)
            self.assertIn("Fast Planner", rendered)
            self.assertIn("fast_speech=null", rendered)
            self.assertIn("progress=[]", rendered)
        self.assertIn("does not author conversational Activities", system_prompt)
        self.assertIn("Do not decide how to acknowledge, clarify, or respond", user_prompt)
        self.assertIn("Fast Planner owns those Activities", user_prompt)
        self.assertIn("external truth check", user_prompt)
        self.assertIn("before evidence", user_prompt)

    def test_model_facing_schema_forbids_goal_interpreter_speech_authorship(self) -> None:
        schema = OllamaGoalInterpreter._route_response_schema()
        self.assertIn("fast_speech", schema["required"])
        self.assertIn("progress", schema["required"])
        self.assertEqual(schema["properties"]["fast_speech"]["type"], "null")
        self.assertEqual(schema["properties"]["progress"]["type"], "array")
        self.assertEqual(schema["properties"]["progress"]["maxItems"], 0)
        self.assertIn("Fast Planner", schema["properties"]["fast_speech"]["description"])

    def test_model_facing_schema_exposes_responsibility_and_native_progress_boundary(self) -> None:
        schema = OllamaGoalInterpreter._route_response_schema()
        progress = schema["$defs"]["FastProgressProposal"]
        responsibility = schema["$defs"]["FastResponsibilityProposal"]
        self.assertNotIn("RouteItem", schema.get("$defs", {}))
        self.assertNotIn("routes", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

        self.assertEqual(progress["properties"]["kind"]["const"], "native_response")
        self.assertEqual(progress["required"], ["response_text"])
        self.assertEqual(progress["properties"]["response_text"]["minLength"], 1)
        self.assertNotIn("capability_id", progress["properties"])
        self.assertNotIn("args", progress["properties"])
        self.assertEqual(schema["properties"]["progress"]["maxItems"], 0)

        self.assertIn("outcome", responsibility["properties"])
        self.assertIn("bindings", responsibility["properties"])
        self.assertIn("completion_requires_work", responsibility["properties"])
        self.assertIn("completion_requires_fresh_evidence", responsibility["properties"])
        self.assertNotIn("actions", schema["properties"])
        self.assertNotIn("candidate_capabilities", schema["properties"])
        self.assertIn("responsibilities", schema["required"])

    async def test_primary_tool_fast_speech_is_preserved_without_second_llm_call(self) -> None:
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
                return {
                    "message": {
                        "content": (
                            '{"route":"tool","intent":"weather_query","confidence":0.95,'
                            '"fast_speech":"好呀，我看看重庆今天的天气。",'
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
                    "gateway_admission_complete": True,
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
        self.assertIsNotNone(decision.fast_speech)
        assert decision.fast_speech is not None
        self.assertEqual(decision.fast_speech.text, "好呀，我看看重庆今天的天气。")
        self.assertEqual(decision.fast_speech.purpose, "acknowledge_and_check")
        self.assertEqual(decision.fast_speech.commitment, "checking_only")
        self.assertEqual(interpreter.stages, ["quick_intent"])
        self.assertNotIn("fast_speech_review", decision.metadata)

    async def test_primary_silence_is_not_repaired_by_second_llm(self) -> None:
        class SilentInterpreter(OllamaGoalInterpreter):
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
                return {
                    "message": {
                        "content": (
                            '{"route":"deep_thought","intent":"plan_weekend",'
                            '"confidence":0.95,"fast_speech":null}'
                        )
                    }
                }

        interpreter = SilentInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="帮我想一下周末怎么安排。",
                language="zh-CN",
                context={"gateway_admission_complete": True},
            )
        )

        self.assertIsNone(decision.fast_speech)
        self.assertEqual(interpreter.stages, ["quick_intent"])
        self.assertNotIn("fast_speech_review", decision.metadata)

    async def test_exact_capability_output_gets_one_provider_neutral_contract_repair(self) -> None:
        class ExactHintInterpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.calls: list[tuple[str, str]] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                self.calls.append((stage, str(payload.get("model") or "")))
                if stage == "quick_intent":
                    return {
                        "message": {
                            "content": (
                                '{"route":"robot_action",'
                                '"intent":"soridormi.walk_forward|speed=quick",'
                                '"confidence":0.95,'
                                '"responsibilities":[],'
                                '"fast_speech":"好呀，我知道啦。","progress":[]}'
                            )
                        }
                    }
                if stage != "quick_intent_contract_repair":
                    raise AssertionError(f"unexpected stage: {stage}")
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action","intent":"move_forward_quickly",'
                            '"confidence":0.95,'
                            '"responsibilities":[{"local_ref":"r1",'
                            '"outcome":"move forward quickly","bindings":{"speed":"quick"},'
                            '"completion_requires_work":true,'
                            '"completion_requires_fresh_evidence":false,"confidence":0.95}],'
                            '"fast_speech":"好呀，我知道啦。","progress":[]}'
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

        self.assertEqual(decision.intent, "move_forward_quickly")
        self.assertEqual(len(decision.responsibilities), 1)
        self.assertEqual(decision.responsibilities[0].bindings, {"speed": "quick"})
        self.assertIsNotNone(decision.fast_speech)
        self.assertEqual(
            [stage for stage, _ in interpreter.calls],
            ["quick_intent", "quick_intent_contract_repair"],
        )
        self.assertNotIn("non_authoritative_capability_intent_hint", decision.metadata)


    def test_explicit_chat_cannot_be_silently_reclassified_by_exact_capability_work(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="你好，今天重庆天气怎么样？",
            language="zh-CN",
            context={
                "gateway_admission_complete": True,
                "common_ability_catalog": [
                    {
                        "capability_id": "chromie.weather.lookup",
                        "route": "tool",
                        "available": True,
                        "interaction_executable": True,
                    }
                ],
            },
        )
        response = {
            "message": {
                "content": (
                    '{"route":"chat","intent":"chromie.weather.lookup",'
                    '"confidence":0.95,'
                    '"fast_speech":"我刚刚查了天气，今天重庆是多云，温度25度，有点热哦！",'
                    '"progress":[{"kind":"capability",'
                    '"capability_id":"chromie.weather.lookup",'
                    '"args":{"location":"重庆","date":"today"},'
                    '"intent":"weather_lookup","confidence":0.95}]}'
                )
            }
        }

        with self.assertRaisesRegex(
            ValueError,
            "Capability selection belongs to Planner",
        ):
            interpreter._decision_from_response(request, response)

    async def test_weather_planner_shaped_output_gets_one_provider_neutral_repair(self) -> None:
        class WeatherConflictInterpreter(OllamaGoalInterpreter):
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
                if stage == "quick_intent":
                    return {
                        "message": {
                            "content": (
                                '{"route":"chat","intent":"chromie.weather.lookup",'
                                '"confidence":0.95,'
                                '"responsibilities":[],'
                                '"fast_speech":"我刚刚查了天气，今天重庆是多云，温度25度，有点热哦！",'
                                '"progress":[{"kind":"capability",'
                                '"capability_id":"chromie.weather.lookup",'
                                '"args":{"location":"重庆","date":"today"},'
                                '"intent":"weather_lookup","confidence":0.95}]}'
                            )
                        }
                    }
                if stage != "quick_intent_contract_repair":
                    raise AssertionError(f"unexpected stage: {stage}")
                return {
                    "message": {
                        "content": (
                            '{"route":"tool","intent":"weather_lookup","confidence":0.95,'
                            '"responsibilities":[{"local_ref":"r1",'
                            '"outcome":"provide today\u2019s weather for 重庆",'
                            '"bindings":{"location":"重庆","time":"today"},'
                            '"completion_requires_work":true,'
                            '"completion_requires_fresh_evidence":true,"confidence":0.95}],'
                            '"fast_speech":"好呀，我看看重庆今天的天气。","progress":[]}'
                        )
                    }
                }

        interpreter = WeatherConflictInterpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="你好，今天重庆天气怎么样？",
                language="zh-CN",
                context={
                    "gateway_admission_complete": True,
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "available": True,
                            "interaction_executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "weather_lookup")
        self.assertEqual(len(decision.responsibilities), 1)
        responsibility = decision.responsibilities[0]
        self.assertEqual(responsibility.bindings, {"location": "重庆", "time": "today"})
        self.assertTrue(responsibility.completion_requires_fresh_evidence)
        self.assertEqual(decision.progress, [])
        self.assertIsNotNone(decision.fast_speech)
        assert decision.fast_speech is not None
        self.assertEqual(decision.fast_speech.text, "好呀，我看看重庆今天的天气。")
        self.assertNotIn("25度", decision.fast_speech.text)
        self.assertEqual(
            interpreter.stages,
            ["quick_intent", "quick_intent_contract_repair"],
        )
        transaction = decision.metadata["goal_interpreter_transaction"]
        self.assertTrue(transaction["contract_repair_attempted"])
        self.assertFalse(transaction["semantic_repair_attempted"])

    def test_single_lane_native_response_is_the_immediate_speech(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        request = RouteRequest(
            text="你叫什么名字？",
            language="zh-CN",
            context={"gateway_admission_complete": True},
        )
        duplicate = {
            "message": {
                "content": (
                    '{"route":"chat","intent":"identity_question",'
                    '"confidence":0.98,"fast_speech":"我叫 Chromie。",'
                    '"progress":[{"kind":"native_response",'
                    '"response_text":"我叫 Chromie。",'
                    '"speech_act":"answer","confidence":0.98}]}'
                )
            }
        }
        with self.assertRaisesRegex(
            ValueError,
            "native_response is the immediate answer; fast_speech must be null",
        ):
            interpreter._decision_from_response(request, duplicate)

        accepted = interpreter._decision_from_response(
            request,
            {
                "message": {
                    "content": (
                        '{"route":"chat","intent":"identity_question",'
                        '"confidence":0.98,"fast_speech":null,'
                        '"progress":[{"kind":"native_response",'
                        '"response_text":"我叫 Chromie。",'
                        '"speech_act":"answer","confidence":0.98}]}'
                    )
                }
            },
        )
        self.assertIsNone(accepted.fast_speech)
        self.assertEqual(len(accepted.progress), 1)
        self.assertEqual(accepted.progress[0].kind, "native_response")
        self.assertEqual(accepted.progress[0].response_text, "我叫 Chromie。")















if __name__ == "__main__":
    unittest.main()
