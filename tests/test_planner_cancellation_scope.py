"""Cancellation reporting through real Schema, Planner, adapter and delivery owners.

Model replies and speech completion are scripted; these are Level A regressions.
"""
from __future__ import annotations

import asyncio
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from agent.app.deep_planner import DeepPlannerResolver
from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_context import planner_goal_context
from benchmarks.datasets.fast_planner_daily_life.deep_qualification import load_cases
from benchmarks.datasets.fast_planner_daily_life.qualification import (
    CaptureModel, ReplayModel, StaticCatalog, materialize_catalog,
)
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from tests.test_cognitive_runtime_pr7 import FakeRuntime


def case_request(language, control, available=True):
    suffix = f'08_{"supported" if control == "released" else "boundary"}_{language}'
    case = copy.deepcopy(next(c for c in load_cases()
                              if 'cancellation_revision' in c['id'] and c['id'].endswith(suffix)))
    evidence = case['input']['request']['context']['trusted_goal_cancellation_evidence'][0]
    if control in ('not_cancelled', 'uncertain'):
        evidence.update(status=control, goal_state_reconciled=False,
                        reason_code='cancellation_not_verified')
    entries = materialize_catalog(case['input'])
    for entry in entries:
        if entry['capability_id'] == 'chromie.reminder.create':
            entry['available'] = available
    return CognitiveWorkRequest.model_validate(case['input']['request']), entries


def report(request):
    gid = request.planner_reentry_scope.goal_ids[0]
    evidence = request.context['trusted_goal_cancellation_evidence'][0]
    speech = {'cancelled': 'That reminder is cancelled.',
              'not_cancelled': 'That reminder has not been cancelled.',
              'uncertain': 'I could not verify that the reminder was cancelled.'}[evidence['status']]
    if evidence['released_confirmation_goal_ids']:
        speech = 'The reminder remains pending; the previous confirmation no longer applies.'
    satisfaction = dict(score=0.0, status='unsatisfied', satisfied_goal_ids=[],
                        unmet_goal_ids=[gid], unmet_requirements=['The original reminder is not created.'],
                        rationale='Control reporting does not fulfill the original effect.')
    return dict(disposition='respond', coverage='complete', confidence=0.99,
                goal_summary='Report the trusted control result.', response_text=speech,
                steps=[], auxiliary_activities=[], escalation_reason='', unresolved=[],
                parameter_resolutions=[], time_conditions=[], plan_relation='exact',
                user_confirmation_required=False, goal_satisfaction=copy.deepcopy(satisfaction),
                goal_outcomes={gid: dict(disposition='respond', coverage='complete',
                    response_text=speech, unresolved=[], step_ids=[], satisfaction=satisfaction,
                    rationale='Report the exact trusted control facts.')})


@pytest.mark.parametrize('resolver', [FastPlannerResolver, DeepPlannerResolver])
@pytest.mark.parametrize('language', ['en', 'zh'])
@pytest.mark.parametrize('control', ['cancelled', 'released', 'not_cancelled', 'uncertain'])
@pytest.mark.parametrize('available', [True, False])
def test_control_report_preserves_catalog_truth_and_unmet_effect(resolver, language, control, available):
    async def run():
        request, entries = case_request(language, control, available)
        capture = CaptureModel()
        await resolver(capture, StaticCatalog(entries)).resolve(request)
        assert len(capture.calls) == 1
        call = capture.calls[0]
        facts, _ = json.JSONDecoder().raw_decode(
            call['prompt'].split('Catalog facts for control reporting JSON:\n', 1)[1])
        reminder = next(row for row in facts if row['capability_id'] == 'chromie.reminder.create')
        assert reminder['available'] is available
        assert request.context['goal_association_resolution']['new_goals'][0]['metadata']['output_mode'] == 'stateful_effect'
        raw = report(request)
        assert not list(Draft202012Validator(call['response_format']).iter_errors(raw))
        replay = ReplayModel(json.dumps(raw))
        plan = await resolver(replay, StaticCatalog(entries)).resolve(request)
        assert replay.calls == 1
        assert plan.disposition == 'respond', plan.metadata
        assert not plan.steps and not plan.auxiliary_activities and not plan.time_conditions
        assert plan.goal_satisfaction.score == 0
        assert plan.goal_satisfaction.unmet_goal_ids == list(request.planner_reentry_scope.goal_ids)
    asyncio.run(run())


@pytest.mark.parametrize('resolver', [FastPlannerResolver, DeepPlannerResolver])
@pytest.mark.parametrize('mutation', ['fake_fulfillment', 'confirmation', 'reschedule', 'extra_work'])
def test_control_scope_rejects_false_completion_and_execution(resolver, mutation):
    async def run():
        request, entries = case_request('en', 'cancelled')
        raw = report(request); gid = request.planner_reentry_scope.goal_ids[0]
        if mutation == 'fake_fulfillment':
            for sat in (raw['goal_satisfaction'], raw['goal_outcomes'][gid]['satisfaction']):
                sat.update(score=1, status='exact', satisfied_goal_ids=[gid], unmet_goal_ids=[], unmet_requirements=[])
        elif mutation == 'confirmation':
            raw['user_confirmation_required'] = True
        elif mutation == 'reschedule':
            raw['time_conditions'] = [dict(goal_id=gid, due_at_ms=4092106800000, reason='Retry later')]
        else:
            raw['disposition'] = raw['goal_outcomes'][gid]['disposition'] = 'execute'
            raw['steps'] = [dict(step_id='retry', capability_id='chromie.reminder.create',
                args=dict(reminder_text='call home', due_at='2026-09-03T20:00:00+08:00'),
                source_goal_ids=[gid], timing='sequential')]
            raw['goal_outcomes'][gid]['step_ids'] = ['retry']
        capture = CaptureModel(); await resolver(capture, StaticCatalog(entries)).resolve(request)
        assert list(Draft202012Validator(capture.calls[0]['response_format']).iter_errors(raw))
        replay = ReplayModel(json.dumps(raw))
        plan = await resolver(replay, StaticCatalog(entries)).resolve(request)
        assert replay.calls == 1
        assert plan.metadata.get('reason') or plan.metadata.get('error_type') or plan.metadata.get('failure_class')
        assert not plan.steps
    asyncio.run(run())


def test_cancellation_scope_preserves_independent_effect_goal_execution():
    request, _ = case_request('en', 'cancelled')
    context = copy.deepcopy(request.context)
    sibling = copy.deepcopy(context['goal_association_resolution']['new_goals'][0])
    sibling.update(goal_id='independent', metadata={'output_mode': 'stateful_effect'})
    context['goal_association_resolution']['new_goals'].append(sibling)
    projected = planner_goal_context(context)
    assert projected.requires_execution
    assert not projected.response_only
    assert 'independent' not in projected.response_goal_ids


@pytest.mark.parametrize('control', ['cancelled', 'released'])
def test_delivering_control_report_does_not_fulfill_original_goal(control):
    async def run():
        request, entries = case_request('en', control)
        plan = await FastPlannerResolver(ReplayModel(json.dumps(report(request))), StaticCatalog(entries)).resolve(request)
        adapter = CanonicalPlanRuntimeAdapter(FakeRuntime())
        response = await adapter.build_planner_owned_response(plan=plan, session_id=request.sid, language='en-US')
        manager = ConversationStateManager(base_conversation_id='control-delivery')
        manager.apply_goal_association_resolution(request.context['goal_association_resolution'],
            sid=request.sid, user_text=request.text, atomic=True)
        gid = plan.goal_ids[0]
        goal = manager._task_context_by_goal_id(gid)
        if control == 'cancelled':
            manager._set_goal_responsibility_status(goal, 'cancelled', source='trusted_control')
        manager.record_interaction_response(request.sid, response)
        assert response.speech and not response.capabilities
        for speech in response.speech:
            manager.update_pending_task_status_for_request_id(request_id=speech.id, status='completed')
        assert manager._goal_responsibility_status(goal) == ('cancelled' if control == 'cancelled' else 'open')
    asyncio.run(run())
