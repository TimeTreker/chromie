import pytest
from pydantic import ValidationError

from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import OllamaUserMeaningInterpreter
from agent.app.goal_association import GoalAssociationResolver
from orchestrator.runtime.cognitive_runtime import (
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
    CoreInterpretationResult,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.social_cognition import SocialCognitionResolution
from tests.test_cognitive_runtime_pr7 import FakeRuntime, RecordingPlannerAdapter, admitted_core, body_goal_association


def test_turn_local_scope_is_semantic_and_speech_only() -> None:
    item = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Acknowledge the conversation.",
        output_mode="speech",
        continuity_scope="turn",
        confidence=1.0,
    )
    assert item.continuity_scope == "turn"

    with pytest.raises(ValidationError):
        CognitiveResponsibilityProposal(
            local_ref="r1",
            outcome="Walk forward.",
            output_mode="body_action",
            continuity_scope="turn",
            confidence=1.0,
        )


def test_umi_binding_evidence_wrapper_is_not_part_of_semantic_value() -> None:
    item = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Nod your head five times.",
        output_mode="body_action",
        continuity_scope="goal",
        bindings={"count": {"value": 5, "source_evidence": "t3"}},
        confidence=1.0,
    )
    assert item.bindings == {"count": 5}


def test_umi_structured_semantic_binding_is_not_flattened() -> None:
    structured = {"value": 5, "unit": "times", "source_evidence": "t3"}
    item = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Nod your head five times.",
        output_mode="body_action",
        continuity_scope="goal",
        bindings={"count": structured},
        confidence=1.0,
    )
    assert item.bindings["count"] == structured


def test_live_user_meaning_interpreter_schema_requires_continuity_scope() -> None:
    schema = OllamaUserMeaningInterpreter._user_meaning_interpretation_response_schema(
        admitted_turn="Yeah."
    )
    item = schema["$defs"]["CognitiveResponsibilityProposal"]
    assert "oneOf" in item
    speech_branch = next(
        branch for branch in item["oneOf"]
        if branch["properties"]["output_mode"].get("const") == "speech"
    )
    work_branch = next(
        branch for branch in item["oneOf"]
        if "enum" in branch["properties"]["output_mode"]
    )
    assert "continuity_scope" in speech_branch["required"]
    assert speech_branch["properties"]["continuity_scope"]["enum"] == ["turn", "goal"]
    assert work_branch["properties"]["continuity_scope"]["const"] == "goal"
    scope_help = speech_branch["properties"]["continuity_scope"]["description"]
    mode_help = speech_branch["properties"]["output_mode"]["description"]
    assert "lifetime" in scope_help
    assert "not routing" in scope_help
    assert "immediate interaction" in scope_help
    assert "continuity_scope=goal" in mode_help


def test_weather_and_body_work_cannot_be_turn_local() -> None:
    for output_mode, outcome in (
        ("information", "Provide today's Chongqing weather."),
        ("body_action", "Nod your head three times."),
    ):
        with pytest.raises(ValidationError, match="turn-local Responsibility"):
            CognitiveResponsibilityProposal(
                local_ref="r1",
                outcome=outcome,
                output_mode=output_mode,
                continuity_scope="turn",
                confidence=1.0,
            )


@pytest.mark.asyncio
async def test_goal_association_materializes_unassociated_turn_speech_as_interaction_goal() -> None:
    request = CognitiveWorkRequest(
        sid="turn-local-ga",
        text="Yeah.",
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1",
            outcome="Acknowledge the conversation.",
            output_mode="speech",
            continuity_scope="turn",
            confidence=1.0,
        )],
        interpretation_confidence=1.0,
    )

    class Model:
        async def generate(self, *args, **kwargs):
            return {
                "decision": "no_goal",
                "unassociated_responsibility_refs": ["r1"],
                "referent_updates": [],
                "resolved_references": [],
                "confidence": 1.0,
                "reason_summary": "The conversational turn is complete without Goal state.",
            }

    result = await GoalAssociationResolver(Model()).resolve(request)
    assert result.resolution_status == "resolved"
    assert result.non_goal_responsibility_refs == []
    assert len(result.new_goals) == 1
    assert result.new_goals[0].source_responsibility_refs == ["r1"]
    assert result.new_goals[0].metadata["goal_lifetime"] == "interaction"
    assert result.associations == []


class TurnLocalAgent:
    def __init__(self) -> None:
        self.social_requests = []
        self.goal_association_calls = 0

    async def resolve_social_cognition(self, session, *, request, timeout_ms):
        del session, timeout_ms
        self.social_requests.append(request)
        return SocialCognitionResolution(
            request_id=request.request_id,
            snapshot_digest=request.snapshot_digest(),
            disposition="communicate",
            activities=[{
                "activity_id": "sc:turn-local:0",
                "text": "Got it.",
                "function": "respond",
                "truth_stage": "context_grounded",
                "delivery_phase": "immediate",
                "source_goal_ids": [],
                "source_responsibility_refs": ["r1"],
                "evidence_refs": [],
                "addressed_need_ids": [],
            }],
            reason_summary="Complete the turn-local conversational responsibility.",
            need_outcomes={},
            model_call_count=1,
        )

    async def resolve_goal_association(self, *args, **kwargs):
        self.goal_association_calls += 1
        return GoalAssociationResolution(
            turn_id="turn-local-ga",
            resolution_status="resolved",
            non_goal_responsibility_refs=["r1"],
            confidence=1.0,
            reason_summary="No canonical Goal is needed after continuity inspection.",
        )

    async def stream_fast_advance(self, *args, **kwargs):
        raise AssertionError("turn-local interaction must not invoke Fast Planner")
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_turn_local_interaction_returns_social_response_without_goal_or_planner() -> None:
    agent = TurnLocalAgent()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent,
        adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=lambda *args, **kwargs: [],
    )
    core, envelope = admitted_core(
        "Yeah.",
        sid="turn-local-runtime",
        language="en-US",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "Acknowledge the conversation.",
            "bindings": {},
            "output_mode": "speech",
            "continuity_scope": "turn",
            "confidence": 1.0,
        }],
    )
    result = await coordinator.resolve(
        object(),
        text="Yeah.",
        sid="turn-local-runtime",
        core_interpretation=core,
        turn_envelope=envelope,
        context={"history": []},
        history=[],
        language="en-US",
    )
    assert result.status == "applied", result.fallback_reason
    assert result.goal_association is not None
    assert result.goal_association.non_goal_responsibility_refs == ["r1"]
    assert result.fast_plan is None
    assert result.terminal_plan is None
    assert result.interaction_response is not None
    assert result.interaction_response.speech[0].text == "Got it."
    assert result.metadata["goal_continuity_checked"] is True
    assert result.metadata["planner_avoided_no_goal"] is True
    assert len(agent.social_requests) == 1
    assert agent.goal_association_calls == 1
    assert agent.social_requests[0].context["work_decision_pending"] is True


def test_umi_cognitive_requests_are_required_but_only_non_standing_authorities() -> None:
    schema = OllamaUserMeaningInterpreter._user_meaning_interpretation_response_schema(
        admitted_turn="Check the weather."
    )
    assert "cognitive_requests" in schema["required"]
    assert schema["properties"]["cognitive_requests"]["minItems"] == 0
    activation = schema["$defs"]["CognitiveActivationRequest"]
    assert activation["properties"]["authority"]["enum"] == [
        "goal_association", "planner"
    ]


def test_core_accepts_planner_activation_without_redundant_ga_request() -> None:
    result = CoreInterpretationResult(
        turn_id="turn-activation",
        session_id="sid-activation",
        confidence=1.0,
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "Check the weather.",
            "output_mode": "information",
            "continuity_scope": "goal",
            "confidence": 1.0,
        }],
        cognitive_requests=[{
            "authority": "planner",
            "responsibility_refs": ["r1"],
            "reason_summary": "Current meaning is ready for HOW.",
        }],
    )
    assert [item.authority for item in result.cognitive_requests] == ["planner"]


def test_runtime_closes_planner_goal_association_dependency_without_mutating_umi() -> None:
    request = CognitiveWorkRequest(
        sid="turn-activation",
        text="Check the weather.",
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1",
            outcome="Check the weather.",
            output_mode="information",
            continuity_scope="goal",
            confidence=1.0,
        )],
        cognitive_requests=[{
            "authority": "planner",
            "responsibility_refs": ["r1"],
            "reason_summary": "Current meaning is ready for HOW.",
        }],
    )

    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(
        request, "planner"
    ) == ["r1"]
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(
        request, "goal_association"
    ) == ["r1"]
    assert [item.authority for item in request.cognitive_requests] == ["planner"]


@pytest.mark.asyncio
async def test_goal_scoped_meaning_does_not_wake_planner_without_model_request() -> None:
    class Agent(TurnLocalAgent):
        def __init__(self) -> None:
            super().__init__()
            self.planner_calls = 0

        async def resolve_social_cognition(self, session, *, request, timeout_ms):
            del session, timeout_ms
            self.social_requests.append(request)
            return SocialCognitionResolution(
                request_id=request.request_id,
                snapshot_digest=request.snapshot_digest(),
                disposition="communicate",
                activities=[{
                    "activity_id": "sc:goal-work:ack",
                    "text": "Okay.",
                    "function": "acknowledge",
                    "truth_stage": "context_grounded",
                    "delivery_phase": "immediate",
                    "source_goal_ids": [],
                    "source_responsibility_refs": ["r1"],
                    "evidence_refs": [],
                    "addressed_need_ids": [],
                }],
                reason_summary="Acknowledge the understood request without claiming completion.",
                need_outcomes={},
                model_call_count=1,
            )

        async def resolve_goal_association(self, *args, **kwargs):
            self.goal_association_calls += 1
            return body_goal_association(source_ref="r1")

        async def stream_fast_advance(self, *args, **kwargs):
            self.planner_calls += 1
            raise AssertionError("Runtime must not infer Planner activation from continuity_scope")
            yield  # pragma: no cover

    agent = Agent()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent,
        adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=lambda *args, **kwargs: [],
    )
    core, envelope = admitted_core(
        "Blink your eyes.",
        sid="model-driven-no-planner",
        language="en-US",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "Blink your eyes.",
            "bindings": {},
            "output_mode": "body_action",
            "continuity_scope": "goal",
            "confidence": 1.0,
        }],
        cognitive_requests=[
            {
                "authority": "goal_association",
                "responsibility_refs": ["r1"],
                "reason_summary": "Check canonical continuity.",
            },
        ],
    )
    result = await coordinator.resolve(
        object(), text="Blink your eyes.", sid="model-driven-no-planner",
        core_interpretation=core, turn_envelope=envelope, context={"history": []},
        history=[], language="en-US",
    )
    assert result.status == "applied", result.fallback_reason
    assert result.goal_association is not None
    assert result.terminal_plan is None
    assert agent.planner_calls == 0
    assert result.metadata["planner_not_requested_by_umi"] is True
    assert len(agent.social_requests) == 1


def test_runtime_preserves_turn_local_refs_when_planner_is_model_requested() -> None:
    request = CognitiveWorkRequest(
        sid="turn-local-planner-scope",
        text="Tell me a joke.",
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1",
            outcome="tell a joke",
            output_mode="speech",
            continuity_scope="turn",
            confidence=1.0,
        )],
        cognitive_requests=[{
            "authority": "planner",
            "responsibility_refs": ["r1"],
            "reason_summary": "The small model incorrectly requested Planner.",
        }],
    )
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(
        request, "planner"
    ) == ["r1"]
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(
        request, "goal_association"
    ) == ["r1"]


def test_runtime_preserves_all_model_requested_planner_refs_regardless_lifetime() -> None:
    request = CognitiveWorkRequest(
        sid="mixed-planner-scope",
        text="Tell me a joke, then bring the cup.",
        responsibilities=[
            CognitiveResponsibilityProposal(
                local_ref="r1", outcome="tell a joke", output_mode="speech",
                continuity_scope="turn", confidence=1.0,
            ),
            CognitiveResponsibilityProposal(
                local_ref="r2", outcome="bring the cup", output_mode="body_action",
                body_effect_family="task_physical_effect", continuity_scope="goal", confidence=1.0,
            ),
        ],
        cognitive_requests=[{
            "authority": "planner",
            "responsibility_refs": ["r1", "r2"],
            "reason_summary": "Plan only the Goal-owned work.",
        }],
    )
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(
        request, "planner"
    ) == ["r1", "r2"]
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(
        request, "goal_association"
    ) == ["r1", "r2"]

@pytest.mark.asyncio
async def test_late_ga_failure_cannot_turn_delivered_joke_into_user_visible_failure() -> None:
    class Agent:
        def __init__(self) -> None:
            self.social_calls = 0

        async def resolve_social_cognition(self, session, *, request, timeout_ms):
            del session, timeout_ms
            self.social_calls += 1
            return SocialCognitionResolution(
                request_id=request.request_id,
                snapshot_digest=request.snapshot_digest(),
                disposition="communicate",
                activities=[{
                    "activity_id": "sc:joke:delivered",
                    "text": "Why did the chicken cross the road? To get to the other side!",
                    "function": "respond",
                    "truth_stage": "context_grounded",
                    "delivery_phase": "immediate",
                    "source_goal_ids": [],
                    "source_responsibility_refs": ["r1"],
                    "evidence_refs": [],
                    "addressed_need_ids": [],
                }],
                reason_summary="Fulfill the requested conversational joke.",
                need_outcomes={},
                model_call_count=1,
            )

        async def resolve_goal_association(self, *args, **kwargs):
            return GoalAssociationResolution(
                turn_id="joke-late-ga",
                resolution_status="fail_closed",
                confidence=0.0,
                reason_summary="Invalid late association output.",
                metadata={
                    "status": "model_contract_failed",
                    "failure_class": "structured_output_validation",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "goal_association",
                    "retryable": False,
                },
            )

        async def stream_fast_advance(self, *args, **kwargs):
            raise AssertionError("Planner was not requested in this containment test")
            yield  # pragma: no cover

    agent = Agent()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent,
        adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    core, envelope = admitted_core(
        "Tell me a joke.",
        sid="joke-late-ga",
        language="en-US",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "Tell the user a joke.",
            "bindings": {},
            "output_mode": "speech",
            "continuity_scope": "turn",
            "confidence": 1.0,
        }],
        cognitive_requests=[{
            "authority": "goal_association",
            "responsibility_refs": ["r1"],
            "reason_summary": "Check whether this conversational responsibility continues retained social history.",
        }],
    )
    result = await coordinator.resolve(
        object(), text="Tell me a joke.", sid="joke-late-ga",
        core_interpretation=core, turn_envelope=envelope,
        context={"history": []}, history=[], language="en-US",
    )
    assert result.status == "applied", result.fallback_reason
    assert result.interaction_response is not None
    assert result.interaction_response.speech[0].text.startswith("Why did the chicken")
    assert result.interaction_response.metadata["presentation_already_dispatched"] is True
    assert result.metadata["optional_cognition_failure_after_delivered_interaction"] is True
    assert result.metadata["suppressed_failure_stage"] == "goal_association"
    assert agent.social_calls == 1, "late GA failure must not trigger apology/retry speech"
