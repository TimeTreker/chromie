from __future__ import annotations

import asyncio

from agent.app.reflection import ReflectionResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.reflection import ReflectionResolution
from shared.chromie_contracts.situation import CognitiveOpportunity


class FakeOllama:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    async def generate(self, *args, **kwargs):
        self.calls += 1
        return self.payload


def request_for(opportunity: CognitiveOpportunity) -> AgentRunRequest:
    return AgentRunRequest(
        sid="sid-reflect",
        text="Please keep trying.",
        route_decision=RouteDecision(
            route="robot_action",
            intent="selective_reflection",
            confidence=1.0,
            source="llm",
            language="en-US",
        ),
        context={
            "cognitive_opportunity": opportunity.prompt_projection(),
            "execution_outcome_bundle": {
                "outcome_id": opportunity.evidence_refs[0],
                "goal_outcomes": [],
            },
            "active_goal_snapshots": [{"goal_id": opportunity.goal_ids[0]}],
        },
    )


def test_fast_opportunity_does_not_invoke_slow_reflection_model() -> None:
    opportunity = CognitiveOpportunity.create(
        trigger="execution_outcome",
        goal_ids=["goal-weather"],
        evidence_refs=["outcome-1", "evidence-1"],
        reason_codes=["temporary_read_failure"],
        recommended_cognition="fast",
    )
    ollama = FakeOllama({"actions": ["replan"]})

    result = asyncio.run(ReflectionResolver(ollama).resolve(request_for(opportunity)))

    assert ollama.calls == 0
    assert result.actions == []
    assert result.goal_ids == ["goal-weather"]
    assert result.evidence_refs == ["outcome-1", "evidence-1"]


def test_slow_reflection_model_cannot_choose_grounding_references() -> None:
    opportunity = CognitiveOpportunity.create(
        trigger="execution_outcome",
        goal_ids=["goal-arm"],
        evidence_refs=["outcome-2", "evidence-2"],
        reason_codes=["grasp_failed"],
        recommended_cognition="slow",
    )
    ollama = FakeOllama(
        {
            "actions": ["replan", "propose_memory"],
            "memory_candidates": [
                {
                    "scope": "task",
                    "kind": "experience",
                    "text": "This manipulation route has repeatedly failed under the current conditions.",
                    "confidence": 0.9,
                }
            ],
            "reason_summary": "Try another route and retain the pattern only if it repeats.",
        }
    )

    result = asyncio.run(ReflectionResolver(ollama).resolve(request_for(opportunity)))

    assert ollama.calls == 1
    assert result.goal_ids == ["goal-arm"]
    assert result.evidence_refs == ["outcome-2", "evidence-2"]
    assert result.actions == ["replan", "propose_memory"]


def test_reflection_replans_without_changing_responsibility_and_promotes_only_repeated_memory() -> None:
    manager = ConversationStateManager(base_conversation_id="reflection")
    manager.apply_semantic_task_operations_atomically(
        [
            {
                "operation_id": "create-goal",
                "operation": "create",
                "goal": {
                    "goal_id": "goal-arm",
                    "description": "Bring the cup.",
                    "source_text": "Bring the cup.",
                },
            }
        ],
        sid="sid-create",
        user_text="Bring the cup.",
    )
    context = manager._task_context_by_goal_id("goal-arm")
    assert context is not None

    def record(outcome_id: str, evidence_id: str) -> None:
        context["evidence_summary"] = {
            "execution_outcome": {
                "outcome_id": outcome_id,
                "turn_id": f"turn-{outcome_id}",
                "evidence_ids": [evidence_id],
                "status": "failed",
            }
        }

    record("outcome-1", "evidence-1")
    first = ReflectionResolution(
        opportunity_id="opportunity-1",
        goal_ids=["goal-arm"],
        evidence_refs=["outcome-1", "evidence-1"],
        reason_codes=["grasp_failed"],
        actions=["replan", "propose_memory"],
        memory_candidates=[
            {
                "scope": "task",
                "kind": "experience",
                "text": "The current grasp route repeatedly fails.",
                "confidence": 0.9,
            }
        ],
        reason_summary="Try another manipulation route.",
    )
    first_result = manager.apply_reflection_resolution(first, sid="sid-1")

    assert first_result[0]["memory_promoted"] == 0
    assert context["semantic_goal"]["responsibility_status"] == "open"
    assert context["plan_status"] == "reflection_future_replan_requested"
    assert not any(
        item["kind"] == "experience"
        for item in manager.snapshot()["extracted_memory"]
    )

    record("outcome-2", "evidence-2")
    second = first.model_copy(
        update={
            "opportunity_id": "opportunity-2",
            "evidence_refs": ["outcome-2", "evidence-2"],
        }
    )
    second_result = manager.apply_reflection_resolution(second, sid="sid-2")

    assert second_result[0]["memory_promoted"] == 1
    assert context["semantic_goal"]["responsibility_status"] == "open"
    experience = [
        item
        for item in manager.snapshot()["extracted_memory"]
        if item["kind"] == "experience"
    ]
    assert len(experience) == 1
    assert experience[0]["persistence_policy"] == "ephemeral"
    assert manager.snapshot()["durable_profile_memory"]["entries"] == []


def test_slow_reflection_without_trusted_evidence_does_not_invoke_model() -> None:
    opportunity = CognitiveOpportunity.create(
        trigger="execution_outcome",
        goal_ids=["goal-arm"],
        evidence_refs=[],
        reason_codes=["grasp_failed"],
        recommended_cognition="slow",
    )
    ollama = FakeOllama({"actions": ["replan"]})
    request = AgentRunRequest(
        sid="sid-reflect-no-evidence",
        text="Please keep trying.",
        route_decision=RouteDecision(
            route="robot_action",
            intent="selective_reflection",
            confidence=1.0,
            source="llm",
            language="en-US",
        ),
        context={
            "cognitive_opportunity": opportunity.prompt_projection(),
            "execution_outcome_bundle": {},
            "active_goal_snapshots": [{"goal_id": "goal-arm"}],
        },
    )

    result = asyncio.run(ReflectionResolver(ollama).resolve(request))

    assert ollama.calls == 0
    assert result.actions == []
    assert "trusted evidence" in result.reason_summary


def test_reflection_cannot_reopen_completed_outcome() -> None:
    manager = ConversationStateManager(base_conversation_id="reflection-completed")
    manager.apply_semantic_task_operations_atomically(
        [
            {
                "operation_id": "create-goal",
                "operation": "create",
                "goal": {
                    "goal_id": "goal-arm-complete",
                    "description": "Bring the cup.",
                    "source_text": "Bring the cup.",
                },
            }
        ],
        sid="sid-create-complete",
        user_text="Bring the cup.",
    )
    context = manager._task_context_by_goal_id("goal-arm-complete")
    assert context is not None
    context["evidence_summary"] = {
        "execution_outcome": {
            "outcome_id": "outcome-complete",
            "turn_id": "turn-complete",
            "evidence_ids": ["evidence-complete"],
            "status": "completed",
        }
    }
    before = context.copy()
    resolution = ReflectionResolution(
        opportunity_id="opportunity-complete",
        goal_ids=["goal-arm-complete"],
        evidence_refs=["outcome-complete", "evidence-complete"],
        reason_codes=["late_reflection"],
        actions=["replan"],
        reason_summary="Try again.",
    )

    result = manager.apply_reflection_resolution(resolution, sid="sid-complete")

    assert result == [
        {
            "goal_id": "goal-arm-complete",
            "applied": False,
            "reason": "reflection_completed_outcome_is_terminal",
        }
    ]
    assert context.get("plan_status") == before.get("plan_status")
    assert context["semantic_goal"]["description"] == "Bring the cup."


def test_reflection_actions_require_evidence_refs() -> None:
    import pytest

    with pytest.raises(ValueError, match="trusted evidence_refs"):
        ReflectionResolution(
            opportunity_id="opportunity-no-evidence",
            goal_ids=["goal-arm"],
            evidence_refs=[],
            reason_codes=["grasp_failed"],
            actions=["replan"],
            reason_summary="Try another route.",
        )
