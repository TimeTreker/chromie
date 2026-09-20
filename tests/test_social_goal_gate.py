from __future__ import annotations

import asyncio

from jsonschema import Draft202012Validator
import pytest

from agent.app.goal_association_contract import GoalSegmentationModelOutput
from agent.app.goal_association_schema import goal_association_response_schema
from agent.app.social_cognition import social_cognition_response_schema
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from shared.chromie_contracts.goal import GoalAssociation, GoalAssociationResolution
from shared.chromie_contracts.plan import (
    FastPlannerAdvance,
    FastPlannerCapabilityActivity,
    FastPlannerStreamTerminal,
)
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.social_cognition import (
    SocialCognitionRequest,
    SocialCognitionResolution,
)
from tests.test_cognitive_runtime_pr7 import FakeRuntime, admitted_core, blink_definition


def _speech(ref: str = "r1") -> CognitiveResponsibilityProposal:
    return CognitiveResponsibilityProposal(
        local_ref=ref,
        outcome="Maintain the current conversation.",
        output_mode="speech",
        continuity_scope="turn",
        confidence=1.0,
    )


def test_ga_no_goal_is_available_only_for_relation_free_ordinary_speech() -> None:
    schema = goal_association_response_schema(
        GoalSegmentationModelOutput,
        [],
        [],
        responsibility_count=1,
        responsibility_refs=["r1"],
        responsibility_output_modes={"r1": "speech"},
        responsibility_bindings={"r1": {}},
    )
    valid = {
        "decision": "no_goal",
        "new_goals": [],
        "non_goal_responsibility_refs": ["r1"],
        "referent_updates": [],
        "resolved_references": [],
        "confidence": 1.0,
        "reason_summary": "The current interaction is socially complete.",
    }
    validator = Draft202012Validator(schema)
    validator.validate(valid)

    # The legacy discriminant is not semantic authority. The ownership
    # collections already encode the complete result, so a decoder choosing
    # the first enum value must not produce a Schema-valid / DTO-invalid object.
    first_enum_compat = {**valid, "decision": "create_goals"}
    validator.validate(first_enum_compat)
    parsed = GoalSegmentationModelOutput.model_validate(first_enum_compat)
    assert parsed.new_goals == []
    assert parsed.non_goal_responsibility_refs == ["r1"]

    related = goal_association_response_schema(
        GoalSegmentationModelOutput,
        [],
        [],
        responsibility_count=2,
        responsibility_refs=["move", "say"],
        responsibility_output_modes={"move": "body_action", "say": "speech"},
        responsibility_bindings={"move": {}, "say": {"after": ["move"]}},
    )
    assert "say" not in (
        related["properties"].get("non_goal_responsibility_refs", {})
        .get("items", {})
        .get("enum", [])
    )


@pytest.mark.asyncio
async def test_conversational_ping_wakes_planner_only_after_ga_finds_goal() -> None:
    calls: list[str] = []
    ga_done = False

    class Agent:
        async def resolve_goal_association(self, session, **kwargs):
            nonlocal ga_done
            del session, kwargs
            calls.append("ga")
            ga_done = True
            return GoalAssociationResolution(
                turn_id="turn-ping",
                resolution_status="resolved",
                associations=[GoalAssociation(
                    association_id="ping-old-goal",
                    relationship="reference",
                    source_responsibility_refs=["r1"],
                    target_goal_ids=["goal-old"],
                    confidence=1.0,
                    reason_summary="The attention ping re-engages unfinished work.",
                )],
                confidence=1.0,
                reason_summary="Re-engage the retained Goal.",
            )

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            del session, kwargs
            calls.append("sc:" + request.trigger)
            if request.trigger == "interpretation":
                return SocialCognitionResolution(
                    request_id=request.request_id,
                    snapshot_digest=request.snapshot_digest(),
                    model_call_count=1,
                    disposition="communicate",
                    reason_summary="Maintain immediate social presence.",
                    activities=[{
                        "activity_id": "ping-presence",
                        "text": "Hey, I'm here.",
                        "function": "respond",
                        "truth_stage": "context_grounded",
                        "source_responsibility_refs": ["r1"],
                    }],
                )
            need = request.communication_needs[0]
            return SocialCognitionResolution(
                request_id=request.request_id,
                snapshot_digest=request.snapshot_digest(),
                model_call_count=1,
                disposition="communicate",
                reason_summary="Answer the Goal-backed status need.",
                need_outcomes={need.need_id: "covered"},
                activities=[{
                    "activity_id": "ping-status",
                    "text": "I'm checking that now.",
                    "function": "respond",
                    "truth_stage": "context_grounded",
                    "source_goal_ids": need.source_goal_ids,
                    "source_responsibility_refs": need.source_responsibility_refs,
                    "addressed_need_ids": [need.need_id],
                    "delivery_phase": need.delivery_phase or "immediate",
                }],
            )

        async def stream_fast_advance(self, session, *, request, **kwargs):
            del session, kwargs
            assert ga_done is True
            calls.append("planner:" + ",".join(
                item.local_ref for item in request.responsibilities
            ))
            advance = FastPlannerAdvance(
                turn_id=request.sid,
                disposition="respond",
                coverage="complete",
                covered_responsibility_refs=["r1"],
                activities=[{
                    "role": "complete_response",
                    "activity_id": "status-answer",
                    "source_responsibility_refs": ["r1"],
                    "rationale": "The retained Goal now owns the status response.",
                    "timing": "parallel",
                }],
                confidence=1.0,
                reason_summary="Answer the retained Goal status.",
            )
            yield FastPlannerStreamTerminal(turn_id=request.sid, advance=advance)

    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(),
        adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=lambda *args, **kwargs: [],
    )
    core, envelope = admitted_core(
        "Hello?",
        sid="social-ping",
        language="en-US",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "Re-engage the current conversation.",
            "output_mode": "speech",
            "continuity_scope": "turn",
            "confidence": 1.0,
        }],
    )
    result = await coordinator.resolve(
        object(),
        text="Hello?",
        sid="social-ping",
        core_interpretation=core,
        turn_envelope=envelope,
        context={"history": []},
        history=[],
        language="en-US",
    )

    assert result.status == "applied", result.fallback_reason
    assert "planner:r1" in calls
    assert calls.index("ga") < calls.index("planner:r1")
    assert result.metadata["planner_waited_for_goal_continuity"] is True
    assert result.goal_association.associations[0].target_goal_ids == ["goal-old"]


@pytest.mark.asyncio
async def test_mixed_greeting_and_work_plans_only_work_concurrently_with_ga() -> None:
    planner_started = asyncio.Event()
    calls: list[str] = []
    planner_refs: list[str] = []

    class Agent:
        async def resolve_goal_association(self, session, **kwargs):
            del session, kwargs
            calls.append("ga:start")
            await asyncio.wait_for(planner_started.wait(), timeout=1.0)
            calls.append("ga:end")
            return GoalAssociationResolution(
                turn_id="turn-mixed",
                resolution_status="resolved",
                non_goal_responsibility_refs=["greet"],
                new_goals=[SemanticGoal(
                    goal_id="goal-blink",
                    source_responsibility_refs=["blink"],
                    description="Blink once.",
                    source_text="blink once",
                    metadata={"output_mode": "body_action"},
                )],
                confidence=1.0,
                reason_summary="Greeting is social-only; blink is Goal-owned Work.",
            )

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            del session, kwargs
            calls.append("sc:" + request.trigger)
            if request.trigger == "interpretation":
                return SocialCognitionResolution(
                    request_id=request.request_id,
                    snapshot_digest=request.snapshot_digest(),
                    model_call_count=1,
                    disposition="communicate",
                    reason_summary="Greet while Work proceeds.",
                    activities=[{
                        "activity_id": "mixed-greeting",
                        "text": "Hi!",
                        "function": "respond",
                        "truth_stage": "context_grounded",
                        "source_responsibility_refs": ["greet"],
                    }],
                )
            return SocialCognitionResolution(
                request_id=request.request_id,
                snapshot_digest=request.snapshot_digest(),
                model_call_count=1,
                disposition="silence",
                activities=[],
                reason_summary="No additional speech is needed.",
                need_outcomes={},
            )

        async def stream_fast_advance(self, session, *, request, **kwargs):
            del session, kwargs
            planner_refs[:] = [item.local_ref for item in request.responsibilities]
            calls.append("planner:" + ",".join(planner_refs))
            planner_started.set()
            advance = FastPlannerAdvance(
                turn_id=request.sid,
                disposition="execute",
                coverage="complete",
                covered_responsibility_refs=["blink"],
                activities=[FastPlannerCapabilityActivity(
                    activity_id="blink-once",
                    role="capability",
                    capability_id="soridormi.blink_eyes",
                    args={"count": 1},
                    timing="parallel",
                    source_responsibility_refs=["blink"],
                )],
                confidence=1.0,
                reason_summary="Execute the requested blink.",
            )
            yield FastPlannerStreamTerminal(turn_id=request.sid, advance=advance)

    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(),
        adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=lambda *args, **kwargs: [],
    )
    core, envelope = admitted_core(
        "Hi, blink once.",
        sid="mixed-social-work",
        language="en-US",
        responsibilities=[
            {
                "local_ref": "greet",
                "outcome": "Greet Chromie.",
                "output_mode": "speech",
                "continuity_scope": "turn",
                "confidence": 1.0,
            },
            {
                "local_ref": "blink",
                "outcome": "Blink once.",
                "bindings": {"count": 1},
                "output_mode": "body_action",
                "continuity_scope": "goal",
                "confidence": 1.0,
            },
        ],
    )
    result = await asyncio.wait_for(
        coordinator.resolve(
            object(),
            text="Hi, blink once.",
            sid="mixed-social-work",
            core_interpretation=core,
            turn_envelope=envelope,
            context={"history": []},
            history=[],
            language="en-US",
        ),
        timeout=3.0,
    )

    assert result.status == "applied", result.fallback_reason
    assert planner_refs == ["blink"]
    assert calls.index("planner:blink") < calls.index("ga:end")
    assert result.metadata["planner_waited_for_goal_continuity"] is False
    assert result.goal_association.non_goal_responsibility_refs == ["greet"]
    assert result.terminal_plan.steps[0].capability_id == "soridormi.blink_eyes"


def test_social_expression_schema_keeps_capability_args_in_disjoint_branches() -> None:
    request = SocialCognitionRequest(
        request_id="sc-expression-branch",
        trigger="interpretation",
        source_refs=["turn-1"],
        source_turn={"turn_id": "turn-1", "original_text": "Hi."},
        responsibilities=[_speech()],
        context={"interaction_context": {"already_spoken": [], "pending_speech": []}},
    )
    candidates = [
        {
            "capability_id": "test.wave",
            "input_schema": {
                "type": "object",
                "properties": {"side": {"type": "string", "enum": ["left", "right"]}},
                "required": ["side"],
                "additionalProperties": False,
            },
        },
        {
            "capability_id": "test.blink",
            "input_schema": {
                "type": "object",
                "properties": {"count": {"type": "integer", "minimum": 1}},
                "required": ["count"],
                "additionalProperties": False,
            },
        },
    ]
    schema = social_cognition_response_schema(request, candidates)
    auxiliary = schema["$defs"]["AuxiliaryPlanActivity"]
    assert "oneOf" in auxiliary
    assert "allOf" not in auxiliary
    wave = next(
        branch for branch in auxiliary["oneOf"]
        if branch["properties"]["capability_id"]["const"] == "test.wave"
    )
    validator = Draft202012Validator({"$defs": schema["$defs"], **wave})
    base = {
        "auxiliary_activity_id": "wave",
        "anchor_kind": "communicative_act",
        "anchor_id": "hello",
        "capability_id": "test.wave",
        "social_function": "engagement",
        "target": {
            "target_ref": "none",
            "source": "none",
            "confidence": 0.0,
            "evidence_refs": [],
        },
    }
    assert validator.is_valid({**base, "args": {"side": "right"}})
    assert not validator.is_valid({**base, "args": {"count": 2}})
