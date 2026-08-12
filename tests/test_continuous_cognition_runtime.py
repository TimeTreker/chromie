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


def test_fully_bound_safe_read_runs_with_goal_association_and_avoids_planner_composer():
    async def scenario():
        candidate = CognitiveProgressCandidate(
            candidate_id="progress-reference",
            capability_id="chromie.reference.lookup",
            args={"query": "current status"},
            intent="capability:chromie.reference.lookup",
            confidence=0.99,
        )
        runtime = ReadyFakeRuntime()
        client = ContinuousClient(runtime, information_goal("goal-reference", candidate.candidate_id))
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(runtime),
            policy=CognitiveRuntimePolicy(mode="apply"),
        )
        result = await coordinator._resolve(
            object(),
            text="Check the current reference status.",
            sid="session-1",
            route_decision=SimpleNamespace(route="tool", intent="capability:chromie.reference.lookup"),
            context={
                "turn_id": "turn-1",
                "progress_candidates": [candidate.model_dump(mode="json")],
            },
            history=[],
            language="zh-CN",
        )
        assert result.status == "applied"
        assert result.fast_plan is not None
        assert result.fast_plan.metadata["resolver"] == "readiness_adoption"
        assert result.metadata["fast_planner_path"] == "readiness_adoption"
        assert result.metadata["ready_result_bound_count"] == 1
        assert result.interaction_response is not None
        assert len(result.interaction_response.skills) == 1
        assert result.interaction_response.skills[0].args == {"query": "current status"}
        assert client.calls == ["association"]
        assert runtime.start_calls == 1
        assert runtime.bind_calls == 1
        assert runtime.cancel_calls == 0

    asyncio.run(scenario())


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
                    "responsibility_kind": "spoken_response",
                    "execution_lane": "speaking",
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


def test_ready_read_is_rebound_once_to_exact_canonical_request_without_second_provider_call():
    async def scenario():
        coordinator = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        definition = safe_read_definition()
        provider = CountingProvider()
        coordinator.registry.register(definition)
        coordinator.runtime.register_provider(provider)
        candidate = CognitiveProgressCandidate(
            candidate_id="progress-reference",
            capability_id=definition.skill_id,
            args={"query": "current status"},
            intent="capability:chromie.reference.lookup",
            confidence=0.99,
        )
        handle = await coordinator.start_ready_capability_read(
            candidate,
            session_id="session-1",
            turn_id="turn-1",
            language="zh-CN",
        )
        assert handle is not None
        canonical = SkillRequest(
            request_id="canonical-reference",
            skill_id=definition.skill_id,
            skill_version=definition.version,
            args={"query": "current status"},
            timing="parallel",
            committed_output_schema_sha256=output_schema_sha256(definition.output_schema),
            metadata={"source_goal_ids": ["goal-reference"]},
        )
        assert await coordinator.bind_ready_capability_read(
            handle,
            canonical_interaction_id="canonical-interaction",
            canonical_request=canonical,
        )
        execution = await coordinator.execute(
            InteractionResponse(
                interaction_id="canonical-interaction",
                skills=[canonical],
                metadata={"language": "zh-CN"},
            ),
            session_id="session-1",
        )
        assert provider.calls == 1
        assert len(execution.results) == 1
        assert execution.results[0].request_id == "canonical-reference"
        assert execution.results[0].metadata["readiness_candidate_reused"] is True

    asyncio.run(scenario())


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
            event="understanding_ready",
            context={},
        )

        assert result["status"] == "completed"
        assert result["materialized_count"] == 1
        assert provider.calls == 1
        evidence = adapter.recent_auxiliary_behavior_evidence("session-social")
        assert len(evidence) == 1
        assert evidence[0]["execution_claim"] == "not_observed"

    asyncio.run(scenario())


def test_social_attention_planning_is_peer_lane_and_does_not_wait_for_goal_association():
    async def scenario():
        candidate = CognitiveProgressCandidate(
            candidate_id="progress-reference-social",
            capability_id="chromie.reference.lookup",
            args={"query": "current status"},
            intent="capability:chromie.reference.lookup",
            confidence=0.99,
        )
        runtime = ReadyFakeRuntime()
        association = information_goal("goal-reference-social", candidate.candidate_id)
        social_planned = asyncio.Event()

        class Client(ContinuousClient):
            async def resolve_social_attention(self, *args, **kwargs):
                self.calls.append("social")
                social_planned.set()
                return SocialAttentionPlan(decision="none", reason="No expression needed.")

            async def resolve_goal_association(self, *args, **kwargs):
                self.calls.append("association")
                await asyncio.wait_for(runtime.started.wait(), timeout=1.0)
                await asyncio.wait_for(social_planned.wait(), timeout=1.0)
                return association

        client = Client(runtime, association)
        adapter = CanonicalPlanRuntimeAdapter(runtime)
        social_executed = asyncio.Event()

        async def execute_social_attention_event(**kwargs):
            social_executed.set()
            return {"status": "not_executed", "materialized_count": 0}

        adapter.execute_social_attention_event = execute_social_attention_event  # type: ignore[method-assign]
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=adapter,
            policy=CognitiveRuntimePolicy(mode="apply"),
        )
        result = await coordinator._resolve(
            object(),
            text="Check the current reference status.",
            sid="session-social-parallel",
            route_decision=SimpleNamespace(
                route="tool", intent="capability:chromie.reference.lookup"
            ),
            context={
                "turn_id": "turn-1",
                "progress_candidates": [candidate.model_dump(mode="json")],
            },
            history=[],
            language="zh-CN",
        )
        await asyncio.wait_for(social_executed.wait(), timeout=1.0)
        assert result.status == "applied"
        assert "social" in client.calls
        assert client.calls.index("social") < client.calls.index("association") or social_planned.is_set()
        assert "compose" not in client.calls

    asyncio.run(scenario())


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


def test_effectful_candidate_never_starts_through_ready_read_boundary():
    async def scenario():
        coordinator = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        definition = stateful_write_definition()
        coordinator.registry.register(definition)
        candidate = CognitiveProgressCandidate(
            candidate_id="progress-write",
            capability_id=definition.skill_id,
            args={"value": "change state"},
            intent="capability:chromie.test.write",
            confidence=0.99,
        )

        handle = await coordinator.start_ready_capability_read(
            candidate,
            session_id="session-write",
            turn_id="turn-write",
            language="en-US",
        )

        assert handle is None

    asyncio.run(scenario())


def test_malformed_safe_read_args_do_not_schedule_provider_work():
    async def scenario():
        coordinator = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        definition = safe_read_definition()
        provider = CountingProvider()
        coordinator.registry.register(definition)
        coordinator.runtime.register_provider(provider)
        candidate = CognitiveProgressCandidate(
            candidate_id="progress-reference-invalid",
            capability_id=definition.skill_id,
            args={},
            intent="capability:chromie.reference.lookup",
            confidence=0.99,
        )

        handle = await coordinator.start_ready_capability_read(
            candidate,
            session_id="session-invalid",
            turn_id="turn-invalid",
            language="zh-CN",
        )
        await asyncio.sleep(0)

        assert handle is None
        assert provider.calls == 0

    asyncio.run(scenario())


def test_social_attention_lane_coalesces_intermediate_state_while_one_decision_is_in_flight():
    async def scenario():
        runtime = ReadyFakeRuntime()
        association = information_goal("goal-social-events", "progress-social-events")
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_finished = asyncio.Event()
        events: list[str] = []

        class Client(ContinuousClient):
            async def resolve_social_attention(self, *args, **kwargs):
                request = kwargs["request"]
                events.append(request.event)
                if len(events) == 1:
                    first_started.set()
                    await release_first.wait()
                else:
                    second_finished.set()
                return SocialAttentionPlan(decision="none", reason="No expression needed.")

        client = Client(runtime, association)
        adapter = CanonicalPlanRuntimeAdapter(runtime)

        async def execute_social_attention_event(**kwargs):
            return {"status": "not_executed", "materialized_count": 0}

        adapter.execute_social_attention_event = execute_social_attention_event  # type: ignore[method-assign]
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=adapter,
            policy=CognitiveRuntimePolicy(mode="apply"),
        )
        common = dict(
            session=object(),
            text="Check the current reference status.",
            sid="session-social-events",
            turn_id="turn-social-events",
            language="zh-CN",
            intent="capability:chromie.reference.lookup",
            context={},
            history=[],
        )
        coordinator._queue_social_attention_event(event="understanding_ready", **common)
        await asyncio.wait_for(first_started.wait(), timeout=1.0)
        coordinator._queue_social_attention_event(event="goal_associated", **common)
        coordinator._queue_social_attention_event(event="work_started", **common)
        coordinator._queue_social_attention_event(event="evidence_arrived", **common)
        release_first.set()
        await asyncio.wait_for(second_finished.wait(), timeout=1.0)
        for _ in range(10):
            if not coordinator._social_attention_workers:
                break
            await asyncio.sleep(0)

        assert events == ["understanding_ready", "evidence_arrived"]
        assert not coordinator._social_attention_pending

    asyncio.run(scenario())
