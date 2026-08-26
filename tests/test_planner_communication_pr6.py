from __future__ import annotations

import unittest

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.main import (
    _fast_first_response_context_window,
    _fast_truth_context_window,
    app,
    fast_first_response_client,
    fast_truth_client,
)
from agent.app.settings import GoalInterpreterSettings, Settings
from agent.app.planner_schema import fast_truth_certificate_response_schema
from orchestrator.clients.agent_client import AgentClient
from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator
from shared.chromie_contracts.goal import (
    GoalAssociationResolution,
)
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.plan import (
    FastPlannerAdvance,
    FastPlannerCompleteResponseAct,
    FastPlannerFirstResponseTruthCertificate,
    FastPlannerProgressAct,
)


class PlannerOwnedCommunicativeActivityTests(unittest.TestCase):
    def test_dedicated_response_model_does_not_inherit_deliberative_context(self) -> None:
        service_settings = Settings().model_copy(
            update={
                "fast_planner_model": "qwen3:4b",
                "fast_first_response_model": "gemma4:12b",
                "fast_truth_model": "gemma4:12b",
                "goal_association_model": "gemma4:12b",
                "fast_planner_num_ctx": 32768,
                "goal_association_num_ctx": 32768,
            }
        )
        interpreter_settings = GoalInterpreterSettings().model_copy(
            update={"model": "qwen3:4b", "llm_num_ctx": 32768}
        )

        self.assertEqual(
            _fast_first_response_context_window(
                service_settings,
                interpreter_settings,
            ),
            6144,
        )
        self.assertEqual(
            _fast_truth_context_window(service_settings),
            6144,
        )
        self.assertIs(fast_first_response_client, fast_truth_client)

    def test_fast_response_reuses_fast_runner_when_models_match(self) -> None:
        service_settings = Settings().model_copy(
            update={
                "fast_planner_model": "qwen3:4b",
                "fast_first_response_model": "qwen3:4b",
                "fast_truth_model": "qwen3:4b",
                "goal_association_model": "gemma4:12b",
                "fast_planner_num_ctx": 32768,
                "goal_association_num_ctx": 32768,
            }
        )
        interpreter_settings = GoalInterpreterSettings().model_copy(
            update={"model": "qwen3:4b", "llm_num_ctx": 32768}
        )

        self.assertEqual(
            _fast_first_response_context_window(
                service_settings, interpreter_settings
            ),
            32768,
        )
        self.assertEqual(_fast_truth_context_window(service_settings), 32768)

    def test_qualification_truth_and_first_response_use_full_fast_context(self) -> None:
        service_settings = Settings().model_copy(
            update={
                "cognitive_budget_profile": "qualification",
                "fast_planner_model": "qwen3:4b",
                "fast_first_response_model": "gemma4:12b",
                "fast_truth_model": "gemma4:12b",
                "fast_planner_num_ctx": 32768,
            }
        )
        interpreter_settings = GoalInterpreterSettings().model_copy(
            update={"model": "qwen3:4b", "llm_num_ctx": 32768}
        )

        self.assertEqual(_fast_truth_context_window(service_settings), 32768)
        self.assertEqual(
            _fast_first_response_context_window(
                service_settings,
                interpreter_settings,
            ),
            32768,
        )

    def test_fast_activity_owns_exact_text_and_truth_stage(self) -> None:
        activity = FastPlannerProgressAct(
            activity_id="weather-progress",
            role="progress",
            text="我看看。",
            progress_kind="check_information",
            speech_act="acknowledge_and_check",
            source_responsibility_refs=["weather"],
        )

        self.assertEqual(activity.text, "我看看。")
        self.assertEqual(activity.truth_stage, "pre_evidence")
        self.assertEqual(activity.evidence_refs, [])

    def test_pre_evidence_activity_cannot_claim_evidence_provenance(self) -> None:
        with self.assertRaises(ValidationError):
            FastPlannerProgressAct(
                activity_id="weather-progress",
                role="progress",
                text="我看看。",
                progress_kind="check_information",
                source_responsibility_refs=["weather"],
                evidence_refs=["weather-evidence"],
            )

    def test_truth_certificate_projects_decision_from_complete_flag_vector(self) -> None:
        fields = {
            "has_unverified_result_or_completion_claim": False,
            "has_ungrounded_method_or_world_claim": False,
            "has_semantic_perspective_contradiction": False,
            "has_epistemic_strength_contradiction": False,
            "has_execution_status_contradiction": False,
            "has_out_of_scope_goal_claim": False,
        }

        generic_reject = FastPlannerFirstResponseTruthCertificate.model_validate(
            {**fields, "decision": "reject"}
        )
        contradictory_accept = FastPlannerFirstResponseTruthCertificate.model_validate(
            {
                **fields,
                "has_execution_status_contradiction": True,
                "decision": "accept",
            }
        )

        self.assertEqual(generic_reject.decision, "accept")
        self.assertEqual(contradictory_accept.decision, "reject")

    def test_truth_certificate_requires_every_model_facing_audit_field(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Field required"):
            FastPlannerFirstResponseTruthCertificate.model_validate(
                {"has_execution_status_contradiction": True}
            )

    def test_truth_certificate_decoder_schema_requires_flat_complete_payload(self) -> None:
        schema = fast_truth_certificate_response_schema()
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        fields = {
            "has_unverified_result_or_completion_claim": False,
            "has_ungrounded_method_or_world_claim": False,
            "has_semantic_perspective_contradiction": False,
            "has_epistemic_strength_contradiction": False,
            "has_execution_status_contradiction": False,
            "has_out_of_scope_goal_claim": False,
        }

        self.assertEqual(
            list(validator.iter_errors({**fields, "decision": "accept"})),
            [],
        )
        self.assertEqual(
            list(
                validator.iter_errors(
                    {
                        **fields,
                        "has_execution_status_contradiction": True,
                        "decision": "reject",
                    }
                )
            ),
            [],
        )
        self.assertNotEqual(
            list(
                validator.iter_errors(
                    {"has_execution_status_contradiction": True}
                )
            ),
            [],
        )
        self.assertNotIn("oneOf", schema)
        self.assertNotIn("anyOf", schema)

        # The complete flag vector owns the semantic judgment; the opposite
        # redundant decision is projected after constrained decoding.
        certificate = FastPlannerFirstResponseTruthCertificate.model_validate(
            {
                **fields,
                "has_execution_status_contradiction": True,
                "decision": "accept",
            }
        )
        self.assertEqual(certificate.decision, "reject")

    def test_post_evidence_response_requires_exact_evidence_refs(self) -> None:
        with self.assertRaises(ValidationError):
            FastPlannerCompleteResponseAct(
                activity_id="weather-answer",
                role="complete_response",
                text="上午不会下雨。",
                speech_act="answer",
                truth_stage="post_evidence",
                source_responsibility_refs=["weather"],
            )

    def test_fast_plan_binds_planner_text_into_canonical_activity(self) -> None:
        advance = FastPlannerAdvance(
            turn_id="turn-greeting",
            disposition="respond",
            coverage="complete",
            covered_responsibility_refs=["greeting"],
            activities=[
                FastPlannerCompleteResponseAct(
                    activity_id="greeting-response",
                    role="complete_response",
                    text="你好呀！",
                    speech_act="greeting",
                    source_responsibility_refs=["greeting"],
                )
            ],
            confidence=0.98,
        )
        association = GoalAssociationResolution(
            turn_id="turn-greeting",
            resolution_status="resolved",
            new_goals=[
                SemanticGoal(
                    goal_id="goal-greeting",
                    description="Respond to the greeting.",
                    source_text="你好",
                    source_responsibility_refs=["greeting"],
                )
            ],
            confidence=0.98,
        )

        plan = GoalDrivenRuntimeCoordinator._canonical_plan_from_fast_advance(
            advance=advance,
            association=association,
            user_text="你好",
        )

        self.assertEqual(plan.response_text, "你好呀！")
        self.assertEqual(plan.communicative_acts[0].text, "你好呀！")
        self.assertEqual(plan.communicative_acts[0].source_goal_ids, ["goal-greeting"])

    def test_duplicate_semantic_endpoints_are_removed(self) -> None:
        paths = {route.path for route in app.routes}
        self.assertNotIn("/compose-response-plan", paths)
        self.assertNotIn("/communicative-acts/realize", paths)
        self.assertNotIn("/tool-result/interpret", paths)
        self.assertFalse(hasattr(AgentClient, "compose_response_plan"))
        self.assertFalse(hasattr(AgentClient, "realize_communicative_acts"))
        self.assertFalse(hasattr(AgentClient, "interpret_tool_result"))


if __name__ == "__main__":
    unittest.main()
