from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveEvidenceRecorder,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.skill_runtime import SkillDefinition
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    ResponseCompositionResolution,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage, SemanticGoal
from shared.chromie_contracts.social_attention import SocialAttentionPlan


class FakeRuntime:
    def __init__(self, definitions: list[SkillDefinition] | None = None):
        self.definitions = {item.skill_id: item for item in (definitions or [])}
        self.ensure_calls: list[list[str]] = []

    async def ensure_skill_definitions(self, skill_ids):
        ids = list(skill_ids)
        self.ensure_calls.append(ids)
        missing = [item for item in ids if item not in self.definitions]
        if missing:
            raise ValueError(f"unknown skills: {missing}")

    def skill_definition(self, skill_id):
        if skill_id not in self.definitions:
            raise ValueError(f"unknown skill {skill_id}")
        return self.definitions[skill_id]


class ScriptedClient:
    def __init__(
        self,
        *,
        association: GoalAssociationResolution,
        fast_plans: list[CanonicalPlan],
        deep_plans: list[CanonicalPlan] | None = None,
        composition_status: str = "resolved",
    ):
        self.association = association
        self.fast_plans = list(fast_plans)
        self.deep_plans = list(deep_plans or [])
        self.composition_status = composition_status
        self.deep_contexts: list[dict] = []
        self.calls: list[str] = []

    async def resolve_goal_association(self, *args, **kwargs):
        self.calls.append("association")
        return self.association

    async def resolve_fast_plan(self, *args, **kwargs):
        self.calls.append("fast")
        return self.fast_plans.pop(0)

    async def resolve_deep_plan(self, *args, **kwargs):
        self.calls.append("deep")
        self.deep_contexts.append(dict(kwargs.get("context") or {}))
        return self.deep_plans.pop(0)

    async def compose_response_plan(self, *args, **kwargs):
        self.calls.append("compose")
        if self.composition_status != "resolved":
            return ResponseCompositionResolution(
                status="model_unavailable",
                reason_summary="composer unavailable",
            )
        plan = CanonicalPlan.model_validate(
            kwargs["context"]["canonical_plan_resolution"]
        )
        if plan.disposition == "execute":
            response_plan = ResponsePlan(
                pre_action=ResponseStage(
                    text="好的，我先执行这个计划。",
                    speech_act="inform",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            )
        elif plan.disposition == "mixed":
            response_texts = [
                item.response_text
                for item in plan.goal_outcomes
                if item.disposition == "respond" and item.response_text
            ]
            response_plan = ResponsePlan(
                pre_action=ResponseStage(
                    text=(
                        "I will carry out the requested action. "
                        + " ".join(response_texts)
                    ).strip(),
                    speech_act="inform",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            )
        elif plan.disposition == "clarify":
            response_plan = ResponsePlan(
                immediate=ResponseStage(
                    text=plan.response_text or "请补充必要信息。",
                    speech_act="clarify",
                    commitment_state="waiting_for_user",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            )
        else:
            response_plan = ResponsePlan(
                final=ResponseStage(
                    text=plan.response_text or "你好。",
                    speech_act="inform",
                    commitment_state="none",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            )
        composition = CoordinatedResponsePlan(
            composition_id=f"composition-{plan.plan_id}",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=response_plan,
            confidence=0.91,
        )
        return ResponseCompositionResolution(
            status="resolved",
            composition=composition,
        )


def new_goal_association(goal_id: str = "goal-1") -> GoalAssociationResolution:
    return GoalAssociationResolution(
        turn_id="turn-1",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                description="Respond to the user.",
                source_text="hello",
            )
        ],
        confidence=0.95,
        reason_summary="A new independent user goal.",
        metadata={"status": "resolved"},
    )


def multi_goal_association(*goal_ids: str) -> GoalAssociationResolution:
    return GoalAssociationResolution(
        turn_id="turn-multi",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                description=f"Goal {goal_id}",
                source_text="multi goal request",
            )
            for goal_id in goal_ids
        ],
        confidence=0.95,
        reason_summary="Independent goals.",
        metadata={"status": "resolved"},
    )


def respond_plan(goal_id: str = "goal-1") -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-chat",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=0.96,
        goal_ids=[goal_id],
        goal_summary="greet the user",
        response_text="你好。",
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
        },
    )


def execute_plan(
    *,
    plan_id: str = "plan-blink",
    goal_id: str = "goal-1",
    relation: str | None = None,
) -> CanonicalPlan:
    metadata = {}
    if relation:
        metadata = {
            "plan_relation": relation,
            "user_confirmation_required": True,
        }
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="deep",
        disposition="execute",
        coverage="complete",
        confidence=0.91,
        goal_ids=[goal_id],
        goal_summary="blink the eyes",
        steps=[
            {
                "step_id": "blink",
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 4},
                "source_goal_ids": [goal_id],
            }
        ],
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
        },
        metadata=metadata,
    )


def blink_definition(*, confirmation: bool = False) -> SkillDefinition:
    return SkillDefinition(
        skill_id="soridormi.blink_eyes",
        provider_id="soridormi.mcp",
        description="Blink the robot eyes.",
        input_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 10}
            },
            "required": ["count"],
        },
        available=True,
        requires_confirmation=confirmation,
        interruptible=True,
        can_run_parallel=True,
        exclusive_group="eye_expression",
        metadata={"resource_claims": ["eye_expression"]},
    )


class GoalDrivenRuntimeTests(unittest.TestCase):
    def run_resolution(self, coordinator, client, *, text="hello"):
        return asyncio.run(
            coordinator.resolve(
                object(),
                text=text,
                sid="sid-pr7",
                route_decision=type(
                    "Decision",
                    (),
                    {"route": "chat", "intent": "conversation", "language": "zh-CN"},
                )(),
                context={"history": [], "active_goal_snapshots": []},
                history=[],
                language="zh-CN",
            )
        )


    def test_runtime_trace_profiles_actual_goal_driven_modules(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="report_only"),
        )
        with mock.patch.dict(
            os.environ,
            {
                "CHROMIE_RUNTIME_TRACE_MODE": "basic",
                "CHROMIE_RUNTIME_TRACE_EMIT_EVENTS": "0",
            },
            clear=False,
        ):
            result = self.run_resolution(coordinator, client)

        trace = result.metadata["runtime_trace"]
        summary = result.metadata["runtime_trace_summary"]
        self.assertTrue(trace["trace_id"].startswith("trace_"))
        self.assertEqual(trace["state"], "complete")
        self.assertGreaterEqual(summary["item_count"], 2)
        modules = {
            item["module"]["name"]
            for item in summary["module_aggregates"]
        }
        self.assertIn("orchestrator.cognitive_runtime", modules)
        self.assertIn("orchestrator.canonical_plan_adapter", modules)
        self.assertIn("total", result.timings_ms)

    def test_runtime_trace_can_emit_one_runtime_event_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = ScriptedClient(
                association=new_goal_association(),
                fast_plans=[respond_plan()],
            )
            coordinator = GoalDrivenRuntimeCoordinator(
                agent_client=client,
                adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
                policy=CognitiveRuntimePolicy(mode="report_only"),
            )
            with mock.patch.dict(
                os.environ,
                {
                    "CHROMIE_RUNTIME_TRACE_MODE": "basic",
                    "CHROMIE_RUNTIME_TRACE_EMIT_EVENTS": "1",
                    "CHROMIE_RUNTIME_EVENT_ROOT": str(root / "events"),
                    "CHROMIE_DATA_LOOP_TRIGGER_ROOT": str(root / "inbox"),
                },
                clear=False,
            ):
                result = self.run_resolution(coordinator, client)

            event = result.metadata["runtime_trace_event"]
            self.assertEqual(event["capture_status"], "complete")
            self.assertEqual(event["trigger_status"], "accepted")
            payload_root = Path(event["payload_root"])
            self.assertTrue((payload_root / "trace.json").is_file())
            self.assertTrue((payload_root / "trace-summary.json").is_file())

    def test_report_only_builds_terminal_plan_without_interaction(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="report_only"),
        )
        result = self.run_resolution(coordinator, client)
        self.assertEqual(result.status, "report_only")
        self.assertIsNone(result.interaction_response)
        self.assertEqual(client.calls, ["association", "fast", "compose"])
        self.assertEqual(result.metadata["architecture_attribution"], "not_evaluated")

    def test_budget_failure_is_preserved_without_causal_attribution(self):
        association = GoalAssociationResolution(
            turn_id="turn-truncated",
            clarification="请稍后重试。",
            confidence=0.0,
            reason_summary="Goal association output was truncated.",
            metadata={
                "status": "model_unavailable",
                "failure_class": "output_truncated",
                "failure_domain": "llm_budget",
                "architecture_attribution": "not_evaluated",
                "retryable": True,
                "done_reason": "length",
                "num_predict": 512,
            },
        )
        client = ScriptedClient(association=association, fast_plans=[])
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="report_only"),
        )

        result = self.run_resolution(coordinator, client)

        self.assertEqual(result.status, "error")
        self.assertEqual(result.metadata["failure_stage"], "goal_association")
        self.assertEqual(result.metadata["failure_class"], "output_truncated")
        self.assertEqual(result.metadata["failure_domain"], "llm_budget")
        self.assertEqual(result.metadata["architecture_attribution"], "not_evaluated")
        self.assertEqual(result.metadata["done_reason"], "length")
        self.assertIn("goal_association:output_truncated", result.fallback_reason)

    def test_goal_association_contract_failure_stops_before_any_planner(self):
        association = GoalAssociationResolution(
            turn_id="turn-contract-failed",
            clarification="Please try again.",
            confidence=0.0,
            reason_summary="Invalid structured output.",
            metadata={
                "status": "model_contract_failed",
                "failure_class": "structured_output_validation",
                "failure_domain": "model_contract",
                "architecture_attribution": "not_evaluated",
                "retryable": True,
            },
        )
        client = ScriptedClient(association=association, fast_plans=[])
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="report_only"),
        )

        result = self.run_resolution(coordinator, client, text="walk and blink")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.metadata["failure_stage"], "goal_association")
        self.assertEqual(client.calls, ["association"])

    def test_goal_association_clarification_skips_planners_and_composes_directly(self):
        association = GoalAssociationResolution(
            turn_id="turn-needs-clarification",
            clarification="Which direction should I move?",
            confidence=0.8,
            reason_summary="Direction is ambiguous.",
            metadata={"status": "needs_clarification"},
        )
        client = ScriptedClient(association=association, fast_plans=[])
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply", apply_lanes=frozenset({"chat"})),
        )

        result = self.run_resolution(coordinator, client, text="move over there")

        self.assertEqual(result.status, "applied")
        self.assertEqual(result.terminal_plan.disposition, "clarify")
        self.assertEqual(result.interaction_response.speech[0].text, "Which direction should I move?")
        self.assertEqual(client.calls, ["association", "compose"])

    def test_resolved_empty_goal_set_fails_closed_before_planning(self):
        association = GoalAssociationResolution(
            turn_id="turn-empty",
            associations=[
                {
                    "association_id": "assoc-new-without-goal",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.9,
                }
            ],
            confidence=0.9,
            metadata={"status": "resolved"},
        )
        client = ScriptedClient(association=association, fast_plans=[])
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="report_only"),
        )

        result = self.run_resolution(coordinator, client, text="walk and blink")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.metadata["failure_class"], "empty_canonical_goal_set")
        self.assertEqual(client.calls, ["association"])

    def test_apply_chat_returns_speech_only_interaction(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply", apply_lanes=frozenset({"chat"})),
        )
        result = self.run_resolution(coordinator, client)
        self.assertEqual(result.status, "applied")
        self.assertEqual(result.lane, "chat")
        self.assertEqual(result.interaction_response.skills, [])
        self.assertEqual(result.interaction_response.speech[0].text, "你好。")
        self.assertEqual(result.metadata["fast_planner_path"], "terminal")
        self.assertFalse(result.metadata["deep_planner_invoked"])
        self.assertTrue(result.metadata["deep_planner_avoided"])

    def test_fast_terminal_multi_goal_mixed_plan_skips_deep_planner(self):
        fast = CanonicalPlan(
            plan_id="fast-mixed",
            planner_tier="fast",
            disposition="mixed",
            coverage="complete",
            confidence=0.97,
            goal_ids=["goal-blink", "goal-joke"],
            steps=[{
                "step_id": "blink",
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-blink"],
            }],
            goal_outcomes=[
                {
                    "goal_id": "goal-blink",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
                {
                    "goal_id": "goal-joke",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "A short joke.",
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
            ],
            goal_satisfaction={"score": 1.0, "status": "exact"},
            metadata={"path_classification": "terminal"},
        )
        client = ScriptedClient(
            association=multi_goal_association("goal-blink", "goal-joke"),
            fast_plans=[fast],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"robot_action"}),
            ),
        )

        result = self.run_resolution(
            coordinator,
            client,
            text="Blink twice and tell me a short joke.",
        )

        self.assertEqual(result.status, "applied")
        self.assertEqual(client.calls, ["association", "fast", "compose"])
        self.assertEqual(result.terminal_plan.planner_tier, "fast")
        self.assertEqual(result.metadata["fast_planner_path"], "terminal")
        self.assertFalse(result.metadata["deep_planner_invoked"])
        self.assertEqual(result.metadata["fast_goal_outcome_count"], 2)
        self.assertEqual(result.metadata["fast_executable_step_count"], 1)

    def test_semantic_escalation_records_normal_deep_invocation_reason(self):
        fast = CanonicalPlan(
            plan_id="fast-semantic-escalation",
            planner_tier="fast",
            disposition="escalate",
            coverage="partial",
            confidence=0.9,
            goal_ids=["goal-1"],
            escalation_reason="rare capability requires full planning",
            metadata={"path_classification": "semantic_escalation"},
        )
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[fast],
            deep_plans=[execute_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
            policy=CognitiveRuntimePolicy(
                mode="apply", apply_lanes=frozenset({"robot_action"})
            ),
        )

        result = self.run_resolution(coordinator, client, text="眨眼。")

        self.assertEqual(result.status, "applied")
        self.assertEqual(
            result.metadata["deep_planner_invocation_reason"],
            "semantic_escalation",
        )
        self.assertEqual(result.metadata["stage_diagnostics"], [])
        self.assertEqual(
            client.deep_contexts[0]["deep_planner_invocation_reason"],
            "semantic_escalation",
        )

    def test_fast_contract_failure_stays_visible_and_is_sanitized_for_deep(self):
        fast = CanonicalPlan(
            plan_id="fast-contract-failure",
            planner_tier="fast",
            disposition="escalate",
            coverage="uncertain",
            confidence=0.0,
            goal_ids=["goal-1"],
            escalation_reason="fast_planner_model_contract_failed",
            metadata={
                "resolver": "fast_planner",
                "status": "escalate",
                "path_classification": "contract_failure",
                "failure_class": "structured_output_validation",
                "failure_domain": "model_contract",
                "initial_raw_output": '{"bad":true}',
                "repair_raw_output": '{"still_bad":true}',
            },
        )
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[fast],
            deep_plans=[execute_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
            policy=CognitiveRuntimePolicy(
                mode="apply", apply_lanes=frozenset({"robot_action"})
            ),
        )

        result = self.run_resolution(coordinator, client, text="眨眼。")

        self.assertEqual(result.status, "applied")
        self.assertEqual(
            result.metadata["deep_planner_invocation_reason"],
            "fast_contract_failure",
        )
        self.assertEqual(
            result.metadata["stage_diagnostics"][0]["failure_class"],
            "structured_output_validation",
        )
        deep_fast_metadata = client.deep_contexts[0]["fast_plan_resolution"][
            "metadata"
        ]
        self.assertNotIn("initial_raw_output", deep_fast_metadata)
        self.assertNotIn("repair_raw_output", deep_fast_metadata)

    def test_apply_robot_action_uses_runtime_confirmation_contract(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[
                CanonicalPlan(
                    plan_id="fast-escalate",
                    planner_tier="fast",
                    disposition="escalate",
                    coverage="partial",
                    confidence=0.9,
                    escalation_reason="needs full planning",
                )
            ],
            deep_plans=[execute_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(
                FakeRuntime([blink_definition(confirmation=True)])
            ),
            policy=CognitiveRuntimePolicy(
                mode="apply", apply_lanes=frozenset({"robot_action"})
            ),
        )
        result = self.run_resolution(coordinator, client, text="眨眼。")
        self.assertEqual(result.status, "applied")
        self.assertEqual(result.lane, "robot_action")
        request = result.interaction_response.skills[0]
        self.assertTrue(request.requires_confirmation)
        self.assertEqual(request.args, {"count": 4})
        self.assertIn("canonical_plan_fingerprint", request.metadata)

    def test_disabled_apply_lane_fails_closed(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[
                CanonicalPlan(
                    plan_id="fast-escalate",
                    planner_tier="fast",
                    disposition="escalate",
                    coverage="partial",
                    confidence=0.9,
                    escalation_reason="needs full planning",
                )
            ],
            deep_plans=[execute_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
            policy=CognitiveRuntimePolicy(mode="apply", apply_lanes=frozenset({"chat"})),
        )
        result = self.run_resolution(coordinator, client, text="眨眼。")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.fallback_reason, "terminal_plan_lane_not_enabled_for_apply")
        self.assertIsNone(result.interaction_response)

    def test_runtime_conflict_triggers_one_deep_replan(self):
        walk = SkillDefinition(
            skill_id="soridormi.walk_forward",
            provider_id="soridormi.mcp",
            input_schema={
                "type": "object",
                "properties": {"duration_s": {"type": "number", "minimum": 0.1}},
                "required": ["duration_s"],
            },
            available=True,
            can_run_parallel=False,
            exclusive_group="base_motion",
            metadata={"resource_claims": ["base_motion"]},
        )
        blink = blink_definition()
        fast = CanonicalPlan(
            plan_id="fast-escalate",
            planner_tier="fast",
            disposition="escalate",
            coverage="partial",
            confidence=0.9,
            escalation_reason="compound goal",
        )
        invalid = CanonicalPlan(
            plan_id="deep-parallel",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=0.9,
            goal_ids=["goal-1"],
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-1"],
                },
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 4},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-1"],
                },
            ],
            goal_satisfaction={"score": 1.0, "status": "exact"},
        )
        revised = invalid.model_copy(
            deep=True,
            update={
                "plan_id": "deep-sequential",
                "steps": [
                    invalid.steps[0].model_copy(update={"timing": "sequential"}),
                    invalid.steps[1].model_copy(update={"timing": "sequential"}),
                ],
                "metadata": {
                    "plan_relation": "alternative",
                    "user_confirmation_required": True,
                },
            },
        )
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[fast],
            deep_plans=[invalid, revised],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([walk, blink])),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"robot_action"}),
                host_replan_budget=1,
            ),
        )
        result = self.run_resolution(coordinator, client, text="边走边眨眼。")
        self.assertEqual(result.status, "applied")
        self.assertEqual(result.metadata["runtime_replan_count"], 1)
        self.assertIn("runtime_validator_feedback", client.deep_contexts[1])
        self.assertEqual(
            [step.timing for step in result.terminal_plan.steps],
            ["sequential", "sequential"],
        )
        self.assertTrue(
            all(item.requires_confirmation for item in result.interaction_response.skills)
        )
        self.assertTrue(
            result.interaction_response.metadata["disable_body_auto_confirm"]
        )

    def test_host_keeps_attention_with_matching_runtime_evidence(self):
        plan = respond_plan()
        attention_definition = SkillDefinition(
            skill_id="soridormi.look_at_person",
            provider_id="soridormi.mcp",
            input_schema={
                "type": "object",
                "properties": {"head_yaw_rad": {"type": "number"}},
                "required": ["head_yaw_rad"],
            },
            available=True,
            can_run_parallel=True,
            metadata={"resource_claims": ["head_attention"]},
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-attention-valid",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                final=ResponseStage(
                    text="你好。",
                    speech_act="inform",
                    commitment_state="none",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            social_attention_plan=SocialAttentionPlan(
                decision="express",
                target={
                    "target_ref": "active_user",
                    "source": "live_perception",
                    "relative_direction": "right",
                    "confidence": 0.9,
                },
                behaviors=[
                    {
                        "skill_id": "soridormi.look_at_person",
                        "args": {"head_yaw_rad": 0.35},
                        "timing": "parallel",
                    }
                ],
                confidence=0.9,
                metadata={"auxiliary_social_attention": True},
            ),
            confidence=0.9,
        )
        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([attention_definition])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-valid-target",
                language="zh-CN",
                context={
                    "social_attention_target_evidence": {
                        "available": True,
                        "source": "live_perception",
                        "target": {
                            "target_ref": "active_user",
                            "relative_direction": "right",
                            "suggested_args": {"head_yaw_rad": 0.35},
                        },
                    }
                },
            )
        )
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.look_at_person"],
        )
        self.assertEqual(response.metadata["omitted_social_attention"], [])

    def test_host_omits_attention_without_target_evidence(self):
        plan = respond_plan()
        attention_definition = SkillDefinition(
            skill_id="soridormi.look_at_person",
            provider_id="soridormi.mcp",
            input_schema={
                "type": "object",
                "properties": {"head_yaw_rad": {"type": "number"}},
                "required": ["head_yaw_rad"],
            },
            available=True,
            can_run_parallel=True,
            metadata={
                "resource_claims": ["head_attention"],
                "parallel_metadata_declared": True,
            },
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-attention-target",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                final=ResponseStage(
                    text="你好。",
                    speech_act="inform",
                    commitment_state="none",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            social_attention_plan=SocialAttentionPlan(
                decision="express",
                target={
                    "target_ref": "active_user",
                    "source": "live_perception",
                    "relative_direction": "left",
                    "confidence": 0.9,
                },
                behaviors=[
                    {
                        "skill_id": "soridormi.look_at_person",
                        "args": {"head_yaw_rad": -0.3},
                        "timing": "parallel",
                    }
                ],
                confidence=0.9,
                metadata={"auxiliary_social_attention": True},
            ),
            confidence=0.9,
        )
        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([attention_definition])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-target",
                language="zh-CN",
                context={"social_attention_target_evidence": {"available": False}},
            )
        )
        self.assertEqual(response.skills, [])
        self.assertIn(
            "attention_target_not_available",
            response.metadata["omitted_social_attention"],
        )

    def test_host_drops_conflicting_attention_but_keeps_primary_plan(self):
        plan = execute_plan()
        attention_definition = SkillDefinition(
            skill_id="soridormi.express_attention",
            provider_id="soridormi.mcp",
            input_schema={"type": "object", "properties": {}},
            available=True,
            can_run_parallel=True,
            exclusive_group="eye_expression",
            metadata={
                "resource_claims": ["eye_expression"],
                "parallel_metadata_declared": True,
            },
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-attention-conflict",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                pre_action=ResponseStage(
                    text="好的，我先准备。",
                    speech_act="inform",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            social_attention_plan=SocialAttentionPlan(
                decision="express",
                behaviors=[
                    {
                        "skill_id": "soridormi.express_attention",
                        "args": {},
                        "timing": "parallel",
                    }
                ],
                confidence=0.9,
                metadata={"auxiliary_social_attention": True},
            ),
            confidence=0.9,
        )
        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([blink_definition(), attention_definition])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-conflict",
                language="zh-CN",
                context={},
            )
        )
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.blink_eyes"],
        )
        self.assertIn(
            "resource_conflict:soridormi.express_attention",
            response.metadata["omitted_social_attention"],
        )

    def test_goal_state_is_not_applied_when_composition_fails(self):
        applied = []
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
            composition_status="model_unavailable",
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply"),
            goal_state_apply=lambda *args, **kwargs: applied.append(True) or [],
        )
        result = self.run_resolution(coordinator, client)
        self.assertEqual(result.status, "error")
        self.assertEqual(applied, [])

    def test_goal_state_applies_after_successful_composition(self):
        applied = []
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply"),
            goal_state_apply=lambda *args, **kwargs: applied.append(kwargs["source"]) or [],
        )
        result = self.run_resolution(coordinator, client)
        self.assertEqual(result.status, "applied")
        self.assertEqual(applied, ["goal_driven_cognitive_runtime"])

    def test_mixed_plan_executes_effectful_goal_and_preserves_ownership(self):
        plan = CanonicalPlan(
            plan_id="plan-mixed-runtime",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.94,
            goal_ids=["goal-blink", "goal-joke"],
            goal_summary="Blink twice and tell a joke.",
            steps=[
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-blink",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                },
                {
                    "goal_id": "goal-joke",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "A short joke.",
                },
            ],
            goal_satisfaction={
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-blink", "goal-joke"],
            },
        )
        response_plan = ResponsePlan(
            immediate=ResponseStage(
                text="A short joke.",
                speech_act="inform",
                commitment_state="none",
                must_not_claim_completion=True,
                covers_goal_ids=["goal-joke"],
            ),
            pre_action=ResponseStage(
                text="I will also blink twice.",
                speech_act="inform",
                commitment_state="evaluating",
                must_not_claim_completion=True,
                covers_goal_ids=["goal-blink"],
            ),
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-mixed-runtime",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=response_plan,
            confidence=0.94,
        )
        adapter = CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()]))

        errors = asyncio.run(adapter.validation_errors(plan))
        response = asyncio.run(
            adapter.build_response(
                plan=plan,
                composition=composition,
                session_id="sid-mixed-runtime",
                language="en-US",
            )
        )

        self.assertEqual(errors, [])
        self.assertEqual(response.status, "ok")
        self.assertEqual([item.skill_id for item in response.skills], ["soridormi.blink_eyes"])
        self.assertEqual(response.skills[0].metadata["source_goal_ids"], ["goal-blink"])
        self.assertEqual(response.metadata["planning_result"], "composed_plan")



class CognitiveEvidenceTests(unittest.TestCase):
    def test_evidence_hashes_text_and_tracks_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            recorder = CognitiveEvidenceRecorder(path, include_text=False)
            client = ScriptedClient(
                association=new_goal_association(),
                fast_plans=[respond_plan()],
            )
            coordinator = GoalDrivenRuntimeCoordinator(
                agent_client=client,
                adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
                policy=CognitiveRuntimePolicy(mode="report_only"),
            )
            result = asyncio.run(
                coordinator.resolve(
                    object(),
                    text="private text",
                    sid="sid-evidence",
                    route_decision=type(
                        "Decision",
                        (),
                        {"route": "chat", "intent": "conversation", "language": "en-US"},
                    )(),
                    context={"history": []},
                    history=[],
                    language="en-US",
                )
            )
            recorder.record(result, sid="sid-evidence", text="private text")
            payload = json.loads(path.read_text().splitlines()[0])
            self.assertNotIn("text", payload)
            self.assertEqual(payload["text_chars"], len("private text"))
            self.assertEqual(recorder.snapshot()["turns"], 1)


class AtomicGoalStateTests(unittest.TestCase):
    def test_atomic_goal_association_rolls_back_mixed_valid_and_invalid_updates(self):
        state = ConversationStateManager(enabled=True, max_pending_tasks=8)
        first = new_goal_association("goal-existing")
        created = state.apply_goal_association_resolution(
            first,
            sid="sid-create",
            user_text="create",
            atomic=True,
        )
        self.assertTrue(any(item.get("applied") for item in created))
        before = state.active_goal_snapshots()
        existing_goal_id = before[0]["goal_id"]
        mixed = GoalAssociationResolution(
            turn_id="turn-mixed",
            associations=[
                {
                    "association_id": "assoc-valid",
                    "relationship": "continue",
                    "target_goal_ids": [existing_goal_id],
                    "confidence": 0.9,
                },
                {
                    "association_id": "assoc-invalid",
                    "relationship": "modify",
                    "target_goal_ids": [existing_goal_id],
                    "confidence": 0.9,
                    "goal_update": {},
                },
            ],
            confidence=0.9,
        )
        results = state.apply_goal_association_resolution(
            mixed,
            sid="sid-mixed",
            user_text="modify",
            atomic=True,
        )
        self.assertTrue(any(item.get("reason") == "semantic_delta_required" for item in results))
        after = state.active_goal_snapshots()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
