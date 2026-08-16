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
from shared.chromie_contracts.execution_outcome import claim_qualification_policy_sha256
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    InteractionResponse,
    output_schema_sha256,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import canonical_plan_fingerprint
from shared.chromie_contracts.tool_result import ToolResultInterpretation


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

    def active_goal_snapshots(self):
        return [
            {
                "goal_id": "goal-first",
                "responsibility_status": "open",
            },
            {
                "goal_id": "goal-second",
                "responsibility_status": "open",
            },
        ]

    def update_pending_task_status_for_request_id(self, *, request_id: str, status: str):
        self.status_updates.append((request_id, status))

    def record_agent_result(self, _sid, response, **_kwargs):
        self.recorded_agent_results.append(response)


class _AgentClient:
    def __init__(self) -> None:
        self.requests = []

    async def interpret_tool_result(self, _session, *, request, timeout_ms):
        del timeout_ms
        self.requests.append(request)
        evidence = request.evidence[0]
        return ToolResultInterpretation(
            status="resolved",
            spoken_response=evidence.data["user_summary"],
            selected_facts=[
                {
                    "evidence_id": evidence.evidence_id,
                    "json_pointer": "/user_summary",
                }
            ],
            confidence=1.0,
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
    assistant.tool_result_interpreter_timeout_ms = 1000
    assistant.active_interaction_task = None
    assistant.active_interaction_id = None
    assistant.active_interaction_tasks = {}
    assistant.active_interaction_reservations = {}
    assistant.active_capability_result_tasks = {}
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

    assistant.reset_playback_ordering = MethodType(reset_playback_ordering, assistant)
    assistant.get_http_session = MethodType(get_http_session, assistant)
    assistant._close_cognitive_execution = MethodType(close_execution, assistant)
    return assistant


@pytest.mark.asyncio
async def test_foreground_dispatch_finishes_while_provider_work_remains_running():
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
    assert len(assistant.active_capability_result_tasks) == 1
    result_task = next(iter(assistant.active_capability_result_tasks))
    assert not result_task.done()

    provider.release_first.set()
    for _ in range(100):
        if spoken:
            break
        await asyncio.sleep(0.01)

    assert spoken == ["first result"]
    assert "Both reads succeeded." not in spoken
    assert not provider.release_second.is_set()
    assert len(assistant.agent_client.requests) == 1
    interpretation_request = assistant.agent_client.requests[0]
    assert interpretation_request.context["incremental_terminal_evidence"] is True
    assert interpretation_request.context["terminal_request_id"] == "request-first"
    assert response.metadata.get("incremental_cognitive_opportunities") is None

    # The detached coordinator uses the prepared response for re-entry metadata;
    # result arrival is internal state, never a fabricated user turn.
    provider.release_second.set()
    await asyncio.wait_for(asyncio.shield(result_task), timeout=1.0)
    assert result_task.done()
    assert "Both reads succeeded." not in spoken


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
    result_task = next(iter(assistant.active_capability_result_tasks))
    await asyncio.wait_for(asyncio.shield(result_task), timeout=1.0)
