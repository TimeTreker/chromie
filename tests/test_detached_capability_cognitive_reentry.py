from __future__ import annotations

import asyncio
from types import MethodType, SimpleNamespace
from typing import Any

import pytest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition,
    CapabilityExecutionContext,
    CapabilityRuntimeResult,
    schema_valid_completion_evidence_policy,
)
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from shared.chromie_contracts.execution_outcome import claim_qualification_policy_sha256
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    InteractionResponse,
    output_schema_sha256,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.plan import canonical_plan_fingerprint


_SCHEMA = {
    "type": "object",
    "properties": {"user_summary": {"type": "string"}},
    "required": ["user_summary"],
    "additionalProperties": False,
}


class _TwoResultProvider:
    provider_id = "test.detached"

    def __init__(self) -> None:
        self.first_started = asyncio.Event()
        self.second_started = asyncio.Event()
        self.release_first = asyncio.Event()
        self.release_second = asyncio.Event()

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        del definition, context
        if request.capability_id.endswith("first"):
            self.first_started.set()
            await self.release_first.wait()
            summary = "first result"
        else:
            self.second_started.set()
            await self.release_second.wait()
            summary = "second result"
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            status="completed",
            output={"user_summary": summary},
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        del request, definition, context


class _ConversationState:
    def __init__(self) -> None:
        self.recorded_agent_results: list[InteractionResponse] = []
        self.status_updates: list[tuple[str, str]] = []
        response = _response()
        self.plan_id = str(response.metadata["canonical_plan_id"])
        self.plan_fingerprint = str(response.metadata["canonical_plan_fingerprint"])
        self.goal_status = {
            "goal-first": "open",
            "goal-second": "open",
        }
        self.goal_request_ids = {
            "goal-first": ["request-first"],
            "goal-second": ["request-second"],
        }

    def active_goal_snapshots(self):
        return [
            {
                "goal_id": goal_id,
                "responsibility_status": status,
            }
            for goal_id, status in self.goal_status.items()
            if status == "open"
        ]

    def goal_cancellation_bindings(self, goal_ids):
        return [
            {
                "goal_id": goal_id,
                "found": goal_id in self.goal_status,
                "responsibility_status": self.goal_status.get(goal_id, ""),
                "canonical_plan_id": self.plan_id,
                "canonical_plan_fingerprint": self.plan_fingerprint,
                "request_ids": list(self.goal_request_ids.get(goal_id, [])),
            }
            for goal_id in goal_ids
        ]

    def update_pending_task_status_for_request_id(self, *, request_id: str, status: str):
        self.status_updates.append((request_id, status))

    def record_interaction_response(self, _sid, response, **_kwargs):
        self.recorded_agent_results.append(response)


class _AgentClient:
    def __init__(self) -> None:
        self.requests = []

    async def resolve_fast_plan(self, _session, *, request, timeout_ms):
        del timeout_ms
        self.requests.append(request)
        evidence = request.context["trusted_terminal_evidence"][0]
        goal_ids = request.context["result_evidence_reentry"]["source_goal_ids"]
        return CanonicalPlan(
            plan_id=f"plan-reentry-{evidence['evidence_id']}",
            planner_tier="fast",
            disposition="respond",
            coverage="complete",
            confidence=1.0,
            goal_ids=goal_ids,
            response_text=evidence["data"]["user_summary"],
            goal_outcomes=[
                {
                    "goal_id": goal_id,
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": evidence["data"]["user_summary"],
                }
                for goal_id in goal_ids
            ],
            goal_satisfaction={
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        )


class _Sessions:
    def __init__(self) -> None:
        self.current_sid = "sid-detached"
        self.state = {"sid-detached": {}}


def _response() -> InteractionResponse:
    plan = CanonicalPlan(
        plan_id="plan-detached-reentry",
        planner_tier="fast",
        disposition="execute",
        coverage="complete",
        confidence=1.0,
        goal_ids=["goal-first", "goal-second"],
        goal_summary="Run two reads.",
        steps=[
            {
                "step_id": "step-first",
                "capability_id": "chromie.test.first",
                "args": {},
                "timing": "parallel",
                "source_goal_ids": ["goal-first"],
            },
            {
                "step_id": "step-second",
                "capability_id": "chromie.test.second",
                "args": {},
                "timing": "parallel",
                "source_goal_ids": ["goal-second"],
            },
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-first",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["step-first"],
            },
            {
                "goal_id": "goal-second",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["step-second"],
            },
        ],
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": ["goal-first", "goal-second"],
        },
    )
    fingerprint = canonical_plan_fingerprint(plan)
    completion_digest = claim_qualification_policy_sha256(
        schema_valid_completion_evidence_policy()
    )

    def request(request_id: str, capability_id: str, step_id: str, goal_id: str):
        return CapabilityRequest(
            request_id=request_id,
            capability_id=capability_id,
            timing="parallel",
            committed_output_schema_sha256=output_schema_sha256(_SCHEMA),
            committed_completion_evidence_sha256=completion_digest,
            metadata={
                "source": "goal_driven_canonical_plan",
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "step_id": step_id,
                "source_goal_ids": [goal_id],
            },
        )

    return InteractionResponse(
        interaction_id="interaction-detached-reentry",
        capabilities=[
            request("request-first", "chromie.test.first", "step-first", "goal-first"),
            request("request-second", "chromie.test.second", "step-second", "goal-second"),
        ],
        speech=[
            {
                "id": "speech-preauthored-final",
                "text": "Both reads succeeded.",
                "timing": "after_capabilities",
            }
        ],
        metadata={
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "turn_id": "turn-detached-reentry",
            "language": "en-US",
            "canonical_plan": plan.model_dump(mode="json"),
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": fingerprint,
            "goal_interpretation": {
                "responsibilities": [
                    {
                        "local_ref": "read-first",
                        "outcome": "Obtain the first requested result.",
                        "output_mode": "information",
                        "relationship": "new",
                        "confidence": 1.0,
                    },
                    {
                        "local_ref": "read-second",
                        "outcome": "Obtain the second requested result.",
                        "output_mode": "information",
                        "relationship": "new",
                        "confidence": 1.0,
                    },
                ]
            },
            "goal_association": {
                "resolution_status": "resolved",
                "turn_id": "turn-detached-reentry",
                "associations": [],
                "new_goals": [
                    {
                        "goal_id": "goal-first",
                        "description": "Run the first read.",
                        "source_text": "Run both reads.",
                        "source_responsibility_refs": ["read-first"],
                    },
                    {
                        "goal_id": "goal-second",
                        "description": "Run the second read.",
                        "source_text": "Run both reads.",
                        "source_responsibility_refs": ["read-second"],
                    },
                ],
                "confidence": 1.0,
            },
            "user_turn_envelope": {
                "turn_id": "turn-detached-reentry",
                "normalized_input": {
                    "text": "Run both reads.",
                    "language": "en-US",
                },
            },
        },
    )


def _assistant(coordinator: InteractionRuntimeCoordinator) -> VoiceAssistant:
    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.interaction_runtime = coordinator
    assistant.playback_generation = 0
    assistant.sessions = _Sessions()
    assistant.conversation_state = _ConversationState()
    assistant.agent_client = _AgentClient()
    assistant.cognitive_runtime = SimpleNamespace(
        adapter=CanonicalPlanRuntimeAdapter(coordinator),
        interaction_ledger=None,
    )
    assistant.cognitive_runtime_policy = SimpleNamespace(fast_planner_timeout_ms=1000)
    assistant.active_interaction_task = None
    assistant.active_interaction_id = None
    assistant.active_interaction_tasks = {}
    assistant.active_cognitive_runtime_tasks = {}
    assistant.cognitive_turn_closure = None
    assistant.session_log = lambda *_args, **_kwargs: None
    assistant.maybe_session_done = lambda _sid: None
    assistant._record_execution_experience_safely = lambda **_kwargs: None

    async def reset_playback_ordering(self):
        return None

    async def get_http_session(self):
        return object()

    async def close_execution(self, **_kwargs):
        return "final_closed"

    def build_context(self, _session_id):
        # This fixture intentionally bypasses full VoiceAssistant construction.
        # Evidence re-entry needs only bounded dialogue/Goal context; do not make
        # the unit test depend on unrelated Mind/audio/runtime collaborators.
        return {
            "history": [],
            "active_goal_snapshots": self.conversation_state.active_goal_snapshots(),
        }

    assistant.reset_playback_ordering = MethodType(reset_playback_ordering, assistant)
    assistant.build_context = MethodType(build_context, assistant)
    assistant.get_http_session = MethodType(get_http_session, assistant)
    assistant._close_cognitive_execution = MethodType(close_execution, assistant)
    return assistant


@pytest.mark.asyncio
async def test_multi_capability_result_reentry_projects_only_terminal_sibling_scope():
    spoken: list[str] = []

    async def schedule_speech(args: dict[str, Any]) -> dict[str, Any]:
        spoken.append(str(args["text"]))
        return {"scheduled": True, "playback_started": True}

    coordinator = InteractionRuntimeCoordinator(schedule_speech)
    provider = _TwoResultProvider()
    for capability_id in ("chromie.test.first", "chromie.test.second"):
        coordinator.registry.register(
            CapabilityDefinition(
                capability_id=capability_id,
                provider_id=provider.provider_id,
                output_schema=_SCHEMA,
                can_run_parallel=True,
            )
        )
    coordinator.runtime.register_provider(provider)
    assistant = _assistant(coordinator)
    response = _response()

    assistant._launch_interaction(
        response,
        "sid-detached",
        reset_playback=False,
    )
    foreground = assistant.active_interaction_task
    assert foreground is not None

    await asyncio.wait_for(provider.first_started.wait(), timeout=1.0)
    await asyncio.wait_for(provider.second_started.wait(), timeout=1.0)
    await asyncio.wait_for(asyncio.shield(foreground), timeout=1.0)

    # The foreground interaction task is gone while Runtime-owned provider work
    # and a distinct result-consumer task remain alive.
    assert foreground.done()
    observation = await coordinator.runtime.execution_observation()
    assert "interaction-detached-reentry" in observation.open_interaction_ids
    assert len(assistant.active_cognitive_runtime_tasks) == 1
    result_task = next(iter(assistant.active_cognitive_runtime_tasks))
    assert not result_task.done()

    provider.release_first.set()
    await asyncio.sleep(0.05)

    assert spoken == ["first result"]
    assert "Both reads succeeded." not in spoken
    assert not provider.release_second.is_set()
    assert len(assistant.agent_client.requests) == 1
    first_request = assistant.agent_client.requests[0]
    assert first_request.text == "Obtain the first requested result."
    assert first_request.original_user_text == first_request.text
    assert "user_turn_envelope" not in first_request.context
    assert first_request.context["result_evidence_reentry"]["source_goal_ids"] == [
        "goal-first"
    ]
    first_truth = first_request.context["trusted_execution_outcome"]
    assert first_truth["aggregate_status"] == "completed"
    assert first_truth["goal_outcomes"][0]["goal_id"] == "goal-first"
    assert first_truth["goal_outcomes"][0]["status"] == "completed"
    assert first_truth["goal_outcomes"][0]["evidence_ids"]
    assert [item.outcome for item in first_request.responsibilities] == [
        "Obtain the first requested result."
    ]

    # Each exact sibling result remains an immediate cognitive opportunity, while
    # its Planner transaction cannot see the other sibling's source semantics.
    provider.release_second.set()
    await asyncio.wait_for(asyncio.shield(result_task), timeout=1.0)
    assert result_task.done()
    assert "Both reads succeeded." not in spoken
    assert len(assistant.agent_client.requests) == 2


@pytest.mark.asyncio
async def test_current_interaction_runtime_ownership_survives_foreground_cleanup():
    coordinator = InteractionRuntimeCoordinator(
        lambda _args: {"scheduled": True, "playback_started": True}
    )
    provider = _TwoResultProvider()
    for capability_id in ("chromie.test.first", "chromie.test.second"):
        coordinator.registry.register(
            CapabilityDefinition(
                capability_id=capability_id,
                provider_id=provider.provider_id,
                output_schema=_SCHEMA,
                can_run_parallel=True,
            )
        )
    coordinator.runtime.register_provider(provider)
    assistant = _assistant(coordinator)
    response = _response()

    assistant._launch_interaction(response, "sid-detached", reset_playback=False)
    foreground = assistant.active_interaction_task
    assert foreground is not None
    await asyncio.wait_for(provider.first_started.wait(), timeout=1.0)
    await asyncio.wait_for(provider.second_started.wait(), timeout=1.0)
    await asyncio.wait_for(asyncio.shield(foreground), timeout=1.0)

    observation = await coordinator.runtime.execution_observation()
    assert observation.open_interaction_ids == ["interaction-detached-reentry"]

    provider.release_first.set()
    provider.release_second.set()
    result_task = next(iter(assistant.active_cognitive_runtime_tasks))
    await asyncio.wait_for(asyncio.shield(result_task), timeout=1.0)


@pytest.mark.asyncio
async def test_late_result_from_superseded_plan_keeps_evidence_but_cannot_speak():
    spoken: list[str] = []

    async def schedule_speech(args: dict[str, Any]) -> dict[str, Any]:
        spoken.append(str(args["text"]))
        return {"scheduled": True, "playback_started": True}

    coordinator = InteractionRuntimeCoordinator(schedule_speech)
    provider = _TwoResultProvider()
    for capability_id in ("chromie.test.first", "chromie.test.second"):
        coordinator.registry.register(
            CapabilityDefinition(
                capability_id=capability_id,
                provider_id=provider.provider_id,
                output_schema=_SCHEMA,
                can_run_parallel=True,
            )
        )
    coordinator.runtime.register_provider(provider)
    assistant = _assistant(coordinator)
    response = _response()

    assistant._launch_interaction(response, "sid-detached", reset_playback=False)
    foreground = assistant.active_interaction_task
    assert foreground is not None
    await asyncio.wait_for(provider.first_started.wait(), timeout=1.0)
    await asyncio.wait_for(provider.second_started.wait(), timeout=1.0)
    await asyncio.wait_for(asyncio.shield(foreground), timeout=1.0)

    # The same Goal remains open, but Host state has committed a replacement plan.
    assistant.conversation_state.plan_id = "plan-replacement"
    assistant.conversation_state.plan_fingerprint = "f" * 64
    provider.release_first.set()
    for _ in range(100):
        prepared = next(iter(assistant.active_cognitive_runtime_tasks), None)
        if prepared is not None and response.metadata.get("suppressed_terminal_reentry"):
            break
        await asyncio.sleep(0.01)

    assert spoken == []
    assert assistant.agent_client.requests == []

    provider.release_second.set()
    result_task = next(iter(assistant.active_cognitive_runtime_tasks))
    await asyncio.wait_for(asyncio.shield(result_task), timeout=1.0)


@pytest.mark.asyncio
async def test_late_result_after_goal_cancellation_cannot_reenter_speech():
    spoken: list[str] = []

    async def schedule_speech(args: dict[str, Any]) -> dict[str, Any]:
        spoken.append(str(args["text"]))
        return {"scheduled": True, "playback_started": True}

    coordinator = InteractionRuntimeCoordinator(schedule_speech)
    provider = _TwoResultProvider()
    for capability_id in ("chromie.test.first", "chromie.test.second"):
        coordinator.registry.register(
            CapabilityDefinition(
                capability_id=capability_id,
                provider_id=provider.provider_id,
                output_schema=_SCHEMA,
                can_run_parallel=True,
            )
        )
    coordinator.runtime.register_provider(provider)
    assistant = _assistant(coordinator)
    response = _response()

    assistant._launch_interaction(response, "sid-detached", reset_playback=False)
    foreground = assistant.active_interaction_task
    assert foreground is not None
    await asyncio.wait_for(provider.first_started.wait(), timeout=1.0)
    await asyncio.wait_for(provider.second_started.wait(), timeout=1.0)
    await asyncio.wait_for(asyncio.shield(foreground), timeout=1.0)

    assistant.conversation_state.goal_status["goal-first"] = "cancelled"
    provider.release_first.set()
    for _ in range(100):
        if response.metadata.get("suppressed_terminal_reentry"):
            break
        await asyncio.sleep(0.01)

    assert spoken == []
    assert assistant.agent_client.requests == []

    provider.release_second.set()
    result_task = next(iter(assistant.active_cognitive_runtime_tasks))
    await asyncio.wait_for(asyncio.shield(result_task), timeout=1.0)

class _FollowUpProvider:
    provider_id = "test.followup"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        del definition, context
        self.started.set()
        await self.release.wait()
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            status="completed",
            output={"user_summary": "follow-up result"},
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        del request, definition, context


class _FollowUpAgentClient(_AgentClient):
    async def resolve_fast_plan(self, _session, *, request, timeout_ms):
        del timeout_ms
        self.requests.append(request)
        evidence = request.context["trusted_terminal_evidence"][0]
        goal_ids = request.context["result_evidence_reentry"]["source_goal_ids"]
        if evidence["tool_id"] == "chromie.test.first":
            return CanonicalPlan(
                plan_id=f"plan-follow-up-{evidence['evidence_id']}",
                planner_tier="fast",
                disposition="execute",
                coverage="complete",
                confidence=1.0,
                goal_ids=goal_ids,
                steps=[
                    {
                        "step_id": "step-follow-up",
                        "capability_id": "chromie.test.followup",
                        "args": {},
                        "timing": "sequential",
                        "source_goal_ids": goal_ids,
                    }
                ],
                goal_outcomes=[
                    {
                        "goal_id": goal_id,
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-follow-up"],
                    }
                    for goal_id in goal_ids
                ],
                goal_satisfaction={
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": goal_ids,
                },
            )
        return await super().resolve_fast_plan(
            _session,
            request=request,
            timeout_ms=1000,
        )


@pytest.mark.asyncio
async def test_terminal_evidence_can_start_follow_up_work_while_sibling_is_running():
    coordinator = InteractionRuntimeCoordinator(
        lambda _args: {"scheduled": True, "playback_started": True}
    )
    provider = _TwoResultProvider()
    for capability_id in ("chromie.test.first", "chromie.test.second"):
        coordinator.registry.register(
            CapabilityDefinition(
                capability_id=capability_id,
                provider_id=provider.provider_id,
                output_schema=_SCHEMA,
                can_run_parallel=True,
            )
        )
    coordinator.runtime.register_provider(provider)

    follow_up = _FollowUpProvider()
    coordinator.registry.register(
        CapabilityDefinition(
            capability_id="chromie.test.followup",
            provider_id=follow_up.provider_id,
            output_schema=_SCHEMA,
        )
    )
    coordinator.runtime.register_provider(follow_up)

    assistant = _assistant(coordinator)
    assistant.agent_client = _FollowUpAgentClient()
    response = _response()

    assistant._launch_interaction(response, "sid-detached", reset_playback=False)
    foreground = assistant.active_interaction_task
    assert foreground is not None
    await asyncio.wait_for(provider.first_started.wait(), timeout=1.0)
    await asyncio.wait_for(provider.second_started.wait(), timeout=1.0)
    await asyncio.wait_for(asyncio.shield(foreground), timeout=1.0)

    # One terminal sibling is enough to create a cognitive opportunity. Planner may
    # schedule genuinely new Work without waiting for the unrelated sibling to finish.
    provider.release_first.set()
    await asyncio.wait_for(follow_up.started.wait(), timeout=1.0)

    assert not provider.release_second.is_set()
    assert len(assistant.agent_client.requests) == 1
    request = assistant.agent_client.requests[0]
    assert request.context["terminal_request_id"] == "request-first"
    assert request.context["result_evidence_reentry"]["source_goal_ids"] == [
        "goal-first"
    ]
    assert "goal-first" in request.context["situation"].get("focus_goal_ids", [])

    # Clean up provider work. The important assertion is that follow-up Work became
    # ready before the original second sibling reached terminal state.
    assistant.conversation_state.goal_status["goal-first"] = "cancelled"
    provider.release_second.set()
    follow_up.release.set()
    for task in list(assistant.active_cognitive_runtime_tasks):
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
