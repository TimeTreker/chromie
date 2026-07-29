from __future__ import annotations

import inspect
import unittest

from types import MethodType
from typing import Any

from agent.app.goal_association import GoalAssociationResolver
from agent.app.planner_contract import (
    canonical_plan_response_schema,
    fast_multi_goal_response_schema,
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
            ["execute", "escalate"],
        )
        self.assertEqual(
            fast["properties"]["response_text"]["maxLength"],
            0,
        )
        fast_outcome = fast["properties"]["goal_outcomes"]["properties"]["goal-weather"]
        self.assertEqual(
            fast_outcome["properties"]["disposition"]["enum"],
            ["execute", "escalate"],
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

    def test_wake_up_prompt_has_no_ungrounded_time_or_state_seed(self) -> None:
        assistant = object.__new__(VoiceAssistant)
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant._direct_llm_identity_json = lambda: "{}"  # type: ignore[method-assign]
        assistant._direct_llm_mind_summary = lambda: "{}"  # type: ignore[method-assign]
        prompt = assistant._runtime_ready_greeting_prompt()

        self.assertNotIn("Local time:", prompt)
        self.assertNotIn("Timezone:", prompt)
        self.assertIn("Do not mention clock time", prompt)
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

    def test_nontrivial_return_statement_is_not_a_bare_greeting(self) -> None:
        request = AgentRunRequest.model_validate(
            {
                "sid": "return-statement",
                "text": "I'm back and pet you.",
                "language": "en-US",
                "route_decision": {
                    "route": "chat",
                    "intent": "greeting",
                    "confidence": 0.9,
                    "source": "llm",
                },
            }
        )
        self.assertFalse(
            ResponseComposerResolver._is_bare_greeting_turn(request)
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
