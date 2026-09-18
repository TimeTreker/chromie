from types import SimpleNamespace

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
)
from shared.chromie_contracts.social_cognition import SocialCognitionResolution
from tests.test_cognitive_runtime_pr7 import FakeRuntime, RecordingPlannerAdapter, admitted_core


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


def test_live_user_meaning_interpreter_schema_requires_continuity_scope() -> None:
    schema = OllamaUserMeaningInterpreter._user_meaning_interpretation_response_schema(
        admitted_turn="Yeah."
    )
    item = schema["$defs"]["CognitiveResponsibilityProposal"]
    assert "continuity_scope" in item["required"]
    assert set(item["properties"]["continuity_scope"]["enum"]) == {"goal", "turn"}


@pytest.mark.asyncio
async def test_goal_association_rejects_turn_local_responsibility() -> None:
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
    with pytest.raises(ValueError, match="turn-local refs belong to Social Cognition"):
        await GoalAssociationResolver(SimpleNamespace()).resolve(request)


class TurnLocalAgent:
    def __init__(self) -> None:
        self.social_requests = []

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
        raise AssertionError("turn-local interaction must not invoke Goal Association")

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
    assert result.goal_association is None
    assert result.fast_plan is None
    assert result.terminal_plan is None
    assert result.interaction_response is not None
    assert result.interaction_response.speech[0].text == "Got it."
    assert result.metadata["turn_local_interaction"] is True
    assert result.metadata["goal_continuity_skipped"] is True
    assert len(agent.social_requests) == 1
    assert agent.social_requests[0].context["work_decision_pending"] is False
