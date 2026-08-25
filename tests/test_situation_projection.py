from __future__ import annotations

from orchestrator.runtime.situation import build_situation_projection
from shared.chromie_contracts.situation import (
    CognitiveOpportunity,
    SituationInterpretation,
    SituationProjection,
    SituationSourceRef,
)


def test_situation_projection_is_bounded_current_interpretation_and_reconstructable() -> None:
    context = {
        "active_goal_snapshots": [
            {
                "goal_id": "goal-water",
                "open_information_gaps": [
                    {
                        "gap_id": "target-container",
                        "description": "Which cup?",
                        "preferred_resolution": "ask_user",
                        "resolved": False,
                    }
                ],
            }
        ],
        "discourse_focus": ["ref-user", "ref-blue-cup"],
        "recent_tool_evidence": [
            {
                "evidence_id": "evidence-camera-1",
                "source": "interaction_camera_observation",
                "payload": {"large": "authoritative evidence stays outside Situation"},
            }
        ],
    }

    first = build_situation_projection(
        context=context,
        turn_id="turn-1",
    )
    rebuilt = build_situation_projection(
        context=context,
        turn_id="turn-1",
    )

    assert first == rebuilt
    assert first.focus_goal_ids == ["goal-water"]
    assert first.discourse_focus_ids == ["ref-user", "ref-blue-cup"]
    assert first.unresolved_conditions[0].condition_id == "target-container"
    assert first.source_refs[0].reference_id == "evidence-camera-1"
    assert first.source_refs[0].kind == "evidence"
    assert first.interpretations == []
    projection = first.prompt_projection()
    assert "payload" not in str(projection)
    assert SituationProjection.model_validate(projection) == first


def test_situation_revision_can_change_focus_without_mutating_source_context() -> None:
    context = {
        "active_goal_snapshots": [{"goal_id": "goal-old"}],
        "discourse_focus": ["ref-one"],
    }

    before = build_situation_projection(
        context=context,
        turn_id="turn-2",
        revision=1,
    )
    after = build_situation_projection(
        context=context,
        turn_id="turn-2",
        focus_goal_ids=["goal-new"],
        revision=2,
    )

    assert before.focus_goal_ids == ["goal-old"]
    assert after.focus_goal_ids == ["goal-new"]
    assert before.digest != after.digest
    assert context["active_goal_snapshots"][0]["goal_id"] == "goal-old"


def test_cognitive_opportunity_is_stable_bounded_and_ephemeral_by_contract():
    first = CognitiveOpportunity.create(
        trigger="execution_outcome",
        goal_ids=["goal-weather"],
        evidence_refs=["outcome-1", "evidence-1"],
        reason_codes=["missing_capability_result"],
        recommended_cognition="fast",
        situation_digest="a" * 64,
    )
    second = CognitiveOpportunity.create(
        trigger="execution_outcome",
        goal_ids=["goal-weather"],
        evidence_refs=["outcome-1", "evidence-1"],
        reason_codes=["missing_capability_result"],
        recommended_cognition="fast",
        situation_digest="a" * 64,
    )

    assert first == second
    assert first.opportunity_id.startswith("cognitive_opportunity_")
    assert first.goal_ids == ["goal-weather"]
    assert first.recommended_cognition == "fast"
    assert first.prompt_projection()["evidence_refs"] == [
        "outcome-1",
        "evidence-1",
    ]


def test_trusted_situation_revision_emits_only_on_semantic_delta() -> None:
    from orchestrator.runtime.situation import derive_situation_revision_opportunity
    from shared.chromie_contracts.situation import SituationRevisionObservation

    source = SituationSourceRef(
        kind="evidence",
        reference_id="scene-evidence-3",
        owner="trusted_scene_projection",
    )
    interpretation = SituationInterpretation(
        interpretation_id="interpretation-cup-visible",
        subject_ref="scene-object:cup-3",
        relation="scene.visibility",
        value="visible",
        epistemic_status="established",
        relevance_goal_ids=["goal-look"],
        source_refs=["scene-evidence-3"],
    )
    projection = build_situation_projection(
        context={"active_goal_snapshots": [{"goal_id": "goal-look"}]},
        turn_id="turn-look",
        revision=3,
        source_refs=[source],
        interpretations=[interpretation],
    )
    observation = SituationRevisionObservation(
        observation_id="scene-observation-3",
        source_id="trusted_scene_projection",
        source_revision=3,
        goal_ids=["goal-look"],
        source_refs=["scene-evidence-3"],
        projection=projection,
    )

    opportunity = derive_situation_revision_opportunity(
        observation,
        previous_situation_digest="b" * 64,
    )
    assert opportunity is not None
    assert opportunity.trigger == "situation_revision"
    assert opportunity.goal_ids == ["goal-look"]
    assert opportunity.evidence_refs == ["scene-evidence-3"]
    assert opportunity.situation_digest == projection.digest
    assert (
        derive_situation_revision_opportunity(
            observation,
            previous_situation_digest=projection.digest,
        )
        is None
    )


def test_live_provider_state_enters_situation_without_becoming_evidence() -> None:
    from orchestrator.runtime.situation import (
        build_provider_state_situation_observation,
        derive_situation_revision_opportunity,
    )

    observation = build_provider_state_situation_observation(
        context={
            "active_goal_snapshots": [{"goal_id": "goal-water"}],
            "recent_tool_evidence": [
                {
                    "evidence_id": "evidence-before-progress",
                    "source": "tool_result",
                    "payload": {"must_not_copy": "large payload"},
                }
            ],
        },
        turn_id="turn-water",
        goal_ids=["goal-water"],
        dispatch_id="dispatch-water",
        request_id="request-walk",
        capability_id="soridormi.walk_forward",
        provider_id="soridormi.mcp",
        sequence=7,
        provider_state={
            "status": "blocked",
            "waiting_for": "door_open",
            "blocked": True,
            "percent": 41,
        },
    )

    projection = observation.projection
    runtime_sources = [
        item for item in projection.source_refs if item.kind == "runtime_state"
    ]
    assert len(runtime_sources) == 1
    assert runtime_sources[0].reference_id == observation.source_refs[0]
    assert {
        (item.relation, item.value) for item in projection.interpretations
    } == {
        ("runtime.status", "blocked"),
        ("runtime.waiting_for", "door_open"),
        ("runtime.condition", "blocked"),
    }
    assert all(
        item.relevance_goal_ids == ["goal-water"]
        for item in projection.interpretations
    )
    prompt = projection.prompt_projection()
    assert "percent" not in str(prompt)
    assert "must_not_copy" not in str(prompt)

    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None
    assert opportunity.trigger == "situation_revision"
    assert opportunity.situation_digest == projection.digest
    assert opportunity.evidence_refs == []


def test_situation_digest_opportunity_cannot_reenter_with_different_projection() -> None:
    import asyncio

    from orchestrator.orchestrator import VoiceAssistant
    from shared.chromie_contracts.core_interpretation import (
        CognitiveResponsibilityProposal,
    )

    situation = build_situation_projection(
        context={"active_goal_snapshots": [{"goal_id": "goal-look"}]},
        turn_id="turn-look",
        focus_goal_ids=["goal-look"],
    )
    mismatched = CognitiveOpportunity.create(
        trigger="situation_revision",
        goal_ids=["goal-look"],
        reason_codes=["trusted_situation_revision"],
        recommended_cognition="fast",
        situation_digest="b" * 64,
    )
    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.session_log = lambda *_args, **_kwargs: None

    response = asyncio.run(
        assistant._planner_state_reentry_response(
            source_response=None,
            canonical_plan=None,
            user_request="Look again.",
            language="en-US",
            goal_ids=["goal-look"],
            evidence_goal_ids=[],
            evidence_refs=[],
            session_id=None,
            phase="situation_revision_reentry",
            context_updates={
                "situation": situation.prompt_projection(),
                "cognitive_opportunity": mismatched.prompt_projection(),
            },
            fast_workflow_stage="fast_planner_situation_revision_reentry",
            deep_workflow_stage="planner_deep_pass_situation_revision_reentry",
            response_source="fast_planner_situation_revision_reentry",
            responsibilities_override=[
                CognitiveResponsibilityProposal(
                    local_ref="resp-look",
                    outcome="Look again.",
                    output_mode="stateful_effect",
                    relationship="new",
                    confidence=1.0,
                )
            ],
        )
    )
    assert response is None


def test_due_time_condition_runtime_cycle_reenters_same_planner_without_evidence() -> None:
    import asyncio

    from orchestrator.runtime.situation import drain_due_time_conditions_once
    from shared.chromie_contracts.situation import GoalTimeCondition

    condition = GoalTimeCondition(
        condition_id="condition-reminder",
        goal_id="goal-reminder",
        due_at_ms=2_000,
        source_plan_id="plan-reminder",
        source_responsibility_refs=["resp-reminder"],
    )
    opportunity = CognitiveOpportunity.create(
        trigger="time_condition",
        goal_ids=["goal-reminder"],
        reason_codes=["planner_time_condition"],
        recommended_cognition="fast",
    )

    class State:
        def due_time_condition_opportunities(self, *, now_ms=None):
            assert now_ms == 2_000
            return [
                {
                    "condition": condition.model_dump(mode="json"),
                    "opportunity": opportunity.prompt_projection(),
                    "source_text": "Remind me later.",
                    "language": "en-US",
                    "responsibilities": [
                        {
                            "local_ref": "resp-reminder",
                            "outcome": "Remind the user at the requested time.",
                            "bindings": {},
                            "output_mode": "stateful_effect",
                            "relationship": "new",
                            "target_goal_ids": [],
                            "confidence": 1.0,
                        }
                    ],
                }
            ]

    class Host:
        def __init__(self) -> None:
            self.conversation_state = State()
            self.reentry = None
            self.applied = None

        def session_log(self, *_args, **_kwargs):
            return None

        async def _planner_state_reentry_response(self, **kwargs):
            self.reentry = kwargs
            return {"planner": "response"}

        async def _apply_planner_reentry_response(self, response, *, session_id):
            self.applied = (response, session_id)
            return "planner_reentry_applied"

    host = Host()
    statuses = asyncio.run(drain_due_time_conditions_once(host, now_ms=2_000))

    assert statuses == ["planner_reentry_applied"]
    assert host.reentry is not None
    assert host.reentry["phase"] == "time_condition_reentry"
    assert host.reentry["goal_ids"] == ["goal-reminder"]
    assert host.reentry["evidence_goal_ids"] == []
    assert host.reentry["evidence_refs"] == []
    assert host.reentry["responsibilities_override"][0].local_ref == "resp-reminder"
    assert host.applied == ({"planner": "response"}, None)
