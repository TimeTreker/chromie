from __future__ import annotations

import asyncio

from agent.app.reflection import ReflectionResolver
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.reflection import ReflectionRequest, ReflectionResolution
from shared.chromie_contracts.situation import CognitiveOpportunity


class FakeOllama:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0
        self.prompts: list[str] = []

    async def generate(self, *args, **kwargs):
        self.calls += 1
        if args:
            self.prompts.append(str(args[0]))
        return self.payload


def request_for(opportunity: CognitiveOpportunity) -> ReflectionRequest:
    return ReflectionRequest(
        sid="sid-reflect",
        text="Please keep trying.",
        language="en-US",
        opportunity=opportunity,
        context={
            "execution_outcome_bundle": {
                "outcome_id": opportunity.evidence_refs[0],
                "goal_outcomes": [],
            },
            "active_goal_snapshots": [{"goal_id": opportunity.goal_ids[0]}],
            "recent_goal_snapshots": [],
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


def test_reflection_replans_without_changing_responsibility_and_promotes_bounded_memory() -> None:
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

    assert first_result[0]["memory_promoted"] == 1
    assert first_result[0]["repeated_pattern"] is False
    assert context["semantic_goal"]["responsibility_status"] == "open"
    assert context["plan_status"] == "not_planned"
    assert first_result[0]["planner_advisory_actions"] == ["replan"]
    assert first_result[0]["planner_advisory"]["authority"] == "planner_advisory_only"
    assert any(
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
    request = ReflectionRequest(
        sid="sid-reflect-no-evidence",
        text="Please keep trying.",
        language="en-US",
        opportunity=opportunity,
        context={
            "execution_outcome_bundle": {},
            "active_goal_snapshots": [{"goal_id": "goal-arm"}],
        },
    )

    result = asyncio.run(ReflectionResolver(ollama).resolve(request))

    assert ollama.calls == 0
    assert result.actions == []
    assert "trusted evidence" in result.reason_summary


def _terminal_reflection_context() -> tuple[ConversationStateManager, dict]:
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
    manager._set_goal_responsibility_status(
        context,
        "satisfied",
        source="test_completed_outcome",
        evidence_refs=["outcome-complete", "evidence-complete"],
    )
    context["status"] = "done"
    context["commitment_state"] = "completed"
    context["plan_status"] = "completed"
    context["evidence_summary"] = {
        "execution_outcome": {
            "outcome_id": "outcome-complete",
            "turn_id": "turn-complete",
            "evidence_ids": ["evidence-complete"],
            "status": "completed",
        }
    }
    return manager, context


def test_reflection_cannot_reopen_completed_outcome() -> None:
    manager, context = _terminal_reflection_context()
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

    assert result[0]["applied"] is False
    assert result[0]["applied_actions"] == []
    assert result[0]["rejected_actions"] == ["replan"]
    assert result[0]["reason"] == "reflection_terminal_responsibility_action_rejected"
    assert result[0]["responsibility_status"] == "satisfied"
    assert context.get("plan_status") == before.get("plan_status")
    assert context["semantic_goal"]["description"] == "Bring the cup."
    assert context["semantic_goal"]["responsibility_status"] == "satisfied"


def test_terminal_history_can_propose_local_memory_without_reopening_goal() -> None:
    manager, context = _terminal_reflection_context()
    resolution = ReflectionResolution(
        opportunity_id="opportunity-terminal-memory",
        goal_ids=["goal-arm-complete"],
        evidence_refs=["outcome-complete", "evidence-complete"],
        reason_codes=["late_reflection"],
        actions=["propose_memory"],
        memory_candidates=[
            {
                "scope": "task",
                "kind": "experience",
                "text": "The completed grasp outcome exposed a misleading local assumption.",
                "confidence": 0.9,
            }
        ],
        reason_summary="Remember the local lesson without changing history.",
    )

    result = manager.apply_reflection_resolution(resolution, sid="sid-terminal-memory")

    assert result[0]["applied"] is True
    assert result[0]["applied_actions"] == ["propose_memory"]
    assert result[0]["rejected_actions"] == []
    assert result[0]["memory_promoted"] == 1
    assert result[0]["terminal_history_learning"] is True
    assert context["semantic_goal"]["responsibility_status"] == "satisfied"
    assert context["status"] == "done"
    assert context["plan_status"] == "completed"
    assert any(
        item["kind"] == "experience"
        for item in manager.snapshot()["extracted_memory"]
    )
    assert manager.snapshot()["durable_profile_memory"]["entries"] == []


def test_terminal_history_rejects_replan_but_keeps_memory_learning() -> None:
    manager, context = _terminal_reflection_context()
    resolution = ReflectionResolution(
        opportunity_id="opportunity-terminal-mixed",
        goal_ids=["goal-arm-complete"],
        evidence_refs=["outcome-complete", "evidence-complete"],
        reason_codes=["late_reflection"],
        actions=["replan", "propose_memory"],
        memory_candidates=[
            {
                "scope": "session",
                "kind": "calibration",
                "text": "Treat a similar unresolved referent as less settled next time.",
                "confidence": 0.85,
            }
        ],
        reason_summary="Learn forward only.",
    )

    result = manager.apply_reflection_resolution(resolution, sid="sid-terminal-mixed")

    assert result[0]["applied"] is True
    assert result[0]["applied_actions"] == ["propose_memory"]
    assert result[0]["rejected_actions"] == ["replan"]
    assert result[0]["terminal_history_learning"] is True
    assert context["semantic_goal"]["responsibility_status"] == "satisfied"
    assert context["status"] == "done"
    assert context["plan_status"] == "completed"


def test_reflection_memory_has_trusted_finite_lifetime_independent_of_goal_boundary() -> None:
    manager = ConversationStateManager(
        base_conversation_id="reflection-expiry",
        hard_idle_timeout_sec=3600,
        reflection_memory_max_ttl_sec=2,
    )
    manager.apply_semantic_task_operations_atomically(
        [
            {
                "operation_id": "create-expiry-goal",
                "operation": "create",
                "goal": {
                    "goal_id": "goal-expiry",
                    "description": "Keep the task open.",
                    "source_text": "Keep the task open.",
                },
            }
        ],
        sid="sid-expiry-create",
        user_text="Keep the task open.",
    )
    context = manager._task_context_by_goal_id("goal-expiry")
    assert context is not None
    context["evidence_summary"] = {
        "execution_outcome": {
            "outcome_id": "outcome-expiry",
            "turn_id": "turn-expiry",
            "evidence_ids": ["evidence-expiry"],
            "status": "failed",
        }
    }
    resolution = ReflectionResolution(
        opportunity_id="opportunity-expiry",
        goal_ids=["goal-expiry"],
        evidence_refs=["outcome-expiry", "evidence-expiry"],
        reason_codes=["local_calibration"],
        actions=["propose_memory"],
        memory_candidates=[
            {
                "scope": "session",
                "kind": "calibration",
                "text": "Treat the local referent as unsettled in this bounded context.",
                "confidence": 0.8,
            }
        ],
    )

    manager.apply_reflection_resolution(resolution, sid="sid-expiry")

    entries = [
        item for item in manager.snapshot()["extracted_memory"]
        if item["kind"] == "calibration"
    ]
    assert len(entries) == 1
    assert entries[0]["expires_ms"] is not None
    assert manager._active_task_contexts()

    manager._memory_store.prune_expired(now=float(entries[0]["expires_ms"]) + 1.0)

    assert not any(
        item["kind"] == "calibration"
        for item in manager.snapshot()["extracted_memory"]
    )
    assert manager._active_task_contexts()


def test_reflection_memory_default_max_ttl_never_exceeds_fifteen_minutes() -> None:
    long_conversation = ConversationStateManager(hard_idle_timeout_sec=7200)
    short_conversation = ConversationStateManager(hard_idle_timeout_sec=120)

    assert long_conversation.reflection_memory_max_ttl_sec == 900
    assert short_conversation.reflection_memory_max_ttl_sec == 120
    assert (
        long_conversation.session_memory()["forgetting_policy"]
        ["reflection_memory_max_ttl_sec"]
        == 900
    )


def test_reflection_prompt_surfaces_terminal_history_and_forbids_global_shortcuts() -> None:
    opportunity = CognitiveOpportunity.create(
        trigger="execution_outcome",
        goal_ids=["goal-arm"],
        evidence_refs=["outcome-2", "evidence-2"],
        reason_codes=["late_reflection"],
        recommended_cognition="slow",
    )
    ollama = FakeOllama({"actions": []})
    request = request_for(opportunity)
    request.context["recent_goal_snapshots"] = [
        {"goal_id": "goal-old", "responsibility_status": "satisfied"}
    ]

    asyncio.run(ReflectionResolver(ollama).resolve(request))

    prompt = ollama.prompts[-1]
    assert "Recent terminal Goal projections JSON" in prompt
    assert "goal-old" in prompt
    assert "never replan, clarify, correct, reopen" in prompt
    assert "pattern-to-always/never-Deep" in prompt
    assert "trusted runtime, not this model, bounds their lifetime" in prompt


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
