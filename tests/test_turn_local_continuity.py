import pytest
from pydantic import ValidationError

from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import OllamaUserMeaningInterpreter
from agent.app.goal_association import GoalAssociationResolver
from orchestrator.runtime.cognitive_runtime import (
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
    CoreInterpretationResult,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import FastPlannerStreamFailure
from shared.chromie_contracts.social_cognition import SocialCognitionResolution
from tests.cognitive_runtime_test_support import FakeRuntime, RecordingPlannerAdapter, admitted_core as _admitted_core, body_goal_association, new_goal_association as _new_goal_association


def admitted_core(*args, **kwargs):
    """These direct-interaction fixtures explicitly request continuity, without HOW."""
    refs = [item["local_ref"] for item in kwargs.get("responsibilities") or [{"local_ref": "r1"}]]
    kwargs.setdefault("cognitive_requests", [{"authority": "goal_association", "responsibility_refs": refs}])
    return _admitted_core(*args, **kwargs)


def new_goal_association(*args, **kwargs):
    association = _new_goal_association(*args, **kwargs)
    for goal in association.new_goals:
        goal.metadata.pop("output_mode", None)
    return association


def test_umi_does_not_author_presentation_or_lifetime() -> None:
    item = CognitiveResponsibilityProposal(local_ref="r1", outcome="Acknowledge the conversation.", confidence=1)
    assert item.outcome == "Acknowledge the conversation."
    for field, value in (("continuity_scope", "turn"), ("output_mode", "speech")):
        with pytest.raises(ValidationError, match="Extra inputs"):
            CognitiveResponsibilityProposal.model_validate({**item.model_dump(), field: value})


def test_umi_binding_evidence_wrapper_is_not_part_of_semantic_value() -> None:
    item = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Nod your head five times.",


        bindings={"count": {"value": 5, "source_evidence": "t3"}},
        confidence=1.0,
    )
    assert item.bindings == {"count": 5}


def test_umi_structured_semantic_binding_is_not_flattened() -> None:
    structured = {"value": 5, "unit": "times", "source_evidence": "t3"}
    item = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Nod your head five times.",


        bindings={"count": structured},
        confidence=1.0,
    )
    assert item.bindings["count"] == structured


def test_live_umi_schema_has_complete_meaning_without_lifetime_category() -> None:
    schema = OllamaUserMeaningInterpreter._user_meaning_interpretation_response_schema(admitted_turn="Yeah.")
    item = schema["$defs"]["CognitiveResponsibilityProposal"]
    assert set(item["properties"]) == {"local_ref", "outcome", "value_review", "confidence", "source_evidence"}
    assert set(item["required"]) == set(item["properties"])
    assert item["additionalProperties"] is False


def test_weather_and_body_meaning_do_not_supply_a_lifetime_label() -> None:
    for outcome in ("Provide today's Chongqing weather.", "Nod your head three times."):
        item = CognitiveResponsibilityProposal(local_ref="r1", outcome=outcome, confidence=1)
        assert item.outcome == outcome
        with pytest.raises(ValidationError, match="Extra inputs"):
            CognitiveResponsibilityProposal.model_validate({**item.model_dump(), "continuity_scope": "goal"})


@pytest.mark.asyncio
async def test_goal_association_materializes_unassociated_turn_speech_as_interaction_goal() -> None:
    request = CognitiveWorkRequest(
        sid="turn-local-ga",
        text="Yeah.",
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1",
            outcome="Acknowledge the conversation.",


            confidence=1.0,
        )],
        interpretation_confidence=1.0,
    )

    class Model:
        async def generate(self, *args, **kwargs):
            return {
                "decision": "no_goal",
                "new_goals": [{"source_responsibility_refs": ["r1"], "related_goal_ids": [], "supersedes_goal_ids": []}],
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
    assert "goal_lifetime" not in result.new_goals[0].metadata
    assert result.associations == []


class TurnLocalAgent:
    def __init__(self) -> None:
        self.social_requests = []
        self.goal_association_calls = 0
        self.response_function = "respond"
        self.covers_need = True

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
                "function": self.response_function,
                "truth_stage": "context_grounded",
                "delivery_phase": "immediate",
                "source_goal_ids": [],
                "source_responsibility_refs": ["r1"],
                "evidence_refs": [],
                "addressed_need_ids": [need.need_id for need in request.communication_needs]
                if self.covers_need else [],
            }],
            reason_summary="Complete the turn-local conversational responsibility.",
            need_outcomes={need.need_id: "covered" if self.covers_need else "pending"
                           for need in request.communication_needs},
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

    async def stream_plan_advance(self, *args, **kwargs):
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
    assert agent.social_requests[0].context["work_decision_pending"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("function", ["respond", "acknowledge", "inform", "ask"])
@pytest.mark.parametrize("covered", [True, False])
async def test_delivered_direct_social_response_closes_materialized_interaction_goal(
    function, covered,
) -> None:
    class Agent(TurnLocalAgent):
        async def resolve_goal_association(self, *args, **kwargs):
            del args, kwargs
            return new_goal_association("goal-direct-social")

    state = ConversationStateManager(base_conversation_id="direct-social")
    agent = Agent()
    agent.response_function, agent.covers_need = function, covered
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent,
        adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=state.apply_goal_association_resolution,
        communicative_goal_completion_apply=(
            state.reconcile_communicative_goal_completion
        ),
    )
    core, envelope = admitted_core(
        "Hello.",
        sid="direct-social-turn",
        language="en-US",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "Acknowledge the greeting.",
            "bindings": {},


            "confidence": 1.0,
        }],
    )

    result = await coordinator.resolve(
        object(),
        text="Hello.",
        sid="direct-social-turn",
        core_interpretation=core,
        turn_envelope=envelope,
        context={"history": []},
        history=[],
        language="en-US",
    )

    assert result.status == "applied", result.fallback_reason
    assert result.interaction_response is not None
    assert result.interaction_response.speech[0].text == "Got it."
    assert len(agent.social_requests[0].communication_needs) == 1
    if not covered:
        assert [item["goal_id"] for item in state.active_goal_snapshots()] == ["goal-direct-social"]
        assert result.metadata["direct_social_completion_results"] == []
        return
    assert state.active_goal_snapshots() == []
    recent = state.recent_goal_snapshots()
    assert [item["goal_id"] for item in recent] == ["goal-direct-social"]
    assert recent[0]["responsibility_status"] == "satisfied"
    assert result.metadata["direct_social_completion_results"][0]["changed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("grouped,covered,split_acts", [
    (True, [], False),
    (True, ["r1"], False),
    (True, ["r2"], False),
    (True, ["r1", "r2"], False),
    (True, ["r1", "r2"], True),
    (False, ["r1"], False),
    (False, ["r1", "r2"], True),
])
async def test_social_completion_preserves_all_contributions_to_each_goal(
    grouped, covered, split_acts,
) -> None:
    class Agent(TurnLocalAgent):
        async def resolve_goal_association(self, *args, **kwargs):
            association = new_goal_association("goal-shared" if grouped else "goal-r1")
            if grouped:
                association.new_goals[0].source_responsibility_refs = ["r1", "r2"]
            else:
                second = new_goal_association("goal-r2").new_goals[0]
                second.source_responsibility_refs = ["r2"]
                association.new_goals.append(second)
            return association

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            groups = [[ref] for ref in covered] if split_acts else [covered]
            words = {"r1": "Hello.", "r2": "Why did the math book look sad? Too many problems!"}
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                disposition="communicate", activities=[{
                    "activity_id": f"social-{index}",
                    "text": " ".join(words[ref] for ref in refs) if refs else "Let me think.",
                    "function": "respond" if refs else "acknowledge",
                    "truth_stage": "context_grounded",
                    "source_responsibility_refs": refs or ["r1", "r2"],
                    "addressed_need_ids": [need.need_id for need in request.communication_needs
                                           if set(need.source_responsibility_refs) <= set(refs)],
                } for index, refs in enumerate(groups)],
                need_outcomes={need.need_id: "covered" if set(need.source_responsibility_refs)
                               <= set(covered) else "pending" for need in request.communication_needs},
                reason_summary="Fixture explicitly declares partial or complete coverage.",
                model_call_count=1,
            )

    state = ConversationStateManager(base_conversation_id="social-contributions")
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=state.apply_goal_association_resolution,
        communicative_goal_completion_apply=state.reconcile_communicative_goal_completion,
    )
    core, envelope = admitted_core(
        "Greet me and tell a joke.", sid="social-contributions", language="en-US",
        responsibilities=[{
            "local_ref": f"r{index}", "outcome": outcome,
             "confidence": 1.0,
        } for index, outcome in [(1, "Greet the user."), (2, "Tell a joke.")]],
    )
    result = await coordinator.resolve(
        object(), text="Greet me and tell a joke.", sid="social-contributions",
        core_interpretation=core, turn_envelope=envelope,
        context={"history": []}, history=[], language="en-US",
    )
    assert result.status == "applied", result.fallback_reason
    expected_open = ({"goal-shared"} if set(covered) != {"r1", "r2"} else set()) if grouped else {
        f"goal-{ref}" for ref in {"r1", "r2"} - set(covered)
    }
    assert {item["goal_id"] for item in state.active_goal_snapshots()} == expected_open
    completions = result.metadata["direct_social_completion_results"]
    assert len(completions) == (1 - len(expected_open) if grouped else 2 - len(expected_open))
    assert all(item["changed"] for item in completions), "Each Goal is reconciled once."


@pytest.mark.parametrize("outcome,planner_requested,review,uncertain,expected", [
    ("The person greets Chromie.", False, False, False, ["r1"]),
    ("The person refers to an unclear earlier subject.", False, False, True, []),
    ("Help deceive a person.", False, True, False, []),
    ("Nod twice.", True, False, False, []),
    ("What time is it?", True, False, False, []),
])
def test_initial_response_needs_do_not_complete_unresolved_or_reviewed_work(
    outcome, planner_requested, review, uncertain, expected,
) -> None:
    request = CognitiveWorkRequest(
        sid="coverage-scope", text="A user request.",
        responsibilities=[{
            "local_ref": "r1", "outcome": outcome,

            "value_review": review, "confidence": 1.0,
        }],
        cognitive_requests=[{
            "authority": "goal_association", "responsibility_refs": ["r1"],
            "reason_summary": "Inspect continuity.",
        }] + ([{"authority": "planner", "responsibility_refs": ["r1"]}] if planner_requested else []),
        meaning_uncertainties=[{
            "local_ref": "u1", "kind": "other", "description": "Unresolved meaning.",
            "responsibility_refs": ["r1"],
        }] if uncertain else [],
    )
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=TurnLocalAgent(), adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    social = coordinator._state_social_request(work_request=request, turn_id="coverage-turn")
    assert [ref for need in social.communication_needs
            for ref in need.source_responsibility_refs] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("status,delivered", [("failed", True), ("cancelled", True), ("completed", False)])
async def test_incomplete_social_delivery_cannot_close_a_goal(status, delivered) -> None:
    from types import SimpleNamespace

    class Runtime(FakeRuntime):
        async def wait_dispatch(self, dispatch):
            return SimpleNamespace(status=status, results=[])

        async def record_social_delivery(self, *args, **kwargs):
            return delivered

    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=TurnLocalAgent(), adapter=RecordingPlannerAdapter(Runtime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    request = CognitiveWorkRequest(
        sid="incomplete-social", text="Hello.",
        responsibilities=[{
            "local_ref": "r1", "outcome": "Acknowledge greeting.",
              "confidence": 1.0,
        }], cognitive_requests=[{
            "authority": "goal_association", "responsibility_refs": ["r1"],
            "reason_summary": "Inspect continuity.",
        }],
    )
    task = coordinator.start_state_interaction(object(), work_request=request, turn_id="incomplete-turn")
    with pytest.raises(RuntimeError, match="social_interaction_delivery_failed"):
        await task


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
                    "addressed_need_ids": [need.need_id for need in request.communication_needs],
                }],
                reason_summary="Acknowledge the understood request without claiming completion.",
                need_outcomes={need.need_id: "covered" for need in request.communication_needs},
                model_call_count=1,
            )

        async def resolve_goal_association(self, *args, **kwargs):
            self.goal_association_calls += 1
            return body_goal_association(source_ref="r1")

        async def stream_plan_advance(self, *args, **kwargs):
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
                local_ref="r1", outcome="tell a joke",
                 confidence=1.0,
            ),
            CognitiveResponsibilityProposal(
                local_ref="r2", outcome="bring the cup",
                  confidence=1.0,
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
@pytest.mark.parametrize("function", ["respond", "inform", "ask"])
@pytest.mark.parametrize("complete", [False, True])
async def test_pending_primary_answer_never_hides_late_cognition_failure(function, complete):
    from tests.cognitive_runtime_test_support import ScriptedClient

    class Agent(ScriptedClient):
        def __init__(self):
            super().__init__(association=GoalAssociationResolution(
                turn_id="partial-failure", resolution_status="fail_closed", confidence=0,
                reason_summary="Invalid association.", metadata={
                    "status": "model_contract_failed", "failure_class": "structured_output_validation",
                    "failure_domain": "model_contract", "architecture_attribution": "goal_association",
                    "retryable": False,
                },
            ), fast_plans=[])

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            if request.trigger != "interpretation":
                result = await super().resolve_social_cognition(session, request=request, **kwargs)
                return result.model_copy(update={"activities": [
                    act.model_copy(update={"text": "I couldn't finish the remaining request."})
                    for act in result.activities
                ]})
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                disposition="communicate", activities=[{
                    "activity_id": "partial-reply", "function": function,
                    "text": "Hello. Why did the math book look sad? Too many problems!" if complete
                    else "Hello. Which kind of joke would you like?" if function == "ask" else "Hello.",
                    "truth_stage": "context_grounded", "source_responsibility_refs": ["r1", "r2"],
                    "addressed_need_ids": [need.need_id for need in request.communication_needs
                                           if complete or need.source_responsibility_refs == ["r1"]],
                }], need_outcomes={need.need_id: "covered" if complete
                                   or need.source_responsibility_refs == ["r1"] else "pending"
                                   for need in request.communication_needs},
                reason_summary="Explicit coverage, independent of broader activity scope.", model_call_count=1,
            )

    core, envelope = admitted_core(
        "Greet me and tell a joke.", sid="partial-failure", language="en-US",
        responsibilities=[{
            "local_ref": f"r{index}", "outcome": outcome,
             "confidence": 1.0,
        } for index, outcome in [(1, "Greet the user."), (2, "Tell a joke.")]],
    )
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    result = await coordinator.resolve(
        object(), text="Greet me and tell a joke.", sid="partial-failure",
        core_interpretation=core, turn_envelope=envelope,
        context={"history": []}, history=[], language="en-US",
    )
    if complete:
        assert result.status == "applied"
        assert result.metadata["optional_cognition_failure_after_delivered_interaction"] is True
    else:
        assert result.status == "error"
        assert "optional_cognition_failure_after_delivered_interaction" not in result.metadata
        assert result.metadata["failure_stage"] == "goal_association"
        assert "couldn't finish" in result.interaction_response.speech[0].text


@pytest.mark.asyncio
async def test_delivered_meaning_question_still_contains_optional_ga_failure():
    from tests.cognitive_runtime_test_support import ScriptedClient

    class Agent(ScriptedClient):
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            assert request.communication_needs == [], "Unresolved meaning has no answer coverage to certify."
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                disposition="communicate", activities=[{
                    "activity_id": "meaning-question", "text": "What are you referring to?",
                    "function": "ask", "truth_stage": "context_grounded",
                    "source_responsibility_refs": ["r1"],
                }], need_outcomes={}, reason_summary="Ask about the supplied meaning uncertainty.",
                model_call_count=1,
            )

    agent = Agent(association=GoalAssociationResolution(
        turn_id="meaning-question", resolution_status="fail_closed", confidence=0, metadata={
            "status": "model_contract_failed", "failure_class": "structured_output_validation",
            "failure_domain": "model_contract", "architecture_attribution": "goal_association",
            "retryable": False,
        },
    ), fast_plans=[])
    core, envelope = admitted_core(
        "Tell me about that.", sid="meaning-question", language="en-US",
        responsibilities=[{"local_ref": "r1", "outcome": "Respond about the referenced topic.",
                             "confidence": 1.0}],
        meaning_uncertainties=["The topic referred to by that is unknown."],
    )
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent, adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    result = await coordinator.resolve(
        object(), text="Tell me about that.", sid="meaning-question", core_interpretation=core,
        turn_envelope=envelope, context={"history": []}, history=[], language="en-US",
    )
    assert result.status == "applied", result.fallback_reason
    assert result.metadata["optional_cognition_failure_after_delivered_interaction"] is True
    assert result.interaction_response.speech[0].text == "What are you referring to?"


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
                    "addressed_need_ids": [need.need_id for need in request.communication_needs],
                }],
                reason_summary="Fulfill the requested conversational joke.",
                need_outcomes={need.need_id: "covered" for need in request.communication_needs},
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

        async def stream_plan_advance(self, *args, **kwargs):
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

@pytest.mark.asyncio
@pytest.mark.parametrize("progress", ["think", "acknowledge_work"])
async def test_pending_planner_failure_is_reported_after_delivered_receipt(progress) -> None:
    """A receipt never hides failure of the separately requested HOW decision."""
    class Agent:
        def __init__(self) -> None:
            self.social_calls = 0

        async def resolve_social_cognition(self, session, *, request, timeout_ms):
            del session, timeout_ms
            self.social_calls += 1
            if request.trigger != "interpretation":
                return SocialCognitionResolution(
                    request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                    disposition="communicate", activities=[{
                        "activity_id": "planner-failed", "text": "I couldn't finish that request.",
                        "function": "inform", "truth_stage": "post_evidence",
                        "source_responsibility_refs": ["r1"],
                        "addressed_need_ids": [need.need_id for need in request.communication_needs],
                    }], need_outcomes={need.need_id: "covered" for need in request.communication_needs},
                    model_call_count=1,
                )
            return SocialCognitionResolution(
                request_id=request.request_id,
                snapshot_digest=request.snapshot_digest(),
                disposition="communicate",
                activities=[{
                    "activity_id": "sc:identity:delivered",
                    "text": "Let me think." if progress == "think" else "Got it.",
                    "function": "acknowledge",
                    "truth_stage": "pre_evidence",
                    "progress_kind": progress,
                    "delivery_phase": "immediate",
                    "source_goal_ids": [],
                    "source_responsibility_refs": ["r1"],
                    "evidence_refs": [],
                    "addressed_need_ids": [],
                }],
                reason_summary="Answer the current identity question.",
                need_outcomes={need.need_id: "pending"
                               for need in request.communication_needs},
                model_call_count=1,
            )

        async def resolve_goal_association(self, *args, **kwargs):
            del args, kwargs
            return new_goal_association("goal-identity")

        async def stream_plan_advance(self, session, *, request, timeout_ms):
            del session, timeout_ms
            yield FastPlannerStreamFailure(
                turn_id=request.sid,
                failure_stage="before_commit",
                failure_class="fast_stream_contract_invalid",
                failure_domain="model_contract",
                architecture_attribution="fast_planner",
                retryable=False,
                reason="Invalid Planner result.",
            )

    agent = Agent()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent,
        adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    core, envelope = admitted_core(
        "who are you?",
        sid="identity-late-fast",
        language="en-US",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "answer who I am",
            "bindings": {},


            "confidence": 1.0,
        }],
        cognitive_requests=[
            {
                "authority": "goal_association",
                "responsibility_refs": ["r1"],
                "reason_summary": "Check continuity.",
            },
            {
                "authority": "planner",
                "responsibility_refs": ["r1"],
                "reason_summary": "Plan the response HOW.",
            },
        ],
    )
    result = await coordinator.resolve(
        object(), text="who are you?", sid="identity-late-fast",
        core_interpretation=core, turn_envelope=envelope,
        context={"history": []}, history=[], language="en-US",
    )
    assert result.status == "error"
    assert "optional_cognition_failure_after_delivered_interaction" not in result.metadata
    assert result.metadata["failure_stage"] == "fast_planner_stream"
    assert agent.social_calls == 2, "A delivered receipt must be followed by the failure notification."


@pytest.mark.asyncio
@pytest.mark.parametrize("information_request", [True, False])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
async def test_late_sc_failure_after_receipt_requires_failure_notification(
    information_request, error_type,
) -> None:
    from shared.chromie_contracts.plan import CanonicalPlan
    from tests.cognitive_runtime_test_support import ScriptedClient, respond_plan

    goal_id = "goal-late-sc"
    association = new_goal_association(goal_id) if information_request else body_goal_association(goal_id)
    plan = respond_plan(goal_id) if information_request else CanonicalPlan(
        plan_id="unavailable-body", planner_tier="fast", disposition="unavailable",
        coverage="uncertain", confidence=1.0, goal_ids=[goal_id],
        goal_summary="The requested body effect is unavailable.",
        unresolved=["No executable body Work is available."],
    )

    class Agent(ScriptedClient):
        def __init__(self):
            super().__init__(association=association, fast_plans=[plan])
            self.social_calls = 0
            self.social_words[goal_id] = "An internal error prevented completion."

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            self.social_calls += 1
            if request.trigger == "interpretation":
                return SocialCognitionResolution(
                    request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                    disposition="communicate", activities=[{
                        "activity_id": "initial-reply", "text": "Hello." if information_request else "Okay.",
                        "function": "acknowledge",
                        "truth_stage": "pre_evidence",
                        "progress_kind": "think",
                        "source_responsibility_refs": ["r1"],
                        "addressed_need_ids": [need.need_id for need in request.communication_needs],
                    }], need_outcomes={need.need_id: "covered" for need in request.communication_needs},
                    reason_summary="Initial interaction.", model_call_count=1,
                )
            if self.social_calls == 2:
                raise error_type("Agent Social Cognition HTTP 422: raw Schema rejected")
            return await super().resolve_social_cognition(session, request=request, **kwargs)

    agent = Agent()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent, adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    text = "Hello." if information_request else "Blink twice."
    core, envelope = admitted_core(
        text, sid="late-sc", language="en-US", responsibilities=[{
            "local_ref": "r1", "outcome": "Greet the user." if information_request else "Blink twice.",

             "confidence": 1.0,
        }], cognitive_requests=[{
            "authority": "planner", "responsibility_refs": ["r1"],
            "reason_summary": "Determine the requested HOW.",
        }],
    )
    result = await coordinator.resolve(
        object(), text=text, sid="late-sc", core_interpretation=core, turn_envelope=envelope,
        context={"history": []}, history=[], language="en-US",
    )
    assert result.status == "error"
    assert result.metadata["failure_stage"] == "social_cognition"
    assert "optional_cognition_failure_after_delivered_interaction" not in result.metadata
    assert agent.social_calls == 3, "A receipt does not complete the pending request."
    assert result.interaction_response.capabilities == []


# A still-open Goal a new Goal may be related to; a link to a finished Goal changes nothing a
# running Planner reads (2026-10-25).
EARLIER_OPEN_GOAL = {"goal_id": "goal-earlier", "responsibility_status": "open"}


@pytest.mark.asyncio
@pytest.mark.parametrize("information_request", [True, False])
async def test_silent_goal_update_cannot_complete_work_after_a_receipt(information_request):
    import asyncio
    from orchestrator.runtime.cognitive_runtime import CognitiveStageFailure
    from tests.cognitive_runtime_test_support import ScriptedClient, respond_plan

    goal_id = "goal-silent-state"
    association = new_goal_association(goal_id) if information_request else body_goal_association(goal_id)
    data = association.model_dump(mode="json")
    data["cognitive_requests"] = [
        {"authority": "planner", "responsibility_refs": ["r1"],
         "reason_summary": "Check canonical Work."},
        {"authority": "social_cognition", "responsibility_refs": ["r1"],
         "reason_summary": "Observe Goal state."},
    ]
    # GA relates the new Goal to a still-open Goal, so its requests are new cognition;
    # an unchanged GA result would join the running plan instead (no late GA failure).
    data["new_goals"][0]["related_goal_ids"] = ["goal-earlier"]
    association = type(association).model_validate(data)

    class Agent(ScriptedClient):
        def __init__(self):
            super().__init__(association=association, fast_plans=[respond_plan(goal_id)])
            self.social_calls = 0
            self.state_seen = asyncio.Event()

        async def resolve_plan(self, *args, **kwargs):
            await self.state_seen.wait()
            raise CognitiveStageFailure("fast_planner", {
                "failure_class": "structured_output_validation",
                "failure_domain": "model_contract", "retryable": False,
            })

        async def stream_plan_advance(self, *args, **kwargs):
            # The first plan fails too: a valid first plan would now be retained
            # (IndependentPlanningTests), so only a late failure of every plan
            # exercises the delivered-response containment this test protects.
            from shared.chromie_contracts.plan import FastPlannerStreamFailure
            yield FastPlannerStreamFailure(
                turn_id=kwargs["request"].sid, failure_stage="before_commit",
                failure_class="structured_output_validation", failure_domain="model_contract",
            )

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            self.social_calls += 1
            if request.trigger == "interpretation":
                return SocialCognitionResolution(
                    request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                    disposition="communicate", activities=[{
                        "activity_id": "initial-delivered",
                        "text": "Let me think." if information_request else "Okay.",
                        "function": "acknowledge",
                        "truth_stage": "pre_evidence",
                        "progress_kind": "think",
                        "source_responsibility_refs": ["r1"],
                        "addressed_need_ids": [need.need_id for need in request.communication_needs],
                    }], need_outcomes={need.need_id: "covered" for need in request.communication_needs},
                    reason_summary="Initial interaction.", model_call_count=1,
                )
            if request.trigger == "goal_state":
                self.state_seen.set()
                return SocialCognitionResolution(
                    request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                    disposition="silence", activities=[], need_outcomes={},
                    reason_summary="Prior response delivered; no new interaction.", model_call_count=1,
                )
            return await super().resolve_social_cognition(session, request=request, **kwargs)

    agent = Agent()
    state = ConversationStateManager(base_conversation_id="silent-state")
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent, adapter=RecordingPlannerAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=state.apply_goal_association_resolution,
        communicative_goal_completion_apply=state.reconcile_communicative_goal_completion,
    )
    text = "I am thirsty, can you help?" if information_request else "Blink twice."
    core, envelope = admitted_core(
        text, sid="silent-state", language="en-US", responsibilities=[{
            "local_ref": "r1", "outcome": "Address thirst help." if information_request else text,

             "confidence": 1.0,
        }], cognitive_requests=[{
            "authority": "planner", "responsibility_refs": ["r1"],
            "reason_summary": "Determine HOW.",
        }],
    )
    result = await asyncio.wait_for(coordinator.resolve(
        object(), text=text, sid="silent-state", core_interpretation=core,
        turn_envelope=envelope, context={"history": [], "active_goal_snapshots": [EARLIER_OPEN_GOAL]},
        history=[], language="en-US",
    ), 3)
    assert result.status == "error"
    assert result.metadata["failure_stage"] == "fast_planner"
    assert "optional_cognition_failure_after_delivered_interaction" not in result.metadata
    assert agent.social_calls == 3
    assert result.interaction_response.capabilities == []
    assert state.active_goal_snapshots()[0]["responsibility_status"] == "open"


@pytest.mark.asyncio
@pytest.mark.parametrize("asked", [True, False])
async def test_goal_state_waits_for_the_answer_to_an_ingress_question(asked):
    """A question asked at ingress stands until the person answers (live 2026-10-22).

    Chromie asked "你是说那个牛奶瓶吗？"; GA then related the Goal to the earlier turn and its
    goal_state SC said "是的，就是那个。", reading Chromie's own question as the answer.
    """
    import asyncio
    from shared.chromie_contracts.plan import FastPlannerAdvance, FastPlannerInputNeed
    from tests.cognitive_runtime_test_support import ScriptedClient

    goal_id = "goal-that-bottle"
    data = body_goal_association(goal_id).model_dump(mode="json")
    data["cognitive_requests"] = [{"authority": "social_cognition", "responsibility_refs": ["r1"],
                                   "reason_summary": "Observe Goal state."}]
    data["new_goals"][0]["related_goal_ids"] = ["goal-earlier"]
    association = GoalAssociationResolution.model_validate(data)
    delivered = asyncio.Event()

    class Runtime(FakeRuntime):
        async def record_social_delivery(self, *args, **kwargs):
            delivered.set()
            return True

    class Agent(ScriptedClient):
        async def resolve_goal_association(self, *args, **kwargs):
            # GA commits after the ingress reply was delivered, as in the live turn.
            await delivered.wait()
            return await super().resolve_goal_association(*args, **kwargs)

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            if request.trigger != "interpretation":
                return await super().resolve_social_cognition(session, request=request, **kwargs)
            self.social_requests.append(request)
            act = ({"text": "你是说那个牛奶瓶吗？", "function": "ask", "truth_stage": "context_grounded"}
                   if asked else
                   {"text": "好的。", "function": "acknowledge", "truth_stage": "pre_evidence",
                    "progress_kind": "acknowledge_work"})
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                disposition="communicate",
                activities=[{"activity_id": "ingress", "source_responsibility_refs": ["r1"], **act}],
                need_outcomes={}, reason_summary="Ingress reply.", model_call_count=1,
            )

    gap = {
        "gap_id": "gap-bottle", "description": "Which bottle should be brought?", "blocking": True,
        "required_for": ["object"], "preferred_resolution": "ask_user", "source_kind": "unresolved_meaning",
        "source_reference": "u1", "resolution_sources_considered": ["authoritative_context"],
    }
    agent = Agent(association=association, fast_plans=[], fast_advances=[FastPlannerAdvance(
        turn_id="turn-that-bottle", disposition="clarify", coverage="uncertain",
        covered_responsibility_refs=["r1"], confidence=0.9, unresolved=["u1"],
        activities=[FastPlannerInputNeed(activity_id="ask-bottle", role="clarification",
                                         information_gaps=[gap], source_responsibility_refs=["r1"])],
        reason_summary="Which bottle is meant is unresolved.",
    )])
    state = ConversationStateManager(base_conversation_id="that-bottle")
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=agent, adapter=RecordingPlannerAdapter(Runtime()),
        policy=CognitiveRuntimePolicy(mode="apply"),
        goal_state_apply=state.apply_goal_association_resolution,
        communicative_goal_completion_apply=state.reconcile_communicative_goal_completion,
    )
    text = "把那个拿给我"
    core, envelope = admitted_core(
        text, sid="that-bottle", language="zh-CN",
        responsibilities=[{"local_ref": "r1", "outcome": "把那个瓶子拿给说话的人",
                            "confidence": 0.9}],
        meaning_uncertainties=["那个 could be the water bottle or the milk bottle."],
    )
    await asyncio.wait_for(coordinator.resolve(
        object(), text=text, sid="that-bottle", core_interpretation=core,
        turn_envelope=envelope, context={"history": [], "active_goal_snapshots": [EARLIER_OPEN_GOAL]},
        history=[], language="zh-CN",
    ), 3)
    triggers = [request.trigger for request in agent.social_requests]
    assert triggers[0] == "interpretation"
    assert ("goal_state" in triggers) is not asked, triggers


def test_umi_risk_review_is_required_without_a_result_category() -> None:
    schema = OllamaUserMeaningInterpreter._user_meaning_interpretation_response_schema(admitted_turn="Please help.")
    meaning = schema["$defs"]["CognitiveResponsibilityProposal"]
    assert "value_review" in meaning["required"]
    assert meaning["properties"]["value_review"]["type"] == "boolean"
    assert not {"output_mode", "continuity_scope", "body_effect_family"} & set(meaning["properties"])


def test_umi_standing_activation_is_rejected_at_parser_and_shared_boundaries():
    import json
    from agent.app.cognitive_core.user_meaning_interpreter.schema import UserMeaningInterpretationRequest
    wire = {"confidence": 1, "responsibilities": [{
        "local_ref": "r1", "outcome": "Hello.", "value_review": False, "confidence": 1,
        "source_evidence": {"source_start_token_ref": "t0", "source_end_token_ref": "t1"},
    }], "meaning_uncertainties": []}
    wire['cognitive_requests'] = [{'authority': 'social_cognition', 'responsibility_refs': ['r1']}]
    with pytest.raises(ValueError, match='non-standing'):
        OllamaUserMeaningInterpreter._validate_interpretation_content(
            UserMeaningInterpretationRequest(text='Hello.'), json.dumps(wire))
    with pytest.raises(ValidationError, match='non-standing'):
        CoreInterpretationResult(turn_id='standing', session_id='standing', confidence=1,
            responsibilities=wire['responsibilities'], cognitive_requests=wire['cognitive_requests'])
