from __future__ import annotations

from tests.capability_runtime_test_support import submit_and_wait_terminal

import asyncio
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from orchestrator.runtime.cognitive_gateway import CognitiveGateway
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveEvidenceRecorder,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.interaction_ledger import InteractionLedger
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.capability_runtime import (
    LocalSpeechCapabilityProvider,
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityRuntime,
    local_speech_definition,
)
from shared.chromie_contracts.execution_outcome import (
    claim_qualification_policy_sha256,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult
from shared.chromie_contracts.user_turn import AttentionReviewResult
from shared.chromie_contracts.interaction import output_schema_sha256
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerProgressActivity,
    render_fast_planner_vocal_activity,
)
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    DirectResponseComposition,
    ResponseCompositionResolution,
    canonical_plan_fingerprint,
    goal_association_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage, SemanticGoal


TEST_SKILL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"completed": {"type": "boolean"}},
    "required": ["completed"],
    "additionalProperties": False,
}


def admitted_core(
    text: str,
    *,
    sid: str,
    language: str,
    responsibilities: list[dict] | None = None,
):
    gateway = CognitiveGateway()
    capture = gateway.capture(
        text,
        session_id=sid,
        conversation_id=f"conversation-{sid}",
        channel="text",
        language=language,
    )
    snapshot = gateway.assemble_context(capture, {})
    envelope = gateway.admit_attention(
        capture,
        snapshot,
        AttentionReviewResult(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            context_digest=snapshot.digest,
            disposition="admit",
            speech_act="request",
            confidence=1.0,
            source="test",
            reason="runtime test input",
        ),
    )
    rows = responsibilities or [
        {
            "local_ref": "r1",
            "outcome": text,
            "bindings": {},
            "completion_requires_work": True,
            "completion_requires_fresh_evidence": False,
            "confidence": 0.95,
        }
    ]
    core = CoreInterpretationResult(
        turn_id=envelope.turn_id,
        session_id=envelope.session_id,
        confidence=min(float(item.get("confidence", 0.95)) for item in rows),
        language=language,
        responsibilities=rows,
    )
    return core, envelope


class FakeRuntime:
    def __init__(self, definitions: list[CapabilityDefinition] | None = None):
        self.definitions = {item.capability_id: item for item in (definitions or [])}
        self.ensure_calls: list[list[str]] = []

    async def ensure_capability_definitions(self, capability_ids):
        ids = list(capability_ids)
        self.ensure_calls.append(ids)
        missing = [item for item in ids if item not in self.definitions]
        if missing:
            raise ValueError(f"unknown capabilities: {missing}")

    def capability_definition(self, skill_id):
        if skill_id not in self.definitions:
            raise ValueError(f"unknown skill {skill_id}")
        return self.definitions[skill_id]


class FastAdvanceRuntime(FakeRuntime):
    def __init__(self, definitions: list[CapabilityDefinition] | None = None):
        super().__init__(definitions)
        self.started_fast_activities: list[tuple[str, str]] = []

    async def start_fast_planner_vocal_activity(
        self, activity, *, session_id: str, turn_id: str, language: str
    ):
        del session_id
        self.started_fast_activities.append(
            (turn_id, render_fast_planner_vocal_activity(activity, language=language))
        )
        return object()


class FastPlannerProgressRenderingTests(unittest.TestCase):
    def test_pre_capability_progress_does_not_promise_unknown_work(self):
        activity = FastPlannerProgressActivity(
            activity_id="status-progress",
            progress_kind="check_information",
            source_responsibility_refs=["status"],
        )

        self.assertEqual(
            render_fast_planner_vocal_activity(activity, language="en-US"),
            "Let me see what I can check.",
        )
        self.assertEqual(
            render_fast_planner_vocal_activity(activity, language="zh-CN"),
            "我先看看能不能查到。",
        )


class ScriptedClient:
    def __init__(
        self,
        *,
        association: GoalAssociationResolution,
        fast_plans: list[CanonicalPlan],
        deep_plans: list[CanonicalPlan] | None = None,
        fast_advances: list[FastPlannerAdvance] | None = None,
        composition_status: str = "resolved",
    ):
        self.association = association
        self.fast_plans = list(fast_plans)
        self.deep_plans = list(deep_plans or [])
        self.fast_advances = list(
            fast_advances
            if fast_advances is not None
            else [
                FastPlannerAdvance(
                    turn_id="test-fast-advance",
                    covered_responsibility_refs=["r1"],
                    continuations=["goal_association"],
                    confidence=0.95,
                    reason_summary="Continue through canonical Goal Association.",
                )
            ]
        )
        self.composition_status = composition_status
        self.deep_contexts: list[dict] = []
        self.compose_contexts: list[dict] = []
        self.calls: list[str] = []

    async def resolve_fast_advance(self, *args, **kwargs):
        self.calls.append("advance")
        if not self.fast_advances:
            raise AssertionError("unexpected pre-Goal Fast Planner advance")
        return self.fast_advances.pop(0)

    async def resolve_goal_association(self, *args, **kwargs):
        self.calls.append("association")
        return self.association

    async def resolve_fast_plan(self, *args, **kwargs):
        self.calls.append("fast")
        return self.fast_plans.pop(0)

    async def resolve_deep_plan(self, *args, **kwargs):
        self.calls.append("deep")
        request = kwargs.get("request")
        self.deep_contexts.append(dict(getattr(request, "context", {}) or {}))
        return self.deep_plans.pop(0)

    async def compose_response_plan(self, *args, **kwargs):
        self.calls.append("compose")
        request = kwargs.get("request")
        request_context = dict(getattr(request, "context", {}) or {})
        self.compose_contexts.append(request_context)
        if self.composition_status != "resolved":
            return ResponseCompositionResolution(
                status="model_unavailable",
                reason_summary="composer unavailable",
            )
        if "direct_goal_association_resolution" in request_context:
            goal_ids = [goal.goal_id for goal in self.association.new_goals]
            direct = DirectResponseComposition(
                composition_id="composition-direct-test",
                goal_association_fingerprint=goal_association_fingerprint(self.association),
                goal_association=self.association,
                response_plan=ResponsePlan(
                    final=ResponseStage(
                        text="你好。",
                        speech_act="inform",
                        commitment_state="completed",
                        must_not_claim_completion=False,
                        covers_goal_ids=goal_ids,
                    )
                ),
                confidence=0.91,
            )
            return ResponseCompositionResolution(
                status="resolved",
                composition=direct,
            )
        plan = CanonicalPlan.model_validate(
            request_context["canonical_plan_resolution"]
        )
        if plan.disposition == "execute":
            confirmation_required = bool(
                plan.metadata.get("user_confirmation_required")
            ) or any(
                item.get("requires_confirmation") is True
                for item in request_context.get("execution_capabilities", [])
            )
            response_plan = ResponsePlan(
                pre_action=ResponseStage(
                    text=(
                        "你愿意让我眨四下眼睛吗？如果可以，我就开始。"
                        if confirmation_required
                        else "好的，我先执行这个计划。"
                    ),
                    speech_act=(
                        "ask_confirmation" if confirmation_required else "inform"
                    ),
                    commitment_state=(
                        "waiting_for_user"
                        if confirmation_required
                        else "evaluating"
                    ),
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
        resolution_status="resolved",
        turn_id="turn-1",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                description="Respond to the user.",
                source_text="hello",
                metadata={
                    "responsibility_kind": "vocal_output",
                    "execution_lane": "vocal",
                    "output_mode": "speech",
                    "provider_required": False,
                },
            )
        ],
        confidence=0.95,
        reason_summary="A new independent user goal.",
        metadata={"status": "resolved"},
    )


def body_goal_association(goal_id: str = "goal-1") -> GoalAssociationResolution:
    return GoalAssociationResolution(
        resolution_status="resolved",
        turn_id="turn-body",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                description="Blink the eyes.",
                source_text="blink",
                metadata={
                    "responsibility_kind": "executable_action",
                    "execution_lane": "activity",
                    "output_mode": "activity",
                    "provider_required": True,
                },
            )
        ],
        confidence=0.95,
        reason_summary="A new observable body-action responsibility.",
        metadata={"status": "resolved"},
    )


def multi_goal_association(*goal_ids: str) -> GoalAssociationResolution:
    return GoalAssociationResolution(
        resolution_status="resolved",
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
                "capability_id": "soridormi.blink_eyes",
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


def blink_definition(*, confirmation: bool = False) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="soridormi.blink_eyes",
        provider_id="soridormi.mcp",
        description="Blink the robot eyes.",
        input_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 10}
            },
            "required": ["count"],
        },
        output_schema=TEST_SKILL_OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=confirmation,
        interruptible=True,
        can_run_parallel=True,
        exclusive_group="eye_expression",
        metadata={"resource_claims": ["eye_expression"]},
    )


def weather_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="chromie.weather.lookup",
        provider_id="chromie.local",
        description="Read the current weather forecast for a requested place.",
        input_schema={
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "date": {"type": "string"},
            },
            "required": ["location", "date"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "temperature_c": {"type": "number"},
                "apparent_temperature_c": {"type": "number"},
            },
            "additionalProperties": False,
        },
        available=True,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=False,
        metadata={
            "safety_class": "safe_read",
            "effects": ["read_only", "external_read", "weather_lookup"],
        },
    )


def walk_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="soridormi.walk_forward",
        provider_id="soridormi.mcp",
        description="Walk forward for a bounded duration.",
        input_schema={
            "type": "object",
            "properties": {
                "duration_s": {"type": "number", "minimum": 0.1, "maximum": 30}
            },
            "required": ["duration_s"],
            "additionalProperties": False,
        },
        output_schema=TEST_SKILL_OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=False,
        metadata={
            "safety_class": "physical_motion",
            "effects": ["physical_motion"],
        },
    )


class GoalDrivenRuntimeTests(unittest.TestCase):
    def test_goal_association_refreshes_committed_continuity_and_excludes_current_dialogue(self):
        live_context = {
            "conversation_id": "conversation-weather",
            "history": [
                {"role": "user", "sid": "turn-1", "text": "上海今晚是不是有大暴雨？"},
                {"role": "user", "sid": "turn-2", "text": "那你帮我查一下是不是有吗？"},
            ],
            "active_goal_snapshots": [
                {
                    "goal_id": "goal-shanghai-weather",
                    "status": "planning",
                    "goal": {
                        "description": "Check Shanghai weather tonight.",
                        "object": {
                            "bindings": {
                                "location": {"entity_type": "location", "value": "上海"}
                            }
                        },
                    },
                }
            ],
            "active_task_snapshots": [
                {
                    "task_id": "task-shanghai-weather",
                    "status": "planning",
                    "semantic_goal": {
                        "goal_id": "goal-shanghai-weather",
                        "description": "Check Shanghai weather tonight.",
                    },
                }
            ],
        }
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=object(),
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply"),
            context_refresh=lambda sid: live_context,
        )

        refreshed, history = coordinator._refresh_continuity_context(
            context={
                "conversation_id": "conversation-weather",
                "history": [],
                "active_goal_snapshots": [],
                "turn_id": "turn-2",
            },
            sid="turn-2",
        )

        self.assertEqual([item["sid"] for item in history], ["turn-1"])
        self.assertEqual(
            refreshed["active_goal_snapshots"][0]["goal"]["object"]["bindings"]["location"]["value"],
            "上海",
        )
        self.assertEqual(refreshed["active_task_snapshots"][0]["status"], "planning")
        first_turn_context, first_turn_history = coordinator._refresh_continuity_context(
            context={
                "conversation_id": "conversation-weather",
                "history": [],
                "turn_id": "turn-1",
            },
            sid="turn-1",
        )
        self.assertEqual(first_turn_history, [])
        self.assertEqual(first_turn_context["history"], [])
        self.assertIs(
            coordinator._goal_association_lock(
                context=refreshed, sid="turn-1"
            ),
            coordinator._goal_association_lock(
                context=refreshed, sid="turn-2"
            ),
        )

    def run_resolution(
        self,
        coordinator,
        client,
        *,
        text="hello",
        route="chat",
        intent=None,
    ):
        del route, intent
        core, envelope = admitted_core(
            text, sid="sid-pr7", language="zh-CN"
        )
        return asyncio.run(
            coordinator.resolve(
                object(),
                text=text,
                sid="sid-pr7",
                core_interpretation=core,
                context={"history": [], "active_goal_snapshots": []},
                history=[],
                language="zh-CN",
                turn_envelope=envelope,
            )
        )



    def test_fast_planner_progress_starts_before_goal_association(self):
        events: list[str] = []

        class Runtime(FastAdvanceRuntime):
            async def start_fast_planner_vocal_activity(
                self, activity, *, session_id: str, turn_id: str, language: str
            ):
                events.append("vocal_activity_started")
                return await super().start_fast_planner_vocal_activity(
                    activity,
                    session_id=session_id,
                    turn_id=turn_id,
                    language=language,
                )

        class Client(ScriptedClient):
            async def resolve_fast_advance(self, *args, **kwargs):
                events.append("advance")
                return await super().resolve_fast_advance(*args, **kwargs)

            async def resolve_goal_association(self, *args, **kwargs):
                events.append("association")
                return await super().resolve_goal_association(*args, **kwargs)

        advance = FastPlannerAdvance(
            turn_id="turn-weather",
            covered_responsibility_refs=["weather"],
            immediate_vocal_activity=FastPlannerProgressActivity(
                activity_id="weather-progress",
                progress_kind="check_information",
                speech_act="acknowledge",
                source_responsibility_refs=["weather"],
            ),
            continuations=["goal_association"],
            confidence=0.96,
            reason_summary="Fresh weather needs continuity while progress can speak now.",
        )
        client = Client(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
            fast_advances=[advance],
        )
        runtime = Runtime()
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(runtime),
            policy=CognitiveRuntimePolicy(mode="apply", apply_lanes=frozenset({"chat", "tool"})),
        )
        original_queue = coordinator._queue_social_attention_for_activity

        def observe_social_attention_queue(*args, **kwargs):
            activity = kwargs.get("activity")
            if activity is not None and activity.activity_id == "weather-progress":
                events.append("social_attention_queued")
            return original_queue(*args, **kwargs)

        coordinator._queue_social_attention_for_activity = observe_social_attention_queue
        core, envelope = admitted_core(
            "今天下午重庆会下雨吗？",
            sid="turn-weather",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "Tell the user whether it will rain in Chongqing this afternoon.",
                    "bindings": {"location": "重庆", "day_part": "afternoon"},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.96,
                }
            ],
        )
        result = asyncio.run(
            coordinator.resolve(
                object(),
                text="今天下午重庆会下雨吗？",
                sid="turn-weather",
                core_interpretation=core,
                turn_envelope=envelope,
                context={"history": [], "active_goal_snapshots": []},
                history=[],
                language="zh-CN",
            )
        )

        self.assertEqual(result.status, "applied")
        self.assertEqual(
            events[:4],
            ["advance", "social_attention_queued", "vocal_activity_started", "association"],
        )
        self.assertEqual(runtime.started_fast_activities[0][1], "我先看看能不能查到。")
        self.assertEqual(client.calls[:3], ["advance", "association", "compose"])

    def test_fast_planner_complexity_disposition_skips_second_fast_plan_after_goal_binding(self):
        advance = FastPlannerAdvance(
            turn_id="turn-complex",
            covered_responsibility_refs=["fetch-water"],
            immediate_vocal_activity=FastPlannerProgressActivity(
                activity_id="fetch-progress",
                progress_kind="perform_action",
                speech_act="acknowledge",
                source_responsibility_refs=["fetch-water"],
            ),
            continuations=["goal_association", "deep_planner"],
            confidence=0.91,
            reason_summary="Meaning is clear but HOW needs deeper planning.",
        )
        deep = execute_plan().model_copy(update={"planner_tier": "deep"})
        client = ScriptedClient(
            association=body_goal_association(),
            fast_plans=[],
            deep_plans=[deep],
            fast_advances=[advance],
        )
        runtime = FastAdvanceRuntime([blink_definition()])
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(runtime),
            policy=CognitiveRuntimePolicy(mode="apply", apply_lanes=frozenset({"chat", "robot_action"})),
        )
        core, envelope = admitted_core(
            "去那边把水拿回来给我。",
            sid="turn-complex",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "fetch-water",
                    "outcome": "Obtain the referenced water and bring it back to the requester.",
                    "bindings": {},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.94,
                }
            ],
        )
        result = asyncio.run(
            coordinator.resolve(
                object(),
                text="去那边把水拿回来给我。",
                sid="turn-complex",
                core_interpretation=core,
                turn_envelope=envelope,
                context={"history": [], "active_goal_snapshots": []},
                history=[],
                language="zh-CN",
            )
        )

        self.assertEqual(result.status, "applied")
        self.assertEqual(client.calls, ["advance", "association", "deep", "compose"])
        self.assertIsNone(result.fast_plan)
        self.assertEqual(result.terminal_plan.planner_tier, "deep")
        self.assertEqual(result.metadata["fast_planner_path"], "pre_goal_deep_escalation")

    def test_runtime_trace_profiles_actual_goal_driven_modules(self):
        client = ScriptedClient(
            association=body_goal_association(),
            fast_plans=[execute_plan().model_copy(update={"planner_tier": "fast"})],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
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
        self.assertGreaterEqual(summary["item_count"], 1)
        modules = {
            item["module"]["name"]
            for item in summary["module_aggregates"]
        }
        self.assertIn("orchestrator.cognitive_runtime", modules)
        self.assertIn("orchestrator.canonical_plan_adapter", modules)
        self.assertIn("total", result.timings_ms)

    def test_workflow_sink_receives_owned_stage_inputs_outputs_and_timing(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
        )
        observed: list[tuple[str, dict]] = []

        def retain_stage(sid: str, **stage: object) -> None:
            self.assertEqual(sid, "sid-pr7")
            observed.append((str(stage["stage"]), dict(stage)))

        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"chat"}),
            ),
            workflow_stage_sink=retain_stage,
        )

        result = self.run_resolution(coordinator, client)

        self.assertEqual(result.status, "applied")
        stage_names = [item[0] for item in observed]
        self.assertEqual(
            stage_names,
            [
                "fast_planner_advance",
                "goal_association",
                "response_composer",
                "runtime_adapter",
            ],
        )
        for _, stage in observed:
            self.assertIn("input_payload", stage)
            self.assertIn("output_payload", stage)
            self.assertGreaterEqual(
                float(stage["finished_monotonic_ms"]),
                float(stage["started_monotonic_ms"]),
            )

    def test_interaction_context_reaches_association_planner_and_composer(self):
        ledger = InteractionLedger()
        ledger.record_playback_event(
            {
                "event_id": "speech-existing",
                "session_id": "sid-pr7",
                "turn_id": "turn-1",
                "status": "playback_started",
                "text": "你好。",
                "source_goal_ids": ["goal-1"],
            }
        )

        class ContextClient(ScriptedClient):
            def __init__(self):
                super().__init__(
                    association=body_goal_association(),
                    fast_plans=[execute_plan().model_copy(update={"planner_tier": "fast"})],
                )
                self.association_contexts: list[dict] = []
                self.fast_contexts: list[dict] = []

            async def resolve_goal_association(self, *args, **kwargs):
                request = kwargs.get("request")
                self.association_contexts.append(
                    dict(getattr(request, "context", {}) or {})
                )
                return await super().resolve_goal_association(*args, **kwargs)

            async def resolve_fast_plan(self, *args, **kwargs):
                request = kwargs.get("request")
                self.fast_contexts.append(dict(getattr(request, "context", {}) or {}))
                return await super().resolve_fast_plan(*args, **kwargs)

        client = ContextClient()
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(
                FakeRuntime([blink_definition()]),
            ),
            policy=CognitiveRuntimePolicy(mode="apply"),
            interaction_ledger=ledger,
        )
        result = self.run_resolution(coordinator, client)

        self.assertEqual(result.status, "applied")
        self.assertEqual(
            client.association_contexts[0]["interaction_context"][
                "already_spoken"
            ][0]["subject_id"],
            "speech-existing",
        )
        self.assertIn(
            "goal_associated",
            {
                item["event_type"]
                for item in client.fast_contexts[0]["interaction_context"][
                    "goal_history"
                ]
            },
        )
        self.assertIn(
            "plan_resolved",
            {
                item["event_type"]
                for item in client.compose_contexts[0]["interaction_context"][
                    "goal_history"
                ]
            },
        )
        association_situation = client.association_contexts[0]["situation"]
        fast_situation = client.fast_contexts[0]["situation"]
        compose_situation = client.compose_contexts[0]["situation"]
        self.assertEqual(association_situation["revision"], 1)
        self.assertEqual(association_situation["focus_goal_ids"], [])
        self.assertEqual(fast_situation["revision"], 2)
        self.assertEqual(fast_situation["focus_goal_ids"], ["goal-1"])
        self.assertEqual(compose_situation, fast_situation)
        self.assertNotEqual(
            association_situation["digest"],
            fast_situation["digest"],
        )
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

    def test_goal_interpretation_cannot_short_circuit_missing_ability_before_goal_state(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"chat"}),
            ),
        )

        core, envelope = admitted_core(
            "附近有啥好吃的？",
            sid="sid-missing-restaurant",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "restaurant",
                    "outcome": "recommend good nearby restaurants",
                    "bindings": {"proximity": "nearby"},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
                }
            ],
        )
        client.fast_advances = [
            FastPlannerAdvance(
                turn_id=envelope.turn_id,
                covered_responsibility_refs=["restaurant"],
                continuations=["goal_association"],
                confidence=0.95,
                reason_summary="Capability availability is decided after canonical Goal binding.",
            )
        ]
        result = asyncio.run(
            coordinator.resolve(
                object(),
                text="附近有啥好吃的？",
                sid="sid-missing-restaurant",
                core_interpretation=core,
                context={"history": [], "active_goal_snapshots": []},
                history=[],
                language="zh-CN",
                turn_envelope=envelope,
            )
        )

        self.assertEqual(result.status, "applied")
        self.assertEqual(client.calls[:2], ["advance", "association"])
        self.assertNotEqual(
            result.metadata.get("fast_planner_path"),
            "terminal_missing_ability",
        )

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
        self.assertEqual(client.calls, ["advance", "association", "compose"])

    def test_response_composer_receives_playback_started_current_turn_speech(self):
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
        )
        event = {
            "event_id": "speech_event_fast",
            "stage": "fast_first",
            "purpose": "acknowledge_and_check",
            "status": "playback_started",
            "text": "好呀，我帮你看看。",
        }
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="report_only"),
            delivered_turn_speech_provider=lambda sid: [
                {**event, "session_id": sid}
            ],
        )

        result = self.run_resolution(coordinator, client)

        self.assertEqual(result.status, "report_only")
        self.assertEqual(
            client.compose_contexts[0]["delivered_turn_speech"],
            [{**event, "session_id": "sid-pr7"}],
        )

    def test_budget_failure_is_preserved_without_causal_attribution(self):
        association = GoalAssociationResolution(
            turn_id="turn-truncated",
            resolution_status="fail_closed",
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
            resolution_status="fail_closed",
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
        self.assertEqual(client.calls, ["advance", "association"])

    def test_goal_association_clarification_skips_planners_and_composes_directly(self):
        association = GoalAssociationResolution(
            resolution_status="needs_clarification",
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
        self.assertEqual(client.calls, ["advance", "association", "compose"])

    def test_resolved_empty_goal_set_fails_closed_before_planning(self):
        association = GoalAssociationResolution(
            resolution_status="resolved",
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
        self.assertEqual(client.calls, ["advance", "association"])

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
        self.assertEqual(result.interaction_response.capabilities, [])
        self.assertEqual(result.interaction_response.speech[0].text, "你好。")
        self.assertEqual(result.metadata["fast_planner_path"], "direct_vocal_output")
        self.assertFalse(result.metadata["deep_planner_invoked"])
        self.assertTrue(result.metadata["deep_planner_avoided"])

    def test_respond_delivery_failure_cannot_complete_goal(self):
        plan = respond_plan()
        composition = CoordinatedResponsePlan(
            composition_id="composition-respond-delivery",
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
            confidence=0.9,
        )
        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(FakeRuntime()).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-respond-delivery",
                language="zh-CN",
            )
        )
        self.assertTrue(response.speech[0].metadata["wait_for_playback_start"])
        self.assertTrue(
            response.speech[0].metadata["playback_start_required_for_delivery"]
        )

        state = ConversationStateManager(
            base_conversation_id="respond-delivery-failure"
        )
        state.apply_goal_association_resolution(new_goal_association(), sid='sid-respond-delivery', user_text='hello', atomic=True)
        state.record_interaction_response("sid-respond-delivery", response)
        self.assertEqual(
            state.active_goal_snapshots()[0]["work_status"],
            "scheduled",
        )

        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(
            LocalSpeechCapabilityProvider(lambda _args: {"scheduled": False})
        )
        execution = asyncio.run(submit_and_wait_terminal(runtime, response))

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[0].reason_code, "playback_not_started")
        self.assertTrue(
            state.update_pending_task_status_for_request_id(
                request_id=execution.results[0].request_id,
                status=execution.results[0].status,
            )
        )
        goal_context = next(
            item
            for item in state.snapshot()["task_contexts"]
            if item["semantic_goal"]["goal_id"] == "goal-1"
        )
        self.assertEqual(goal_context["status"], "failed")
        self.assertEqual(goal_context["plan_status"], "failed")
        self.assertNotEqual(goal_context["status"], "done")

    def test_canonical_robot_action_lane_comes_from_goal_state_not_pre_goal_label(self):
        fast = execute_plan(plan_id="fast-canonical-body").model_copy(
            update={
                "planner_tier": "fast",
                "metadata": {"path_classification": "terminal"},
            }
        )
        runtime = FakeRuntime([blink_definition()])
        client = ScriptedClient(
            association=body_goal_association(),
            fast_plans=[fast],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(runtime),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"chat", "robot_action"}),
            ),
        )

        result = self.run_resolution(
            coordinator,
            client,
            text="Blink your eyes.",
            route="chat",
        )

        self.assertEqual(result.status, "applied")
        self.assertEqual(result.lane, "robot_action")
        self.assertEqual(client.calls, ["advance", "association", "fast", "compose"])
        self.assertIsNotNone(result.interaction_response)
        self.assertEqual(
            [item.capability_id for item in result.interaction_response.capabilities],
            ["soridormi.blink_eyes"],
        )
        self.assertTrue(runtime.ensure_calls)

    def test_exact_execute_plan_preserves_prospective_response_text(self):
        top_level_payload = execute_plan().model_dump(mode="json")
        top_level_payload["response_text"] = "I can start with the supported action."
        top_level = CanonicalPlan.model_validate(top_level_payload)
        self.assertEqual(
            top_level.response_text,
            "I can start with the supported action.",
        )

        goal_outcome_payload = execute_plan().model_dump(mode="json")
        goal_outcome_payload["goal_outcomes"] = [
            {
                "goal_id": "goal-1",
                "disposition": "execute",
                "coverage": "complete",
                "response_text": "I can start with the supported action.",
                "step_ids": ["blink"],
            }
        ]
        per_goal = CanonicalPlan.model_validate(goal_outcome_payload)
        self.assertEqual(
            per_goal.goal_outcomes[0].response_text,
            "I can start with the supported action.",
        )

    def test_safe_read_preserves_model_owned_specific_pre_action_speech(self):
        plan = CanonicalPlan(
            plan_id="plan-weather",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=0.96,
            goal_ids=["goal-weather"],
            goal_summary="Check whether Chongqing is hot today.",
            steps=[
                {
                    "step_id": "weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "today"},
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["weather"],
                }
            ],
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-weather",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                pre_action=ResponseStage(
                    text="我看看。",
                    speech_act="inform",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            confidence=0.95,
        )
        mind = default_mind_profile().prompt_context(max_chars=5000)
        user_turn_envelope = {
            "turn_id": "turn-weather",
            "normalized_input": {
                "text": "今天重庆热不热呀？",
                "language": "zh-CN",
            },
        }

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([weather_definition()])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-weather",
                language="zh-CN",
                context={
                    "mind": mind,
                    "user_turn_envelope": user_turn_envelope,
                },
            )
        )

        self.assertEqual(len(response.speech), 1)
        self.assertEqual(response.speech[0].text, "我看看。")
        self.assertNotIn("相关信息", response.speech[0].text)
        self.assertEqual(
            response.speech[0].metadata["operational_text_source"],
            "llm_wording_runtime_validated",
        )
        self.assertEqual(
            response.metadata["operational_speech_authority"],
            "llm_optional_micro_ack",
        )
        self.assertTrue(response.metadata["safe_read_parallel_execution"])
        self.assertEqual(response.speech[0].timing, "parallel")
        self.assertFalse(response.speech[0].metadata["wait_for_playback_start"])
        self.assertFalse(
            response.speech[0].metadata["playback_start_required_for_effects"]
        )
        self.assertEqual(response.capabilities[0].timing, "parallel")
        self.assertTrue(response.capabilities[0].metadata["retryable_safe_read"])
        self.assertEqual(
            response.metadata["user_turn_envelope"],
            user_turn_envelope,
        )
        self.assertIn(
            "smart",
            response.metadata["personality_expression"]["core_traits"],
        )

    def test_safe_read_reuses_scheduled_fast_speech_without_duplicate_audio(self):
        plan = CanonicalPlan(
            plan_id="plan-weather-reuse",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.98,
            goal_ids=["goal-weather"],
            goal_summary="Check Chongqing weather.",
            steps=[
                {
                    "step_id": "weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "tomorrow"},
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["weather"],
                }
            ],
        )
        fast_text = "好嘛，我帮你看看重庆明天的天气。"
        composition = CoordinatedResponsePlan(
            composition_id="composition-weather-reuse",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text=fast_text,
                    speech_act="acknowledge_and_check",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    reuse_current_turn_speech=True,
                    reused_speech_event_id="speech_event_weather_reuse",
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            confidence=0.97,
        )

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([weather_definition()])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-weather-reuse",
                language="zh-CN",
                context={
                    "scheduled_turn_speech": [
                        {
                            "event_id": "speech_event_weather_reuse",
                            "status": "scheduled",
                            "text": fast_text,
                            "purpose": "acknowledge_and_check",
                            "generation": 6,
                            "orders": [11],
                            "source_goal_ids": ["goal-weather"],
                            "canonical_plan_id": plan.plan_id,
                            "canonical_plan_fingerprint": (
                                canonical_plan_fingerprint(plan)
                            ),
                        }
                    ]
                },
            )
        )

        self.assertEqual(len(response.speech), 1)
        metadata = response.speech[0].metadata
        self.assertTrue(metadata["reuse_current_turn_speech"])
        self.assertEqual(
            metadata["reused_speech_event_id"],
            "speech_event_weather_reuse",
        )
        self.assertEqual(metadata["reused_speech_generation"], 6)
        self.assertEqual(metadata["reused_speech_orders"], [11])
        self.assertEqual(metadata["turn_id"], "sid-weather-reuse")
        self.assertEqual(metadata["source_goal_ids"], ["goal-weather"])
        self.assertEqual(metadata["canonical_plan_id"], plan.plan_id)
        self.assertEqual(
            metadata["canonical_plan_fingerprint"],
            canonical_plan_fingerprint(plan),
        )
        self.assertEqual(response.speech[0].text, fast_text)

        with self.assertRaisesRegex(ValueError, "cannot be reassigned"):
            asyncio.run(
                CanonicalPlanRuntimeAdapter(
                    FakeRuntime([weather_definition()])
                ).build_response(
                    plan=plan,
                    composition=composition,
                    session_id="sid-weather-reuse",
                    language="zh-CN",
                    context={
                        "scheduled_turn_speech": [
                            {
                                "event_id": "speech_event_weather_reuse",
                                "status": "scheduled",
                                "text": fast_text,
                                "purpose": "acknowledge_and_check",
                                "generation": 6,
                                "orders": [11],
                                "source_goal_ids": ["goal-other"],
                                "canonical_plan_id": "plan-other",
                                "canonical_plan_fingerprint": "fingerprint-other",
                            }
                        ]
                    },
                )
            )

    def test_physical_activity_reuses_scheduled_fast_speech_and_keeps_skill(self):
        plan = CanonicalPlan(
            plan_id="plan-walk-reuse",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.98,
            goal_ids=["goal-walk"],
            goal_summary="Walk forward for fifteen seconds.",
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                }
            ],
        )
        fast_text = "好，我准备往前走十五秒。"
        composition = CoordinatedResponsePlan(
            composition_id="composition-walk-reuse",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                pre_action=ResponseStage(
                    text=fast_text,
                    speech_act="acknowledge",
                    commitment_state="heard",
                    must_not_claim_completion=True,
                    reuse_current_turn_speech=True,
                    reused_speech_event_id="speech_event_walk_reuse",
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            confidence=0.0,
        )

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([walk_definition()])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-walk-reuse",
                language="zh-CN",
                context={
                    "scheduled_turn_speech": [
                        {
                            "event_id": "speech_event_walk_reuse",
                            "status": "scheduled",
                            "text": fast_text,
                            "purpose": "acknowledge",
                            "generation": 7,
                            "orders": [12],
                        }
                    ]
                },
            )
        )

        self.assertEqual(len(response.capabilities), 1)
        self.assertEqual(
            response.capabilities[0].capability_id,
            "soridormi.walk_forward",
        )
        self.assertEqual(len(response.speech), 1)
        self.assertTrue(response.speech[0].metadata["wait_for_playback_start"])
        self.assertTrue(
            response.speech[0].metadata["playback_start_required_for_effects"]
        )
        self.assertTrue(
            response.speech[0].metadata["reuse_current_turn_speech"]
        )

    def test_safe_read_may_start_silently_without_delivery_barrier(self):
        plan = CanonicalPlan(
            plan_id="plan-weather-silent",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=0.96,
            goal_ids=["goal-weather"],
            goal_summary="Check Shanghai weather.",
            steps=[
                {
                    "step_id": "weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "上海", "date": "today"},
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["weather"],
                }
            ],
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-weather-silent",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(),
            confidence=0.95,
            metadata={"safe_read_speech_optional": True},
        )

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([weather_definition()])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-weather-silent",
                language="zh-CN",
                context={},
            )
        )

        self.assertEqual(response.speech, [])
        self.assertEqual(response.capabilities[0].timing, "parallel")
        self.assertTrue(response.capabilities[0].metadata["retryable_safe_read"])
        self.assertTrue(response.metadata["safe_read_parallel_execution"])

    def test_effectful_pre_execution_preserves_model_speech_with_barrier(self):
        plan = execute_plan()
        composition = CoordinatedResponsePlan(
            composition_id="composition-pre-action-projection",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="I heard the request and will blink next.",
                    speech_act="inform",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                ),
                progress=[
                    ResponseStage(
                        text="I am beginning the blink.",
                        speech_act="inform",
                        commitment_state="evaluating",
                        must_not_claim_completion=True,
                        covers_goal_ids=plan.goal_ids,
                    )
                ],
            ),
            confidence=0.9,
        )

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                FakeRuntime([blink_definition()])
            ).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-pre-action-projection",
                language="en-US",
            )
        )

        self.assertEqual(len(response.speech), 1)
        self.assertEqual(
            response.speech[0].text,
            "I heard the request and will blink next.",
        )
        self.assertEqual(response.speech[0].metadata["phase"], "immediate")
        self.assertEqual(
            response.speech[0].metadata["operational_text_source"],
            "llm_wording_runtime_validated",
        )
        self.assertTrue(response.speech[0].metadata["wait_for_playback_start"])
        self.assertTrue(
            response.speech[0].metadata["playback_start_required_for_delivery"]
        )
        self.assertTrue(
            response.speech[0].metadata["playback_start_required_for_effects"]
        )
        self.assertEqual(
            response.metadata["omitted_pre_execution_speech_phases"],
            ["progress"],
        )

    def test_compound_action_preserves_exact_composer_sentence(self):
        goal_ids = ["goal-walk", "goal-nod", "goal-turn"]
        plan = CanonicalPlan(
            plan_id="plan-walk-nod-turn",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=0.95,
            goal_ids=goal_ids,
            goal_summary="Walk, nod twice, and turn left.",
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_velocity",
                    "args": {"duration_s": 10.0, "speed": "0.2"},
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "nod",
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-nod"],
                },
                {
                    "step_id": "turn",
                    "capability_id": "soridormi.turn_in_place",
                    "args": {"yaw_radps": -0.12},
                    "source_goal_ids": ["goal-turn"],
                },
            ],
            goal_outcomes=[
                {
                    "goal_id": goal_id,
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": [step_id],
                }
                for goal_id, step_id in zip(
                    goal_ids,
                    ("walk", "nod", "turn"),
                    strict=True,
                )
            ],
            goal_satisfaction={
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        )
        composer_text = (
            "Okay! I'll walk forward for a bit, give you two nods, and then "
            "turn left."
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-walk-nod-turn",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                pre_action=ResponseStage(
                    text=composer_text,
                    speech_act="acknowledge",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=goal_ids,
                )
            ),
            confidence=0.95,
        )
        definitions = [
            CapabilityDefinition(
                capability_id=skill_id,
                provider_id="soridormi.mcp",
                input_schema={"type": "object"},
                output_schema=TEST_SKILL_OUTPUT_SCHEMA,
                available=True,
                requires_confirmation=False,
            )
            for skill_id in (
                "soridormi.walk_velocity",
                "soridormi.nod_yes",
                "soridormi.turn_in_place",
            )
        ]

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(FakeRuntime(definitions)).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-walk-nod-turn",
                language="en-US",
            )
        )

        self.assertEqual([item.text for item in response.speech], [composer_text])
        self.assertEqual(
            response.speech[0].metadata["operational_text_source"],
            "llm_wording_runtime_validated",
        )
        self.assertTrue(
            response.speech[0].metadata["playback_start_required_for_effects"]
        )

    def test_exact_execute_rejects_structurally_unrequired_confirmation(self):
        plan = execute_plan()
        composition = CoordinatedResponsePlan(
            composition_id="composition-false-confirmation",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="你愿意让我眨眼睛吗？",
                    speech_act="ask_confirmation",
                    commitment_state="waiting_for_user",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            confidence=0.9,
        )

        with self.assertRaisesRegex(
            ValueError,
            "requests confirmation without a runtime confirmation requirement",
        ):
            asyncio.run(
                CanonicalPlanRuntimeAdapter(
                    FakeRuntime([blink_definition()])
                ).build_response(
                    plan=plan,
                    composition=composition,
                    session_id="sid-false-confirmation",
                    language="zh-CN",
                )
            )

    def test_mixed_execute_and_clarify_preserves_coordinated_model_speech(self):
        plan = CanonicalPlan(
            plan_id="plan-mixed-execute-clarify",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.93,
            goal_ids=["goal-nod", "goal-walk"],
            goal_summary="Nod twice and ask how long to walk.",
            steps=[
                {
                    "step_id": "nod",
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-nod"],
                }
            ],
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "ask_user",
                    "blocking": True,
                    "source_goal_ids": ["goal-walk"],
                    "rationale": "Walking duration is required.",
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-nod",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["nod"],
                },
                {
                    "goal_id": "goal-walk",
                    "disposition": "clarify",
                    "coverage": "partial",
                    "response_text": "你希望我往前走多久？",
                },
            ],
            goal_satisfaction={
                "score": 0.75,
                "status": "substantial",
                "satisfied_goal_ids": ["goal-nod"],
                "unmet_goal_ids": ["goal-walk"],
            },
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-mixed-execute-clarify",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="我先点头两次。你希望我往前走多久？",
                    speech_act="clarify",
                    commitment_state="waiting_for_user",
                    must_not_claim_completion=True,
                    covers_goal_ids=["goal-nod", "goal-walk"],
                )
            ),
            confidence=0.92,
        )
        nod = CapabilityDefinition(
            capability_id="soridormi.nod_yes",
            provider_id="soridormi.mcp",
            input_schema={
                "type": "object",
                "properties": {"count": {"type": "integer", "minimum": 1}},
                "required": ["count"],
            },
            output_schema=TEST_SKILL_OUTPUT_SCHEMA,
            available=True,
            requires_confirmation=False,
        )

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(FakeRuntime([nod])).build_response(
                plan=plan,
                composition=composition,
                session_id="sid-mixed-execute-clarify",
                language="zh-CN",
            )
        )

        self.assertEqual(len(response.speech), 1)
        coordinated = response.speech[0]
        self.assertEqual(
            coordinated.text,
            "我先点头两次。你希望我往前走多久？",
        )
        self.assertEqual(
            coordinated.metadata["covers_goal_ids"],
            ["goal-nod", "goal-walk"],
        )
        self.assertEqual(
            coordinated.metadata["commitment_state"], "waiting_for_user"
        )
        self.assertFalse(coordinated.metadata["runtime_confirmation_required"])
        self.assertFalse(response.requires_confirmation)

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
                "capability_id": "soridormi.blink_eyes",
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
            route="robot_action",
        )

        self.assertEqual(result.status, "applied")
        self.assertEqual(client.calls, ["advance", "association", "fast", "compose"])
        self.assertEqual(result.terminal_plan.planner_tier, "fast")
        self.assertEqual(result.metadata["fast_planner_path"], "terminal")
        self.assertFalse(result.metadata["deep_planner_invoked"])
        self.assertTrue(result.metadata["fast_plan_committed_without_deep"])
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
            association=body_goal_association(),
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

        result = self.run_resolution(
            coordinator, client, text="眨眼。", route="robot_action"
        )

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

    def test_fast_contract_failure_does_not_invoke_deep_planner(self):
        validation_feedback = [
            {
                "type": "invalid_args",
                "capability_id": "soridormi.blink_eyes",
                "errors": ["args has unknown fields: ['times']"],
            }
        ]
        fast = CanonicalPlan(
            plan_id="fast-invalid-args",
            planner_tier="fast",
            disposition="escalate",
            coverage="uncertain",
            confidence=0.0,
            goal_ids=["goal-1"],
            escalation_reason="fast_planner_model_contract_failed",
            metadata={
                "path_classification": "contract_failure",
                "validation_feedback": validation_feedback,
                "failure_class": "structured_output_validation",
                "failure_domain": "model_contract",
            },
        )
        client = ScriptedClient(
            association=body_goal_association(),
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

        result = self.run_resolution(
            coordinator, client, text="眨眼。", route="robot_action"
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.metadata["failure_stage"], "fast_planner")
        self.assertEqual(result.metadata["fast_planner_path"], "contract_failure")
        self.assertFalse(result.metadata["deep_planner_invoked"])
        self.assertTrue(result.metadata["deep_planner_avoided"])
        self.assertEqual(client.deep_contexts, [])

    def test_fast_contract_failure_stays_visible_without_deep_repair(self):
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
            association=body_goal_association(),
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

        result = self.run_resolution(
            coordinator, client, text="眨眼。", route="robot_action"
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.metadata["failure_stage"], "fast_planner")
        self.assertEqual(result.metadata["failure_class"], "structured_output_validation")
        self.assertEqual(result.metadata["fast_planner_path"], "contract_failure")
        self.assertFalse(result.metadata["deep_planner_invoked"])
        self.assertNotIn("initial_raw_output", result.metadata)
        self.assertNotIn("repair_raw_output", result.metadata)
        self.assertEqual(client.deep_contexts, [])

    def test_apply_robot_action_uses_runtime_confirmation_contract(self):
        client = ScriptedClient(
            association=body_goal_association(),
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
        result = self.run_resolution(
            coordinator, client, text="眨眼。", route="robot_action"
        )
        self.assertEqual(result.status, "applied")
        self.assertEqual(result.lane, "robot_action")
        request = result.interaction_response.capabilities[0]
        self.assertTrue(request.requires_confirmation)
        self.assertEqual(request.args, {"count": 4})
        self.assertIn("canonical_plan_fingerprint", request.metadata)
        self.assertEqual(
            request.committed_output_schema_sha256,
            output_schema_sha256(TEST_SKILL_OUTPUT_SCHEMA),
        )
        expected_definition = blink_definition(confirmation=True)
        self.assertIsNotNone(expected_definition.completion_evidence_policy)
        assert expected_definition.completion_evidence_policy is not None
        self.assertEqual(
            request.committed_completion_evidence_sha256,
            claim_qualification_policy_sha256(
                expected_definition.completion_evidence_policy
            ),
        )
        self.assertEqual(
            result.interaction_response.speech[0].text,
            "你愿意让我眨四下眼睛吗？如果可以，我就开始。",
        )
        self.assertEqual(
            result.interaction_response.metadata["confirmation_prompt"],
            result.interaction_response.speech[0].text,
        )
        self.assertTrue(
            result.interaction_response.speech[0].metadata[
                "runtime_confirmation_required"
            ]
        )
        self.assertEqual(
            result.interaction_response.metadata["confirmation_prompt_source"],
            "llm_wording_runtime_validated",
        )
        self.assertTrue(
            result.interaction_response.speech[0].metadata[
                "wait_for_playback_start"
            ]
        )

    def test_disabled_apply_lane_fails_closed(self):
        client = ScriptedClient(
            association=body_goal_association(),
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
        result = self.run_resolution(
            coordinator, client, text="眨眼。", route="robot_action"
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.fallback_reason, "terminal_plan_lane_not_enabled_for_apply")
        self.assertIsNone(result.interaction_response)

    def test_single_step_parallel_plan_is_allowed(self):
        plan = execute_plan().model_copy(
            deep=True,
            update={
                "steps": [
                    execute_plan().steps[0].model_copy(
                        update={"timing": "parallel"}
                    )
                ]
            },
        )
        adapter = CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()]))

        errors = asyncio.run(adapter.validation_errors(plan))

        self.assertEqual(errors, [])

    def test_runtime_rejects_undeclared_provider_output_before_commit(self):
        definition = blink_definition().model_copy(update={"output_schema": {}})
        adapter = CanonicalPlanRuntimeAdapter(FakeRuntime([definition]))

        errors = asyncio.run(adapter.validation_errors(execute_plan()))

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["type"], "runtime_invalid_output_schema")
        self.assertEqual(errors[0]["step_id"], "blink")
        self.assertIn("root must have type=object", errors[0]["message"])

    def test_singleton_parallel_batch_in_multi_step_plan_is_rejected(self):
        base = execute_plan()
        plan = base.model_copy(
            deep=True,
            update={
                "steps": [
                    base.steps[0].model_copy(
                        update={"step_id": "blink-first", "timing": "sequential"}
                    ),
                    base.steps[0].model_copy(
                        update={"step_id": "blink-second", "timing": "parallel"}
                    ),
                ]
            },
        )
        adapter = CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()]))

        errors = asyncio.run(adapter.validation_errors(plan))

        self.assertEqual(
            errors,
            [
                {
                    "type": "runtime_parallel_singleton_group",
                    "step_id": "blink-second",
                    "capability_id": "soridormi.blink_eyes",
                }
            ],
        )

    def test_runtime_conflict_fails_closed_without_host_replan(self):
        walk = CapabilityDefinition(
            capability_id="soridormi.walk_forward",
            provider_id="soridormi.mcp",
            input_schema={
                "type": "object",
                "properties": {"duration_s": {"type": "number", "minimum": 0.1}},
                "required": ["duration_s"],
            },
            output_schema=TEST_SKILL_OUTPUT_SCHEMA,
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
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-1"],
                },
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
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
            association=body_goal_association(),
            fast_plans=[fast],
            deep_plans=[invalid, revised],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([walk, blink])),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"robot_action"}),
            ),
        )
        result = self.run_resolution(
            coordinator, client, text="边走边眨眼。", route="robot_action"
        )
        self.assertEqual(result.status, "error")
        self.assertIn(
            "runtime validation rejected terminal canonical plan",
            result.fallback_reason,
        )
        self.assertEqual(len(client.deep_contexts), 1)
        self.assertNotIn("host_replan", client.deep_contexts[0].values())
        self.assertEqual(
            [step.timing for step in result.terminal_plan.steps],
            ["parallel", "parallel"],
        )
        self.assertIsNone(result.interaction_response)

    def test_goal_state_is_visible_even_when_later_composition_fails(self):
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
            goal_state_apply=lambda *args, **kwargs: applied.append(
                kwargs["source"]
            )
            or [],
        )
        result = self.run_resolution(coordinator, client)
        self.assertEqual(result.status, "error")
        self.assertEqual(
            applied,
            ["goal_driven_cognitive_runtime_goal_association"],
        )
        self.assertEqual(
            result.metadata["goal_state_commit_stage"],
            "goal_association",
        )

    def test_goal_state_applies_immediately_after_goal_association(self):
        applied = []
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[respond_plan()],
        )

        def apply_goal_state(*args, **kwargs):
            del args
            applied.append(
                {
                    "source": kwargs["source"],
                    "client_calls": list(client.calls),
                }
            )
            return []

        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply"),
            goal_state_apply=apply_goal_state,
        )
        result = self.run_resolution(coordinator, client)
        self.assertEqual(result.status, "applied")
        self.assertEqual(
            applied,
            [
                {
                    "source": "goal_driven_cognitive_runtime_goal_association",
                    "client_calls": ["advance", "association"],
                }
            ],
        )
        self.assertEqual(
            result.metadata["goal_state_commit_stage"],
            "goal_association",
        )

    def test_followup_context_can_see_goal_while_planner_is_still_running(self):
        manager = ConversationStateManager(enabled=True)

        class BlockingPlannerClient(ScriptedClient):
            def __init__(self):
                super().__init__(
                    association=body_goal_association("goal-weather"),
                    fast_plans=[execute_plan(goal_id="goal-weather").model_copy(update={"planner_tier": "fast"})],
                )
                self.planner_started = asyncio.Event()
                self.release_planner = asyncio.Event()

            async def resolve_fast_plan(self, *args, **kwargs):
                del args, kwargs
                self.calls.append("fast")
                self.planner_started.set()
                await self.release_planner.wait()
                return self.fast_plans.pop(0)

        client = BlockingPlannerClient()
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
            policy=CognitiveRuntimePolicy(mode="apply"),
            goal_state_apply=manager.apply_goal_association_resolution,
        )

        async def run():
            core, envelope = admitted_core(
                "check the weather", sid="sid-weather", language="en-US"
            )
            task = asyncio.create_task(
                coordinator.resolve(
                    object(),
                    text="check the weather",
                    sid="sid-weather",
                    core_interpretation=core,
                    turn_envelope=envelope,
                    context={"history": [], "active_goal_snapshots": []},
                    history=[],
                    language="en-US",
                )
            )
            await asyncio.wait_for(client.planner_started.wait(), timeout=1.0)
            self.assertFalse(task.done())
            snapshots = manager.active_goal_snapshots()
            self.assertEqual(
                [item["goal_id"] for item in snapshots],
                ["goal-weather"],
            )
            self.assertEqual(snapshots[0]["work_status"], "planning")
            client.release_planner.set()
            return await task

        result = asyncio.run(run())
        self.assertEqual(result.status, "applied")
        self.assertEqual(client.calls, ["advance", "association", "fast", "compose"])

    def test_named_cancellation_is_not_committed_before_runtime_closure(self):
        association = GoalAssociationResolution(
            resolution_status="resolved",
            turn_id="turn-cancel",
            associations=[
                {
                    "association_id": "association-cancel",
                    "relationship": "cancel",
                    "target_goal_ids": ["goal-existing"],
                    "confidence": 0.96,
                    "reason_summary": "The user cancelled the existing goal.",
                }
            ],
            confidence=0.96,
            metadata={"status": "resolved"},
        )
        applied = []
        client = ScriptedClient(
            association=association,
            fast_plans=[respond_plan("goal-existing")],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply"),
            goal_state_apply=lambda *args, **kwargs: applied.append(
                (args, kwargs)
            )
            or [],
        )

        result = self.run_resolution(coordinator, client)

        self.assertEqual(result.status, "applied")
        self.assertEqual(applied, [])
        self.assertEqual(
            result.metadata["goal_state_commit_stage"],
            "deferred_named_goal_cancellation",
        )

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
                    "capability_id": "soridormi.blink_eyes",
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
        self.assertEqual([item.capability_id for item in response.capabilities], ["soridormi.blink_eyes"])
        self.assertEqual(response.capabilities[0].metadata["source_goal_ids"], ["goal-blink"])
        self.assertEqual(response.metadata["planning_result"], "composed_plan")
        self.assertEqual(
            [item.text for item in response.speech],
            [
                "A short joke.",
                "I will also blink twice.",
            ],
        )
        self.assertTrue(
            all(item.metadata["wait_for_playback_start"] for item in response.speech)
        )



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
            core, envelope = admitted_core(
                "private text", sid="sid-evidence", language="en-US"
            )
            result = asyncio.run(
                coordinator.resolve(
                    object(),
                    text="private text",
                    sid="sid-evidence",
                    core_interpretation=core,
                    turn_envelope=envelope,
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
            resolution_status="resolved",
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
