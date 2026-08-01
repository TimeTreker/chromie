from __future__ import annotations

import inspect
import unittest

from types import MethodType
from typing import Any

from agent.app.goal_association import GoalAssociationResolver
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.planner_contract import (
    PlannerModelOutput,
    canonical_plan_response_schema,
    fast_multi_goal_response_schema,
    planner_coverage_review_response_schema,
    validate_goal_responsibility_outcomes,
)
from agent.app.response_composer import ResponseComposerResolver
from agent.app.schema import AgentRunRequest
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.outcome_reconciliation import ExecutionOutcomeReconciler
from shared.chromie_contracts.interaction import SkillRequest
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import canonical_plan_fingerprint
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage


class _SequenceOllama:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.schemas: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        del prompt
        self.schemas.append(kwargs["response_format"])
        return self.replies.pop(0)


def _clarify_request() -> AgentRunRequest:
    return AgentRunRequest.model_validate(
        {
            "sid": "clarify-authority",
            "text": "F.",
            "language": "en-US",
            "route_decision": {
                "route": "clarify",
                "intent": "clarify_insufficient_information",
                "agents": ["speaker_agent"],
                "confidence": 0.0,
                "source": "llm",
            },
        }
    )


def _allows_null(node: Any) -> bool:
    if isinstance(node, dict):
        if node.get("type") == "null":
            return True
        return any(_allows_null(value) for value in node.values())
    if isinstance(node, list):
        return any(_allows_null(value) for value in node)
    return False


class RuntimeRootCauseRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_coverage_review_schema_requires_branch_complete_output(self) -> None:
        schema = planner_coverage_review_response_schema()

        self.assertEqual(
            set(schema["required"]),
            {"decision", "confidence", "uncovered_requirements", "reason"},
        )
        branches = schema["allOf"][0]["anyOf"]
        self.assertEqual(
            branches[0]["properties"]["uncovered_requirements"]["maxItems"],
            0,
        )
        self.assertEqual(
            branches[1]["properties"]["uncovered_requirements"]["minItems"],
            1,
        )

    def test_planner_schema_requires_confirmation_for_material_adjustment(self) -> None:
        schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-walk"],
            allowed_skill_ids=["soridormi.walk_forward"],
        )
        relation_constraint = next(
            item
            for item in schema["allOf"]
            if any(
                "plan_relation" in branch.get("properties", {})
                for branch in item.get("anyOf", [])
            )
        )
        exact, adjusted = relation_constraint["anyOf"]

        self.assertEqual(
            exact["properties"]["user_confirmation_required"]["enum"],
            [False],
        )
        self.assertEqual(
            adjusted["properties"]["user_confirmation_required"]["enum"],
            [True],
        )
        self.assertEqual(
            adjusted["properties"]["response_text"]["minLength"], 1
        )

    def test_deep_safety_revision_schema_forbids_exact_sequential_execution(self) -> None:
        base = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-walk", "goal-blink"],
            allowed_skill_ids=[
                "soridormi.walk_forward",
                "soridormi.blink_eyes",
            ],
        )
        feedback = [{"type": "parallel_capability_not_declared_safe"}]
        schema = DeepPlannerResolver._safety_revision_response_schema(
            base,
            feedback=feedback,
        )
        branches = schema["allOf"][-1]["anyOf"]
        adjustment, non_execution = branches

        self.assertEqual(
            adjustment["properties"]["plan_relation"]["enum"],
            ["safe_adjustment", "alternative"],
        )
        self.assertEqual(
            adjustment["properties"]["user_confirmation_required"]["enum"],
            [True],
        )
        self.assertEqual(
            non_execution["properties"]["steps"]["maxItems"], 0
        )
        self.assertEqual(
            schema["$defs"]["PlannerModelStep"]["properties"]["timing"]["enum"],
            ["sequential"],
        )
        self.assertTrue(
            DeepPlannerResolver._requires_safety_revision(feedback)
        )

    def test_deep_safety_revision_is_enforced_after_decoder_output(self) -> None:
        feedback = [{"type": "parallel_capability_not_declared_safe"}]
        exact = CanonicalPlan(
            plan_id="unsafe-exact-revision",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-walk"],
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            metadata={
                "plan_relation": "exact",
                "user_confirmation_required": False,
            },
        )
        adjusted = exact.model_copy(
            update={
                "plan_id": "safe-adjusted-revision",
                "response_text": "I cannot verify overlap safety; may I run the actions sequentially?",
                "metadata": {
                    "plan_relation": "safe_adjustment",
                    "user_confirmation_required": True,
                },
            }
        )
        relabeled_parallel = adjusted.model_copy(
            update={
                "steps": [
                    adjusted.steps[0].model_copy(update={"timing": "parallel"})
                ]
            }
        )

        errors = DeepPlannerResolver._safety_revision_contract_errors(
            exact,
            feedback,
        )

        self.assertEqual(
            errors[0]["type"],
            "safety_revision_contract_not_satisfied",
        )
        self.assertEqual(
            DeepPlannerResolver._safety_revision_contract_errors(
                adjusted,
                feedback,
            ),
            [],
        )
        self.assertEqual(
            DeepPlannerResolver._safety_revision_contract_errors(
                relabeled_parallel,
                feedback,
            )[0]["parallel_step_ids"],
            ["walk"],
        )

    def test_execute_outcome_null_response_normalizes_only_to_semantic_empty(self) -> None:
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "mixed",
                "coverage": "complete",
                "confidence": 1.0,
                "response_text": None,
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15},
                        "source_goal_ids": ["goal-walk"],
                    }
                ],
                "goal_outcomes": {
                    "goal-walk": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": None,
                        "step_ids": ["walk"],
                    },
                    "goal-song": {
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "我给你唱一段。",
                        "step_ids": [],
                    },
                },
                "goal_satisfaction": {"score": 1.0, "status": "exact"},
            }
        )

        self.assertEqual(output.response_text, "")
        self.assertEqual(output.goal_outcomes["goal-walk"].response_text, "")
        self.assertEqual(
            output.goal_outcomes["goal-song"].response_text,
            "我给你唱一段。",
        )

    def test_spoken_goal_schema_and_validator_forbid_executable_ownership(self) -> None:
        for schema in (
            fast_multi_goal_response_schema(
                expected_goal_ids=["goal-walk", "goal-song"],
                allowed_skill_ids=["soridormi.walk_forward"],
                response_goal_ids=["goal-song"],
            ),
            canonical_plan_response_schema(
                planner_tier="deep",
                expected_goal_ids=["goal-walk", "goal-song"],
                allowed_skill_ids=["soridormi.walk_forward"],
                response_goal_ids=["goal-song"],
            ),
        ):
            outcome = schema["properties"]["goal_outcomes"]["properties"][
                "goal-song"
            ]
            self.assertEqual(
                outcome["properties"]["disposition"]["enum"], ["respond"]
            )
            self.assertEqual(outcome["properties"]["step_ids"]["maxItems"], 0)
            self.assertEqual(
                outcome["properties"]["response_text"]["minLength"], 1
            )

        satisfaction = {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": ["goal-song"],
            "unmet_goal_ids": [],
            "unmet_requirements": [],
            "rationale": "The proposed capability would complete the goal.",
        }
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "steps": [
                    {
                        "step_id": "wrong-song-step",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-song"],
                    }
                ],
                "goal_outcomes": {
                    "goal-song": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": ["wrong-song-step"],
                        "satisfaction": satisfaction,
                        "rationale": "Incorrectly assigns motion to speech.",
                    }
                },
                "goal_satisfaction": satisfaction,
            }
        )
        with self.assertRaisesRegex(ValueError, "spoken_response goal must use"):
            validate_goal_responsibility_outcomes(
                output,
                authoritative_goals=[
                    {
                        "goal_id": "goal-song",
                        "metadata": {"responsibility_kind": "spoken_response"},
                    }
                ],
            )

        tool_schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-lookup", "goal-joke"],
            allowed_skill_ids=["chromie.weather.lookup"],
            requires_execution=True,
            response_goal_ids=["goal-joke"],
        )
        self.assertIn("mixed", tool_schema["properties"]["disposition"]["enum"])
        joke_outcome = tool_schema["properties"]["goal_outcomes"]["properties"][
            "goal-joke"
        ]
        self.assertEqual(
            joke_outcome["properties"]["disposition"]["enum"], ["respond"]
        )
        self.assertTrue(joke_outcome["oneOf"])

    async def test_core_clarify_authority_cannot_become_a_new_goal(self) -> None:
        ollama = _SequenceOllama(
            [
                {
                    "decision": "create_goals",
                    "new_goals": [{"description": "Respond naturally to F."}],
                    "clarification": "",
                    "confidence": 1.0,
                    "reason_summary": "Treat the fragment as conversation.",
                },
                {
                    "decision": "clarify",
                    "new_goals": [],
                    "clarification": "What did you mean by F?",
                    "confidence": 0.9,
                    "reason_summary": "The admitted turn is insufficiently clear.",
                },
            ]
        )
        resolution = await GoalAssociationResolver(ollama).resolve(  # type: ignore[arg-type]
            _clarify_request()
        )

        self.assertEqual(resolution.new_goals, [])
        self.assertEqual(resolution.associations, [])
        self.assertEqual(resolution.clarification, "What did you mean by F?")
        self.assertEqual(len(ollama.schemas), 2)
        self.assertEqual(
            ollama.schemas[0]["properties"]["decision"]["enum"],
            ["clarify"],
        )
        self.assertEqual(
            ollama.schemas[0]["properties"]["new_goals"]["maxItems"],
            0,
        )

    def test_single_goal_fast_schema_requires_model_authored_outcome(self) -> None:
        schema = canonical_plan_response_schema(
            planner_tier="fast",
            expected_goal_ids=["goal-weather"],
            allowed_skill_ids=["chromie.weather.lookup"],
        )
        outcomes = schema["properties"]["goal_outcomes"]

        self.assertEqual(outcomes["required"], ["goal-weather"])
        self.assertEqual(outcomes["minProperties"], 1)
        self.assertEqual(outcomes["maxProperties"], 1)
        self.assertFalse(_allows_null(schema["properties"]["goal_satisfaction"]))


    def test_tool_route_planner_schemas_forbid_model_authored_speech(self) -> None:
        fast = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-weather"],
            allowed_skill_ids=["chromie.weather.lookup"],
            requires_execution=True,
        )
        deep = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-weather"],
            allowed_skill_ids=["chromie.weather.lookup"],
            requires_execution=True,
        )

        self.assertEqual(
            fast["properties"]["disposition"]["enum"],
            ["execute", "clarify", "escalate"],
        )
        self.assertEqual(
            fast["properties"]["response_text"]["maxLength"],
            0,
        )
        fast_outcome = fast["properties"]["goal_outcomes"]["properties"]["goal-weather"]
        self.assertEqual(
            fast_outcome["properties"]["disposition"]["enum"],
            ["execute", "clarify", "escalate"],
        )
        self.assertEqual(
            fast_outcome["properties"]["response_text"]["maxLength"],
            0,
        )

        self.assertEqual(
            deep["properties"]["disposition"]["enum"],
            ["execute", "clarify", "unavailable", "refused"],
        )
        self.assertEqual(
            deep["properties"]["response_text"]["maxLength"],
            0,
        )
        deep_outcome = deep["properties"]["goal_outcomes"]["properties"]["goal-weather"]
        self.assertEqual(
            deep_outcome["properties"]["response_text"]["maxLength"],
            0,
        )
        self.assertNotIn(
            ["respond"],
            [
                branch.get("properties", {}).get("disposition", {}).get("enum")
                for branch in deep_outcome.get("oneOf", [])
            ],
        )

    def test_safe_read_response_schema_requires_model_authored_acknowledgement(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-weather-ack",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-weather"],
            goal_summary="Check current weather.",
            steps=[
                {
                    "step_id": "lookup",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "today"},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["lookup"],
                }
            ],
        )
        context = {
            "execution_capabilities": [
                {
                    "skill_id": "chromie.weather.lookup",
                    "safety_class": "safe_read",
                }
            ]
        }
        schema = ResponseComposerResolver._response_schema(plan, context)
        response_plan = schema["$defs"]["ResponsePlan"]

        self.assertIn("immediate", response_plan["required"])
        self.assertEqual(
            response_plan["properties"]["immediate"],
            {"$ref": "#/$defs/ResponseStage"},
        )
        self.assertEqual(
            response_plan["properties"]["pre_action"],
            {"type": "null"},
        )
        with self.assertRaisesRegex(ValueError, "requires one model-authored"):
            ResponseComposerResolver._validate_safe_read_acknowledgement(
                ResponsePlan(),
                plan=plan,
                context=context,
                language="zh-CN",
            )
        ResponseComposerResolver._validate_safe_read_acknowledgement(
            ResponsePlan(
                immediate=ResponseStage(
                    text="我查一下天气预报。",
                    speech_act="acknowledge",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=["goal-weather"],
                )
            ),
            plan=plan,
            context=context,
            language="zh-CN",
        )

    def test_deep_planner_cannot_silently_drop_parallel_timing(self) -> None:
        from agent.app.deep_planner import DeepPlannerResolver

        context = {
            "fast_plan_resolution": {
                "steps": [
                    {
                        "step_id": "walk",
                        "skill_id": "soridormi.walk_forward",
                        "timing": "parallel",
                    },
                    {
                        "step_id": "blink",
                        "skill_id": "soridormi.blink_eyes",
                        "timing": "parallel",
                    },
                ]
            }
        }
        raw = {
            "steps": [
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                },
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                },
            ]
        }
        with self.assertRaisesRegex(ValueError, "omitted timing"):
            DeepPlannerResolver._validate_parallel_timing_preservation(
                raw,
                context=context,
            )

        for step in raw["steps"]:
            step["timing"] = "parallel"
        DeepPlannerResolver._validate_parallel_timing_preservation(
            raw,
            context=context,
        )

    def test_safe_read_parallel_timing_is_exactly_provenanced(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-weather",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-weather"],
            goal_summary="Check the weather.",
            steps=[
                {
                    "step_id": "lookup",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "today"},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["lookup"],
                }
            ],
        )
        fingerprint = canonical_plan_fingerprint(plan)
        request = SkillRequest(
            request_id="weather-request",
            skill_id="chromie.weather.lookup",
            args={"location": "重庆", "date": "today"},
            timing="parallel",
            requires_confirmation=False,
            metadata={
                "source": "goal_driven_canonical_plan",
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "step_id": "lookup",
                "source_goal_ids": ["goal-weather"],
                "safety_class": "safe_read",
                "retryable_safe_read": True,
                "parallel_with_speech": True,
                "canonical_timing": "sequential",
                "effective_timing": "parallel",
                "runtime_timing_adjustment": "safe_read_parallel",
            },
        )

        planned, _, _ = ExecutionOutcomeReconciler._planned_requests(
            plan,
            fingerprint=fingerprint,
            requests=[request],
        )
        self.assertEqual(planned["lookup"].timing, "parallel")

        forged = request.model_copy(
            deep=True,
            update={
                "metadata": {
                    **request.metadata,
                    "runtime_timing_adjustment": "none",
                }
            },
        )
        with self.assertRaisesRegex(ValueError, "timing does not match"):
            ExecutionOutcomeReconciler._planned_requests(
                plan,
                fingerprint=fingerprint,
                requests=[forged],
            )

    def test_wake_up_greeting_rejects_incomplete_clause(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "complete punctuated"):
            VoiceAssistant._validate_runtime_ready_greeting_completion(
                "六点半啦，我困了，你吃晚"
            )
        self.assertEqual(
            VoiceAssistant._validate_runtime_ready_greeting_completion(
                "嗨，我醒啦！"
            ),
            "嗨，我醒啦！",
        )
        with self.assertRaisesRegex(RuntimeError, "introduced the speaker"):
            VoiceAssistant._validate_runtime_ready_greeting_semantics(
                "你好，我是Chromie。"
            )
        with self.assertRaisesRegex(RuntimeError, "speaker age"):
            VoiceAssistant._validate_runtime_ready_greeting_semantics(
                "嗨，我六岁啦！"
            )

    def test_wake_up_prompt_uses_grounded_time_without_unverified_state(self) -> None:
        assistant = object.__new__(VoiceAssistant)
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant._direct_llm_identity_json = lambda: "{}"  # type: ignore[method-assign]
        assistant._direct_llm_mind_summary = lambda: "{}"  # type: ignore[method-assign]
        prompt = assistant._runtime_ready_greeting_prompt()

        self.assertIn("Grounded local temporal context JSON", prompt)
        self.assertIn("local_period", prompt)
        self.assertIn("Do not quote the exact clock time", prompt)
        self.assertIn("Do not invent meals, hunger, sleepiness, weather", prompt)
        self.assertIn("Do not ask a question or end mid-clause", prompt)

    async def test_vad_segment_started_during_playback_keeps_barge_in_threshold(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.target_asr_rate = 16000
        assistant.max_vad_utterance_ms = 20000
        assistant.min_audio_ms = 100
        assistant.min_rms = 120.0
        assistant.barge_in_min_rms = 350.0
        assistant.is_playing_audio = False
        assistant.playback_generation = 2
        created: list[str] = []

        def create_session(self: VoiceAssistant) -> str:
            created.append("created")
            return "unexpected"

        assistant.create_session = MethodType(create_session, assistant)
        audio = int(200).to_bytes(2, "little", signed=True) * 16000

        await assistant.handle_vad_audio(
            audio,
            started_during_playback=True,
            playback_generation_at_start=1,
        )

        self.assertEqual(created, [])


    def test_tts_echo_match_rejects_concatenated_robot_speech(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant._tts_text_by_generation = {
            4: [
                "我会先眨两下眼睛，再往前走15秒。",
                "刚才没成功。",
            ]
        }

        likely, ratio, coverage = assistant._likely_tts_echo(
            "我会先眨两下眼睛，再往前走15秒，刚才没成功。",
            playback_generation_at_start=4,
        )

        self.assertTrue(likely)
        self.assertGreaterEqual(ratio, 0.78)
        self.assertGreaterEqual(coverage, 0.88)

    def test_tts_echo_match_keeps_real_barge_in(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant._tts_text_by_generation = {
            5: ["我会先眨两下眼睛，再往前走15秒。"]
        }

        likely, _, _ = assistant._likely_tts_echo(
            "停一下，我不是让你先眨眼。",
            playback_generation_at_start=5,
        )

        self.assertFalse(likely)

    def test_planner_prompts_preserve_requested_concurrency(self) -> None:
        from agent.app.deep_planner import DeepPlannerResolver
        from agent.app.fast_planner import FastPlannerResolver

        fast_source = inspect.getsource(FastPlannerResolver._prompt)
        deep_source = inspect.getsource(DeepPlannerResolver._prompt)
        for source in (fast_source, deep_source):
            self.assertIn(
                "Never silently rewrite simultaneous independent actions as before/after actions",
                source,
            )
            self.assertIn("timing=parallel", source)
            self.assertIn("Every executable step must explicitly include timing", source)
            self.assertIn("Never satisfy a prohibition", source)

    def test_response_language_validation_rejects_full_english_for_chinese(self) -> None:
        request = AgentRunRequest.model_validate(
            {
                "sid": "language-boundary",
                "text": "今天重庆热不热？",
                "language": "zh-CN",
                "route_decision": {
                    "route": "chat",
                    "intent": "question",
                    "confidence": 0.9,
                    "source": "llm",
                },
            }
        )
        with self.assertRaisesRegex(ValueError, "authoritative Chinese"):
            ResponseComposerResolver._validate_spoken_language(
                ResponsePlan(
                    final=ResponseStage(
                        text="It is about 32 degrees Celsius.",
                    )
                ),
                request=request,
            )

        ResponseComposerResolver._validate_spoken_language(
            ResponsePlan(
                final=ResponseStage(
                    text="重庆现在大约32摄氏度。",
                )
            ),
            request=request,
        )

    def test_deep_tool_schema_inlines_required_goal_outcome_fields(self) -> None:
        schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-weather"],
            allowed_skill_ids=["chromie.weather.lookup"],
            requires_execution=True,
        )
        outcome = schema["properties"]["goal_outcomes"]["properties"][
            "goal-weather"
        ]

        self.assertNotIn("$ref", outcome)
        self.assertEqual(
            set(outcome["required"]),
            {
                "disposition",
                "coverage",
                "response_text",
                "unresolved",
                "step_ids",
                "satisfaction",
                "rationale",
            },
        )
        self.assertNotIn(
            "respond",
            outcome["properties"]["disposition"]["enum"],
        )
        self.assertNotIn(
            "respond",
            schema["properties"]["disposition"]["enum"],
        )
        self.assertFalse(_allows_null(schema["properties"]["goal_satisfaction"]))

    def test_courteous_social_attention_needs_concrete_restraint_for_none(self) -> None:
        source = inspect.getsource(ResponseComposerResolver._prompt)
        self.assertIn("positive scene evidence for subtle embodiment", source)
        self.assertIn("is not a concrete restraint", source)
        self.assertIn("not phrase matching or a fixed gesture rule", source)


if __name__ == "__main__":
    unittest.main()
