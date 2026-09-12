"""Real aggregate closure and owned Reflection lifecycle with controlled model waits."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.app.reflection import ReflectionResolver
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from orchestrator.runtime.mind import MindManager
from orchestrator.runtime.shutdown_lifecycle import shutdown_voice_assistant
from shared.chromie_contracts.interaction import CapabilityResult
from shared.chromie_contracts.execution_outcome import ExecutionOutcomeBundle
from shared.chromie_contracts.reflection import ReflectionResolution
from tests.test_cognitive_turn_loop_closure import (
    CognitiveTurnLoopClosureTests, _Runtime, _plan, _response,
)


def episode(timeout_ms=125000, perspective='Curiosity deserves patient attention.'):
    plan = _plan(); response = _response(plan)
    execution = CapabilityRuntimeResult(interaction_id=response.interaction_id, status='failed', results=[
        CapabilityResult(request_id='request-first', capability_id='chromie.test.first',
                         provider_id='test.provider', status='failed', reason_code='provider_failed'),
        CapabilityResult(request_id='request-second', capability_id='chromie.test.second',
                         provider_id='test.provider', status='completed', output={'user_summary': 'Second completed.'}),
    ])
    host, sid, _ = CognitiveTurnLoopClosureTests()._assistant(_Runtime(execution), response)
    host.cognitive_runtime_policy = SimpleNamespace(deep_planner_timeout_ms=timeout_ms)
    mind = MindManager().context()
    mind['worldview']['household_perspectives'] = [perspective]
    mind['private_session_payload'] = 'PRIVATE_MARKER_MUST_NOT_TRANSFER'
    host.mind = SimpleNamespace(context=lambda: mind)
    started, release, exited = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests, planner_calls, ordering = [], [], []

    async def reflect(session, *, request, **kwargs):
        requests.append(request); ordering.append('reflection_started'); started.set()
        try:
            await release.wait()
            return ReflectionResolution(opportunity_id=request.opportunity.opportunity_id,
                goal_ids=request.opportunity.goal_ids, evidence_refs=request.opportunity.evidence_refs,
                reason_codes=request.opportunity.reason_codes, actions=['replan'],
                reason_summary='Recorded diagnostic proposal, never a second result review.')
        finally:
            exited.set()

    async def session():
        return None

    async def result_planner(**kwargs):
        ordering.append('planner_started'); planner_calls.append(kwargs)
        ordering.append('planner_finished'); return None

    host.agent_client = SimpleNamespace(resolve_reflection=reflect)
    host.get_http_session = session
    host._outcome_response_is_stale = lambda **kwargs: False
    host._plan_evidence_bound_capability_result_response = result_planner
    return host, sid, response, execution, started, release, exited, requests, planner_calls, ordering


async def start_episode(values):
    host, sid, response, execution, started, *_ = values
    result = await asyncio.wait_for(host._close_cognitive_execution(response=response,
        execution=execution, session_id=sid, generation=4, provider_status=None), 2)
    await asyncio.wait_for(started.wait(), 2)
    assert result == 'planner_reentry_unavailable'
    return list(host.active_cognitive_runtime_tasks)


@pytest.mark.parametrize('perspective', ['Curiosity deserves patient attention.', 'Consider how choices affect others.'])
def test_ready_result_precedes_blocked_reflection_and_mind_crosses_real_request(perspective):
    async def run():
        values = episode(perspective=perspective)
        host, _, response, _, _, release, _, requests, planner_calls, ordering = values
        tasks = await start_episode(values)
        assert ordering == ['planner_started', 'planner_finished', 'reflection_started']
        assert len(planner_calls) == 1 and not tasks[0].done()
        request = requests[0]
        assert perspective in str(request.context['mind'])
        assert 'PRIVATE_MARKER' not in str(request.context['mind'])
        prompt = ReflectionResolver(None)._prompt(request, request.opportunity)
        assert perspective in prompt
        assert 'worldview/values JSON:\nnull' not in prompt
        host._schedule_outcome_reflection(response=response, plan=_plan(),
            bundle=ExecutionOutcomeBundle.model_validate(request.context['execution_outcome_bundle']),
            opportunities=[request.opportunity], session_id=values[1], generation=4)
        await asyncio.sleep(0)
        assert len(requests) == 1 and len(host.active_cognitive_runtime_tasks) == 1
        release.set(); await asyncio.gather(*tasks); await asyncio.sleep(0)
        assert len(planner_calls) == 1
        assert not host.active_cognitive_runtime_tasks
        assert response.metadata['reflection_state_results']
        assert all(not row['applied'] for row in response.metadata['reflection_state_results'])
        assert 'reflection_advisories' not in str(planner_calls)
    asyncio.run(run())


@pytest.mark.parametrize('ending', ['cancel', 'timeout', 'shutdown', 'stale', 'terminal'])
def test_background_reflection_expires_drains_and_cannot_reopen_goal(ending):
    async def run():
        values = episode(timeout_ms=30 if ending == 'timeout' else 125000)
        host, _, response, _, _, release, exited, requests, planner_calls, _ = values
        tasks = await start_episode(values)
        goal = host.conversation_state._task_context_by_goal_id(requests[0].opportunity.goal_ids[0])
        if ending == 'cancel':
            for task in tasks: task.cancel()
        elif ending == 'shutdown':
            host.sessions = None
            host.playback_start_waiters = {}
            async def close_output(): return None
            await shutdown_voice_assistant(host, close_output_stream=close_output)
        elif ending == 'stale':
            host.playback_generation += 1; release.set()
        elif ending == 'terminal':
            host.conversation_state._set_goal_responsibility_status(goal, 'satisfied', source='trusted_delivery')
            release.set()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 2)
        await asyncio.sleep(0)
        assert exited.is_set() and not host.active_cognitive_runtime_tasks
        assert len(planner_calls) == 1
        if ending == 'terminal':
            assert host.conversation_state._goal_responsibility_status(goal) == 'satisfied'
            assert response.metadata['reflection_state_results'][0]['rejected_actions'] == ['replan']
        else:
            assert 'reflection_state_results' not in response.metadata
    asyncio.run(run())
