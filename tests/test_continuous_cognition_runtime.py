from __future__ import annotations

import asyncio
from types import SimpleNamespace

from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.runtime.skill_runtime import SkillDefinition
from shared.chromie_contracts.core_interpretation import CognitiveProgressCandidate
from shared.chromie_contracts.goal import GoalAssociationResolution, GoalProgressBinding
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    SkillRequest,
    SkillResult,
    output_schema_sha256,
)
from shared.chromie_contracts.resource import (
    AcquireAndDeliverResource,
    ResourceDescriptor,
    ResourceRecipient,
    ResourceSource,
)
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.social_attention import SocialAttentionPlan


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}
INPUT_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string", "minLength": 1}},
    "required": ["query"],
    "additionalProperties": False,
}


def social_activity_context(
    activity_id: str,
    *,
    kind: str = "speech",
    capability_ids: list[str] | None = None,
) -> dict:
    return {
        "social_attention_primary_activity": {
            "activity_id": activity_id,
            "kind": kind,
            "phase": "ready",
            "summary": "primary outward activity",
            "capability_ids": list(capability_ids or []),
        }
    }


def safe_read_definition(*, provider_id: str = "test.reference") -> SkillDefinition:
    return SkillDefinition(
        skill_id="chromie.reference.lookup",
        version="1.0",
        provider_id=provider_id,
        description="test provider-neutral information read",
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=True,
        timeout_ms=1000,
        idempotent=True,
        requires_safety_monitor=False,
        metadata={
            "effects": ["read_only"],
            "safety_class": "safe_read",
            "side_effect_free": True,
            "execution_lane": "activity",
            "semantic_scope": {
                "responsibility_type": "acquire_and_deliver_resource",
                "resource_kinds": ["information"],
            },
            "resource_contract": {
                "plan_provides": ["resource_acquired"],
                "final_delivery_owner": "chromie_response_layer",
            },
        },
    )


def information_goal(goal_id: str, candidate_id: str) -> GoalAssociationResolution:
    resource = AcquireAndDeliverResource(
        resource=ResourceDescriptor(kind="information", description="current reference information"),
        source=ResourceSource(status="provider_resolved"),
        recipient=ResourceRecipient(description="requester"),
        delivery_mode="spoken_explanation",
    )
    return GoalAssociationResolution(
        turn_id="turn-1",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                description="Look up the current reference status.",
                source_text="Check the current reference status.",
                resource_responsibility=resource,
                metadata={
                    "responsibility_kind": "capability_dependent",
                    "execution_lane": "activity",
                    "output_mode": "capability_work",
                    "provider_required": True,
                    "media_operation": "none",
                },
            )
        ],
        progress_bindings=[
            GoalProgressBinding(
                candidate_id=candidate_id,
                goal_ids=[goal_id],
                confidence=0.98,
                reason_summary="The exact information read satisfies this Goal.",
            )
        ],
        confidence=0.98,
        reason_summary="New information Goal.",
        metadata={"status": "resolved"},
    )


class ReadyFakeRuntime:
    def __init__(self) -> None:
        self.definition = safe_read_definition()
        self.started = asyncio.Event()
        self.start_calls = 0
        self.bind_calls = 0
        self.cancel_calls = 0

    async def ensure_skill_definitions(self, skill_ids):
        for item in skill_ids:
            if item != self.definition.skill_id:
                raise ValueError(item)

    def skill_definition(self, skill_id):
        if skill_id != self.definition.skill_id:
            raise ValueError(skill_id)
        return self.definition

    async def start_ready_capability_read(self, candidate, **kwargs):
        assert candidate.capability_id == self.definition.skill_id
        self.start_calls += 1
        request = SkillRequest(
            request_id=f"ready_{candidate.candidate_id}",
            skill_id=candidate.capability_id,
            skill_version=self.definition.version,
            args=candidate.args,
            committed_output_schema_sha256=output_schema_sha256(self.definition.output_schema),
        )
        self.started.set()
        return SimpleNamespace(candidate=candidate, request=request)

    async def cancel_ready_capability_read(self, handle):
        self.cancel_calls += 1

    async def bind_ready_capability_read(self, handle, **kwargs):
        canonical_request = kwargs["canonical_request"]
        assert canonical_request.skill_id == handle.request.skill_id
        assert canonical_request.args == handle.request.args
        self.bind_calls += 1
        return True


class ContinuousClient:
    def __init__(self, runtime: ReadyFakeRuntime, association: GoalAssociationResolution):
        self.runtime = runtime
        self.association = association
        self.calls: list[str] = []

    async def resolve_goal_association(self, *args, **kwargs):
        self.calls.append("association")
        # Proves the trusted read branch is allowed to start while Goal Association
        # is still in flight rather than after it returns.
        await asyncio.wait_for(self.runtime.started.wait(), timeout=1.0)
        return self.association

    async def resolve_fast_plan(self, *args, **kwargs):
        self.calls.append("fast")
        raise AssertionError("Fast Planner must not run for fully bound safe-read progress")

    async def resolve_deep_plan(self, *args, **kwargs):
        self.calls.append("deep")
        raise AssertionError("Deep Planner must not run")

    async def compose_response_plan(self, *args, **kwargs):
        self.calls.append("compose")
        raise AssertionError("pre-evidence Response Composer must not block a pure safe read")


class ReadyConversationRuntime:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.start_calls = 0
        self.bind_calls = 0
        self.cancel_calls = 0

    async def start_ready_capability_read(self, candidate, **kwargs):
        return None

    async def start_ready_native_response(self, candidate, **kwargs):
        assert candidate.kind == "native_response"
        self.start_calls += 1
        self.started.set()
        return SimpleNamespace(candidate=candidate)

    async def cancel_ready_capability_read(self, handle):
        self.cancel_calls += 1

    async def cancel_ready_native_response(self, handle):
        self.cancel_calls += 1

    async def bind_ready_native_response(self, handle, **kwargs):
        speech = kwargs["canonical_speech"]
        assert speech.text == handle.candidate.response_text
        self.bind_calls += 1
        return True


def spoken_goal(goal_id: str, candidate_id: str) -> GoalAssociationResolution:
    return GoalAssociationResolution(
        turn_id="turn-native",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                description="Answer the user's identity question.",
                source_text="What is your name?",
                metadata={
                    "responsibility_kind": "vocal_output",
                    "execution_lane": "vocal",
                    "output_mode": "speech",
                    "provider_required": False,
                    "media_operation": "none",
                },
            )
        ],
        progress_bindings=[
            GoalProgressBinding(
                candidate_id=candidate_id,
                goal_ids=[goal_id],
                confidence=0.99,
                reason_summary="The native response directly satisfies this Goal.",
            )
        ],
        confidence=0.99,
        reason_summary="One direct conversational Goal.",
        metadata={"status": "resolved"},
    )


def test_native_converse_runs_with_goal_association_and_skips_planner_composer():
    async def scenario():
        candidate = CognitiveProgressCandidate(
            candidate_id="progress-native",
            kind="native_response",
            response_text="I'm Chromie!",
            speech_act="answer",
            intent="identity_question",
            confidence=0.99,
        )
        runtime = ReadyConversationRuntime()
        association = spoken_goal("goal-native", candidate.candidate_id)

        class Client:
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def resolve_goal_association(self, *args, **kwargs):
                self.calls.append("association")
                await asyncio.wait_for(runtime.started.wait(), timeout=1.0)
                return association

            async def resolve_fast_plan(self, *args, **kwargs):
                raise AssertionError("Fast Planner must not run for bound native conversation")

            async def resolve_deep_plan(self, *args, **kwargs):
                raise AssertionError("Deep Planner must not run for bound native conversation")

            async def compose_response_plan(self, *args, **kwargs):
                raise AssertionError("Response Composer must not rewrite bound native conversation")

        client = Client()
        conversation = ConversationStateManager(base_conversation_id="transient-native")
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(runtime),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"chat"}),
            ),
            goal_state_apply=conversation.apply_goal_association_resolution,
        )
        result = await coordinator._resolve(
            object(),
            text="What is your name?",
            sid="session-native",
            route_decision=SimpleNamespace(route="chat", intent="identity_question"),
            context={
                "turn_id": "turn-native",
                "progress_candidates": [candidate.model_dump(mode="json")],
            },
            history=[],
            language="en-US",
        )

        assert result.status == "applied"
        assert result.fast_plan is None
        assert result.terminal_plan is None
        assert result.response_composition is None
        assert result.metadata["fast_planner_path"] == "native_response_readiness_adoption"
        assert result.metadata["native_response_readiness_adoption"] is True
        assert result.metadata["ready_result_bound_count"] == 1
        assert result.metadata["goal_state_commit_stage"] == "transient_native_responsibility"
        assert result.metadata["authoritative_goal_count"] == 0
        assert result.metadata["transient_responsibility_ids"] == ["goal-native"]
        assert conversation.active_goal_snapshots() == []
        assert result.interaction_response is not None
        assert result.interaction_response.metadata["transient_responsibility"] is True
        conversation.record_agent_result("session-native", result.interaction_response)
        assert conversation.active_goal_snapshots() == []
        assert not [
            item
            for item in conversation.snapshot()["pending_tasks"]
            if item.get("type") == "goal_execution"
        ]
        assert [item.text for item in result.interaction_response.speech] == ["I'm Chromie!"]
        assert result.interaction_response.speech[0].metadata["covers_goal_ids"] == [
            "goal-native"
        ]
        assert client.calls == ["association"]
        assert runtime.start_calls == 1
        assert runtime.bind_calls == 1
        assert runtime.cancel_calls == 0

    asyncio.run(scenario())


def test_ready_native_speech_is_rebound_to_canonical_speech_without_second_tts_call():
    async def scenario():
        scheduled: list[dict] = []

        def scheduler(payload):
            scheduled.append(dict(payload))
            return {"scheduled": True, "playback_started": True}

        coordinator = InteractionRuntimeCoordinator(scheduler)
        candidate = CognitiveProgressCandidate(
            candidate_id="progress-native-runtime",
            kind="native_response",
            response_text="I'm Chromie!",
            speech_act="answer",
            intent="identity_question",
            confidence=0.99,
        )
        handle = await coordinator.start_ready_native_response(
            candidate,
            session_id="session-native-runtime",
            turn_id="turn-native-runtime",
            language="en-US",
        )
        assert handle is not None
        canonical_speech = InteractionSpeech(
            id="speech-canonical-native",
            text="I'm Chromie!",
            metadata={"source_goal_ids": ["goal-native-runtime"]},
        )
        assert await coordinator.bind_ready_native_response(
            handle,
            canonical_interaction_id="interaction-native-runtime",
            canonical_speech=canonical_speech,
        )
        execution = await coordinator.execute(
            InteractionResponse(
                interaction_id="interaction-native-runtime",
                speech=[canonical_speech],
            ),
            session_id="session-native-runtime",
        )

        assert len(scheduled) == 1
        assert execution.status == "completed"
        assert any(
            result.request_id == "speech-canonical-native"
            and result.skill_id == "chromie.speak"
            for result in execution.results
        )

    asyncio.run(scenario())


class CountingProvider:
    provider_id = "test.reference"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request, definition, context):
        self.calls += 1
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output={"summary": "The current reference status is available."},
        )

    async def cancel(self, request, definition, context):
        return None


def blink_definition() -> SkillDefinition:
    return SkillDefinition(
        skill_id="chromie.social.blink",
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


def nod_definition(*, resource_claim: str = "visual.head") -> SkillDefinition:
    return SkillDefinition(
        skill_id="chromie.social.nod",
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
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
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
                        "capability_id": definition.skill_id,
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
                                "capability_id": definition.skill_id,
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
            intent="weather_lookup",
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
                        "capability_id": definition.skill_id,
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
                    kind="body_action",
                    capability_ids=[definition.skill_id],
                ),
                "social_attention_interaction_state": {
                    "primary_capability_ids": [definition.skill_id]
                },
            },
        )

        assert result["status"] == "rejected"
        assert result["materialized_count"] == 0
        assert f"duplicates_primary_activity:{definition.skill_id}" in result["reasons"]
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
                        "capability_id": auxiliary.skill_id,
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
                    kind="body_action",
                    capability_ids=[primary.skill_id],
                ),
                "social_attention_interaction_state": {
                    "primary_capability_ids": [primary.skill_id]
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
                        "capability_id": auxiliary.skill_id,
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
                    kind="body_action",
                    capability_ids=[primary.skill_id],
                ),
                "social_attention_interaction_state": {
                    "primary_capability_ids": [primary.skill_id]
                },
            },
        )

        assert result["status"] == "rejected"
        assert result["materialized_count"] == 0
        assert f"resource_conflict:{auxiliary.skill_id}" in result["reasons"]
        assert provider.calls == 0

    asyncio.run(scenario())


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
            intent="weather_lookup",
            context=context,
            history=[],
        )
        await asyncio.wait_for(planned.wait(), timeout=1.0)
        for _ in range(10):
            if not coordinator._social_attention_workers:
                break
            await asyncio.sleep(0)

        assert captured["event"] == "primary_activity_ready"
        assert captured["activity"]["activity_id"] == "speech-fast-1"
        assert captured["activity"]["kind"] == "speech"
        assert captured["activity"]["summary"] == "好呀，我查一下。"

    asyncio.run(scenario())
    assert "event=primary_activity_ready" in caplog.text


def stateful_write_definition() -> SkillDefinition:
    return SkillDefinition(
        skill_id="chromie.test.write",
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
            intent="conversation",
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
