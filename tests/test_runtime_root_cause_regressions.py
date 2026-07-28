from __future__ import annotations

import inspect
import unittest
from typing import Any

from agent.app.goal_association import GoalAssociationResolver
from agent.app.planner_contract import canonical_plan_response_schema
from agent.app.response_composer import ResponseComposerResolver
from agent.app.schema import AgentRunRequest
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.outcome_reconciliation import ExecutionOutcomeReconciler
from shared.chromie_contracts.interaction import SkillRequest
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import canonical_plan_fingerprint


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

    def test_courteous_social_attention_needs_concrete_restraint_for_none(self) -> None:
        source = inspect.getsource(ResponseComposerResolver._prompt)
        self.assertIn("positive scene evidence for subtle embodiment", source)
        self.assertIn("is not a concrete restraint", source)
        self.assertIn("not phrase matching or a fixed gesture rule", source)


if __name__ == "__main__":
    unittest.main()
