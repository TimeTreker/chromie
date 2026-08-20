from __future__ import annotations

import asyncio

import pytest
from types import SimpleNamespace

from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveRuntimeResolution,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.runtime.capability_runtime import CapabilityDefinition
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
    CapabilityResult,
)
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.social_attention import SocialAttentionPlan


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}

def social_activity_context(
    activity_id: str,
    *,
    execution_lane: str = "vocal",
    vocal_modes: list[str] | None = None,
    capability_ids: list[str] | None = None,
    goal_ids: list[str] | None = None,
    summary: str = "primary outward activity",
) -> dict:
    return {
        "social_attention_primary_activity": {
            "activity_id": activity_id,
            "phase": "ready",
            "summary": summary,
            "goal_ids": list(goal_ids or []),
            "realization": {
                "execution_lanes": [execution_lane],
                "vocal_modes": list(
                    vocal_modes
                    or (["speech"] if execution_lane == "vocal" else [])
                ),
                "capability_ids": list(capability_ids or []),
            },
        }
    }


def blink_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="chromie.social.blink",
        version="1.0",
        provider_id="test.social",
        description="test independent blink",
        input_schema={
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 4}},
            "required": ["count"],
            "additionalProperties": False,
        },
        output_schema=OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=True,
        timeout_ms=1000,
        requires_safety_monitor=False,
        metadata={
            "effects": ["visual_expression"],
            "safety_class": "low_risk_action",
            "behavior_domains": ["social_attention"],
            "parallel_metadata_declared": True,
            "resource_claims": ["visual.eyes"],
            "control_coupling": "independent_output",
            "execution_lane": "activity",
        },
    )


def nod_definition(*, resource_claim: str = "visual.head") -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="chromie.social.nod",
        version="1.0",
        provider_id="test.social",
        description="test independent nod",
        input_schema={
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 4}},
            "required": ["count"],
            "additionalProperties": False,
        },
        output_schema=OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=True,
        timeout_ms=1000,
        requires_safety_monitor=False,
        metadata={
            "effects": ["physical_motion"],
            "safety_class": "low_risk_action",
            "behavior_domains": ["social_attention"],
            "parallel_metadata_declared": True,
            "resource_claims": [resource_claim],
            "control_coupling": "independent_output",
            "execution_lane": "activity",
        },
    )


class SocialProvider:
    provider_id = "test.social"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request, definition, context):
        self.calls += 1
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output={"summary": "blink completed"},
        )

    async def cancel(self, request, definition, context):
        return None


def test_independent_social_attention_uses_same_trusted_runtime_without_goal_authority():
    async def scenario():
        runtime = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        definition = blink_definition()
        provider = SocialProvider()
        runtime.registry.register(definition)
        runtime.runtime.register_provider(provider)
        adapter = CanonicalPlanRuntimeAdapter(runtime, social_attention_mode="on")
        plan = SocialAttentionPlan.model_validate(
            {
                "purpose": "acknowledge",
                "decision": "express",
                "target": {"target_ref": "none", "source": "none"},
                "behaviors": [
                    {
                        "capability_id": definition.capability_id,
                        "args": {"count": 1},
                        "timing": "parallel",
                        "reason": "A subtle acknowledgement is natural.",
                    }
                ],
                "confidence": 0.9,
            }
        )

        result = await adapter.execute_social_attention_event(
            plan=plan,
            session_id="session-social",
            turn_id="turn-social",
            event="primary_activity_ready",
            context=social_activity_context("activity-social"),
        )

        assert result["status"] == "completed"
        assert result["materialized_count"] == 1
        assert provider.calls == 1
        evidence = adapter.recent_auxiliary_behavior_evidence("session-social")
        assert len(evidence) == 1
        assert evidence[0]["execution_claim"] == "not_observed"
        assert evidence[0]["turn_id"] == "turn-social"

    asyncio.run(scenario())


def test_social_attention_cooldown_is_scoped_to_primary_activity_not_turn():
    async def scenario():
        runtime = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        definition = blink_definition()
        provider = SocialProvider()
        runtime.registry.register(definition)
        runtime.runtime.register_provider(provider)
        adapter = CanonicalPlanRuntimeAdapter(runtime, social_attention_mode="on")
        calls: list[str] = []

        class Client:
            async def resolve_social_attention(self, *args, **kwargs):
                request = kwargs["request"]
                calls.append(request.primary_activity.activity_id)
                return SocialAttentionPlan.model_validate(
                    {
                        "purpose": "acknowledge",
                        "decision": "express",
                        "target": {"target_ref": "none", "source": "none"},
                        "behaviors": [
                            {
                                "capability_id": definition.capability_id,
                                "args": {"count": 1},
                                "timing": "parallel",
                                "reason": "One subtle blink is enough.",
                            }
                        ],
                        "confidence": 0.9,
                    }
                )

        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=Client(),
            adapter=adapter,
            policy=CognitiveRuntimePolicy(mode="apply"),
        )
        common = dict(
            session=object(),
            text="Check the weather.",
            sid="session-social-cooldown",
            turn_id="turn-social-cooldown",
            language="en-US",
            history=[],
        )
        first = await coordinator._run_social_attention_event(
            event="primary_activity_ready",
            context=social_activity_context("activity-ack"),
            **common,
        )
        duplicate = await coordinator._run_social_attention_event(
            event="primary_activity_ready",
            context=social_activity_context("activity-ack"),
            **common,
        )
        later = await coordinator._run_social_attention_event(
            event="primary_activity_ready",
            context=social_activity_context("activity-final"),
            **common,
        )

        assert first["materialized_count"] == 1
        assert duplicate == {
            "status": "suppressed",
            "event": "primary_activity_ready",
            "decision": "none",
            "materialized_count": 0,
            "reasons": ["same_primary_activity_auxiliary_cooldown"],
        }
        assert later["materialized_count"] == 1
        assert calls == ["activity-ack", "activity-final"]
        assert provider.calls == 2

    asyncio.run(scenario())


def test_social_attention_primary_progress_is_scoped_to_semantic_activity_goal():
    async def scenario():
        captured: dict[str, object] = {}

        class Client:
            async def resolve_social_attention(self, *args, **kwargs):
                request = kwargs["request"]
                captured.update(request.context["social_attention_interaction_state"])
                return SocialAttentionPlan(decision="none", reason="No decoration needed.")

        adapter = CanonicalPlanRuntimeAdapter(SimpleNamespace())

        async def execute_social_attention_event(**kwargs):
            return {"status": "not_executed", "materialized_count": 0}

        adapter.execute_social_attention_event = execute_social_attention_event  # type: ignore[method-assign]
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=Client(),
            adapter=adapter,
            policy=CognitiveRuntimePolicy(mode="apply"),
        )
        context = {
            **social_activity_context(
                "goal:goal-walk",
                execution_lane="activity",
                capability_ids=["soridormi.walk_forward"],
                goal_ids=["goal-walk"],
                summary="walk forward",
            ),
            "canonical_plan_resolution": {
                "steps": [
                    {
                        "step_id": "step-walk",
                        "capability_id": "soridormi.walk_forward",
                        "source_goal_ids": ["goal-walk"],
                        "args": {"duration_s": 2},
                    },
                    {
                        "step_id": "step-blink",
                        "capability_id": "soridormi.blink_eyes",
                        "source_goal_ids": ["goal-blink"],
                        "args": {"count": 2},
                    },
                ]
            },
        }

        outcome = await coordinator._run_social_attention_event(
            session=object(),
            event="primary_activity_ready",
            text="Walk forward and blink twice.",
            sid="session-semantic-activity-scope",
            turn_id="turn-semantic-activity-scope",
            language="en-US",
            context=context,
            history=[],
        )

        assert outcome["status"] == "not_executed"
        assert captured["primary_capability_ids"] == ["soridormi.walk_forward"]
        assert [
            item["step_id"] for item in captured["primary_progress"]  # type: ignore[index]
        ] == ["step-walk"]

    asyncio.run(scenario())


def test_social_attention_cannot_duplicate_explicit_primary_activity():
    async def scenario():
        runtime = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        definition = blink_definition()
        provider = SocialProvider()
        runtime.registry.register(definition)
        runtime.runtime.register_provider(provider)
        adapter = CanonicalPlanRuntimeAdapter(runtime, social_attention_mode="on")
        plan = SocialAttentionPlan.model_validate(
            {
                "purpose": "engagement",
                "decision": "express",
                "behaviors": [
                    {
                        "capability_id": definition.capability_id,
                        "args": {"count": 1},
                        "timing": "parallel",
                    }
                ],
                "confidence": 0.9,
            }
        )

        result = await adapter.execute_social_attention_event(
            plan=plan,
            session_id="session-social-primary",
            turn_id="turn-social-primary",
            event="primary_activity_ready",
            context={
                **social_activity_context(
                    "activity-social-primary",
                    execution_lane="activity",
                    capability_ids=[definition.capability_id],
                ),
                "social_attention_interaction_state": {
                    "primary_capability_ids": [definition.capability_id]
                },
            },
        )

        assert result["status"] == "rejected"
        assert result["materialized_count"] == 0
        assert f"duplicates_primary_activity:{definition.capability_id}" in result["reasons"]
        assert provider.calls == 0

    asyncio.run(scenario())


def test_social_attention_allows_a_different_compatible_auxiliary_cue():
    async def scenario():
        runtime = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        primary = blink_definition()
        auxiliary = nod_definition()
        provider = SocialProvider()
        runtime.registry.register(primary)
        runtime.registry.register(auxiliary)
        runtime.runtime.register_provider(provider)
        adapter = CanonicalPlanRuntimeAdapter(runtime, social_attention_mode="on")
        plan = SocialAttentionPlan.model_validate(
            {
                "purpose": "engagement",
                "decision": "express",
                "behaviors": [
                    {
                        "capability_id": auxiliary.capability_id,
                        "args": {"count": 1},
                        "timing": "parallel",
                        "reason": "A small compatible cue supports the playful framing.",
                    }
                ],
                "confidence": 0.9,
            }
        )

        result = await adapter.execute_social_attention_event(
            plan=plan,
            session_id="session-social-compatible",
            turn_id="turn-social-compatible",
            event="primary_activity_ready",
            context={
                **social_activity_context(
                    "activity-social-compatible",
                    execution_lane="activity",
                    capability_ids=[primary.capability_id],
                ),
                "social_attention_interaction_state": {
                    "primary_capability_ids": [primary.capability_id]
                },
            },
        )

        assert result["status"] == "completed"
        assert result["materialized_count"] == 1
        assert provider.calls == 1

    asyncio.run(scenario())


def test_social_attention_rejects_a_different_cue_that_conflicts_with_primary_activity():
    async def scenario():
        runtime = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        primary = blink_definition()
        auxiliary = nod_definition(resource_claim="visual.eyes")
        provider = SocialProvider()
        runtime.registry.register(primary)
        runtime.registry.register(auxiliary)
        runtime.runtime.register_provider(provider)
        adapter = CanonicalPlanRuntimeAdapter(runtime, social_attention_mode="on")
        plan = SocialAttentionPlan.model_validate(
            {
                "purpose": "engagement",
                "decision": "express",
                "behaviors": [
                    {
                        "capability_id": auxiliary.capability_id,
                        "args": {"count": 1},
                        "timing": "parallel",
                    }
                ],
                "confidence": 0.9,
            }
        )

        result = await adapter.execute_social_attention_event(
            plan=plan,
            session_id="session-social-conflict",
            turn_id="turn-social-conflict",
            event="primary_activity_ready",
            context={
                **social_activity_context(
                    "activity-social-conflict",
                    execution_lane="activity",
                    capability_ids=[primary.capability_id],
                ),
                "social_attention_interaction_state": {
                    "primary_capability_ids": [primary.capability_id]
                },
            },
        )

        assert result["status"] == "rejected"
        assert result["materialized_count"] == 0
        assert f"resource_conflict:{auxiliary.capability_id}" in result["reasons"]
        assert provider.calls == 0

    asyncio.run(scenario())


def test_social_attention_projects_semantic_activities_not_execution_modalities():
    resolution = CognitiveRuntimeResolution(
        mode="apply",
        status="applied",
        goal_association=GoalAssociationResolution(
            resolution_status="resolved",
            turn_id="turn-compound-social",
            new_goals=[
                SemanticGoal(
                    goal_id="goal-greet",
                    description="greet Alice warmly",
                    source_text="Greet Alice while you walk, then sing a short song.",
                    metadata={"output_mode": "speech"},
                ),
                SemanticGoal(
                    goal_id="goal-walk",
                    description="walk forward for two seconds",
                    source_text="Greet Alice while you walk, then sing a short song.",
                    metadata={"output_mode": "body_action"},
                ),
                SemanticGoal(
                    goal_id="goal-sing",
                    description="sing a short song",
                    source_text="Greet Alice while you walk, then sing a short song.",
                    metadata={"output_mode": "singing", "provider_required": True},
                ),
            ],
        ),
        interaction_response=InteractionResponse(
            interaction_id="interaction-compound-social",
            speech=[
                InteractionSpeech(
                    id="speech-greet",
                    text="Hi Alice!",
                    metadata={
                        "source_goal_ids": ["goal-greet"],
                        "speech_act": "greet",
                        "delivery_role": "response",
                    },
                )
            ],
            capabilities=[
                CapabilityRequest(
                    request_id="request-wave",
                    capability_id="soridormi.wave_hand",
                    args={},
                    metadata={
                        "canonical_plan_id": "plan-compound-social",
                        "step_id": "step-wave",
                        "reason_summary": "wave to Alice as part of the greeting",
                        "source_goal_ids": ["goal-greet"],
                    },
                ),
                CapabilityRequest(
                    request_id="request-walk",
                    capability_id="soridormi.walk_forward",
                    args={"duration_s": 2},
                    metadata={
                        "canonical_plan_id": "plan-compound-social",
                        "step_id": "step-walk",
                        "reason_summary": "walk forward for two seconds",
                        "source_goal_ids": ["goal-walk"],
                    },
                ),
                CapabilityRequest(
                    request_id="request-sing",
                    capability_id="chromie.vocal.perform",
                    args={"mode": "singing", "content": "la la"},
                    metadata={
                        "canonical_plan_id": "plan-compound-social",
                        "step_id": "step-sing",
                        "reason_summary": "sing a short song",
                        "source_goal_ids": ["goal-sing"],
                    },
                ),
            ],
        ),
    )

    activities = GoalDrivenRuntimeCoordinator._resolution_social_activities(
        resolution, turn_id="turn-compound-social"
    )

    assert len(activities) == 4
    assert len({activity.activity_id for activity in activities}) == 4
    assert all(activity.activity_id.startswith("activity_") for activity in activities)
    assert [activity.summary for activity in activities] == [
        "greet: greet Alice warmly",
        "wave to Alice as part of the greeting",
        "walk forward for two seconds",
        "sing a short song",
    ]
    # Goal ownership is above Activity identity: one Goal may own more than one
    # semantic Activity/work item.  Execution modality stays below both.
    assert activities[0].goal_ids == ["goal-greet"]
    assert activities[1].goal_ids == ["goal-greet"]
    assert activities[0].activity_id != activities[1].activity_id
    assert activities[0].realization.execution_lanes == ["vocal"]
    assert activities[0].realization.vocal_modes == ["speech"]
    assert activities[0].realization.execution_item_ids == ["speech-greet"]
    assert activities[0].realization.capability_ids == []
    assert activities[1].realization.execution_lanes == ["activity"]
    assert activities[1].realization.capability_ids == ["soridormi.wave_hand"]
    assert activities[2].realization.execution_lanes == ["activity"]
    assert activities[2].realization.capability_ids == ["soridormi.walk_forward"]
    assert activities[3].realization.execution_lanes == ["vocal"]
    assert activities[3].realization.vocal_modes == ["singing"]
    assert activities[3].realization.capability_ids == ["chromie.vocal.perform"]


def test_social_attention_realization_is_not_primary_activity_identity():
    from pydantic import ValidationError
    from shared.chromie_contracts.social_attention import SocialAttentionActivityAnchor

    with pytest.raises(ValidationError):
        SocialAttentionActivityAnchor.model_validate(
            {
                "activity_id": "wrong-layer",
                "kind": "speech",
                "phase": "ready",
                "summary": "tell a joke",
            }
        )

    anchor = SocialAttentionActivityAnchor.model_validate(
        {
            "activity_id": "goal:joke",
            "phase": "ready",
            "summary": "tell a joke",
            "goal_ids": ["joke"],
            "realization": {
                "execution_lanes": ["vocal"],
                "vocal_modes": ["speech"],
                "execution_item_ids": ["speech-joke"],
            },
        }
    )
    assert anchor.summary == "tell a joke"
    assert anchor.realization.vocal_modes == ["speech"]


def test_social_attention_uses_scheduled_primary_speech_as_activity_anchor(caplog):
    caplog.set_level("INFO", logger="orchestrator.runtime.cognitive_runtime")

    async def scenario():
        captured = {}
        planned = asyncio.Event()

        class Client:
            async def resolve_social_attention(self, *args, **kwargs):
                request = kwargs["request"]
                captured["event"] = request.event
                captured["activity"] = request.primary_activity.model_dump(mode="json")
                planned.set()
                return SocialAttentionPlan(decision="none", reason="No expression needed.")

        runtime = SimpleNamespace()
        adapter = CanonicalPlanRuntimeAdapter(runtime)

        async def execute_social_attention_event(**kwargs):
            return {"status": "not_executed", "materialized_count": 0}

        adapter.execute_social_attention_event = execute_social_attention_event  # type: ignore[method-assign]
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=Client(),
            adapter=adapter,
            policy=CognitiveRuntimePolicy(mode="apply"),
        )
        context = {
            "scheduled_turn_speech": [
                {
                    "status": "scheduled",
                    "stage": "fast_first",
                    "text": "好呀，我查一下。",
                    "speech_event_id": "speech-fast-1",
                }
            ]
        }
        activity = coordinator._scheduled_speech_social_activity(
            context, turn_id="turn-social-speech"
        )
        coordinator._queue_social_attention_for_activity(
            object(),
            activity=activity,
            text="今天重庆天气怎么样？",
            sid="session-social-speech",
            turn_id="turn-social-speech",
            language="zh-CN",
            context=context,
            history=[],
        )
        await asyncio.wait_for(planned.wait(), timeout=1.0)
        for _ in range(10):
            if not coordinator._social_attention_workers:
                break
            await asyncio.sleep(0)

        assert captured["event"] == "primary_activity_ready"
        assert captured["activity"]["activity_id"].startswith("activity_")
        assert captured["activity"]["activity_id"] != "speech-fast-1"
        assert captured["activity"]["summary"] == "好呀，我查一下。"
        assert captured["activity"]["realization"]["execution_lanes"] == ["vocal"]
        assert captured["activity"]["realization"]["vocal_modes"] == ["speech"]
        assert captured["activity"]["realization"]["execution_item_ids"] == [
            "speech-fast-1"
        ]

    asyncio.run(scenario())
    assert "event=primary_activity_ready" in caplog.text


def stateful_write_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="chromie.test.write",
        version="1.0",
        provider_id="test.write",
        description="test stateful write",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string", "minLength": 1}},
            "required": ["value"],
            "additionalProperties": False,
        },
        output_schema=OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=True,
        timeout_ms=1000,
        idempotent=False,
        requires_safety_monitor=False,
        metadata={
            "effects": ["stateful_write"],
            "safety_class": "stateful_write",
            "side_effect_free": False,
            "execution_lane": "activity",
        },
    )


def test_social_attention_lane_coalesces_duplicate_updates_for_one_primary_activity():
    async def scenario():
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_finished = asyncio.Event()
        activities: list[str] = []

        class Client:
            async def resolve_social_attention(self, *args, **kwargs):
                request = kwargs["request"]
                activities.append(request.primary_activity.activity_id)
                if len(activities) == 1:
                    first_started.set()
                    await release_first.wait()
                else:
                    second_finished.set()
                return SocialAttentionPlan(decision="none", reason="No expression needed.")

        adapter = CanonicalPlanRuntimeAdapter(SimpleNamespace())

        async def execute_social_attention_event(**kwargs):
            return {"status": "not_executed", "materialized_count": 0}

        adapter.execute_social_attention_event = execute_social_attention_event  # type: ignore[method-assign]
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=Client(),
            adapter=adapter,
            policy=CognitiveRuntimePolicy(mode="apply"),
        )
        common = dict(
            session=object(),
            text="Tell me something.",
            sid="session-social-events",
            turn_id="turn-social-events",
            language="en-US",
            history=[],
        )
        activity = coordinator._scheduled_speech_social_activity(
            {
                "scheduled_turn_speech": [
                    {"text": "Sure.", "speech_event_id": "activity-speech-1"}
                ]
            },
            turn_id="turn-social-events",
        )
        assert activity is not None
        context = social_activity_context("activity-speech-1")
        coordinator._queue_social_attention_event(
            event="primary_activity_ready", context=context, **common
        )
        await asyncio.wait_for(first_started.wait(), timeout=1.0)
        coordinator._queue_social_attention_event(
            event="primary_activity_ready", context=context, **common
        )
        coordinator._queue_social_attention_event(
            event="primary_activity_ready", context=context, **common
        )
        release_first.set()
        await asyncio.wait_for(second_finished.wait(), timeout=1.0)
        for _ in range(10):
            if not coordinator._social_attention_workers:
                break
            await asyncio.sleep(0)

        assert activities == ["activity-speech-1", "activity-speech-1"]
        assert not coordinator._social_attention_pending

    asyncio.run(scenario())
