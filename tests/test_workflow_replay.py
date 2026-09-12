"""Frozen references exercise real role HTTP, contracts and asynchronous Runtime."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from benchmarks.integration.model_replay import ModelReplay, ReplayMismatch
from benchmarks.datasets.fast_planner_daily_life.qualification import ReplayModel, StaticCatalog
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.fast_planner import FastPlannerResolver
from tests.workflow_replay_support import Episode, controlled_runtime, run_case
from benchmarks.integration.model_replay import ReplayServer

CASES = Path(__file__).resolve().parents[1]/'benchmarks/integration/scenarios'


def load(name='normal'):
    return json.loads((CASES/f'workflow-{name}.json').read_text())


@pytest.mark.parametrize('path', sorted(CASES.glob('workflow-*.json')), ids=lambda p:p.stem)
def test_frozen_episode(path, tmp_path):
    case = json.loads(path.read_text())
    result = asyncio.run(run_case(case, tmp_path))
    assert result['passed'] and not result['model_ability_evaluated']
    assert result['model_calls'] == len(case['model_steps'])


@pytest.mark.parametrize('mutation', ['order','text','schema','option','path'])
def test_request_mismatch_is_sticky(mutation):
    case = load()
    request = copy.deepcopy(case['model_steps'][0]['request'])
    path = '/api/chat'
    if mutation == 'order':
        request = case['model_steps'][1]['request']
    elif mutation == 'text':
        request['messages'][-1]['content'] += 'different admitted turn'
    elif mutation == 'schema':
        request['format'] = {'type':'object'}
    elif mutation == 'option':
        request['stream'] = True
    else:
        path = '/api/generate'
    replay = ModelReplay(case)
    with pytest.raises(ReplayMismatch, match='request mismatch'):
        replay.reply(path, request)
    with pytest.raises(ReplayMismatch):
        replay.reply('/api/chat', case['model_steps'][0]['request'])
    assert replay.position == 0 and not replay.records


def test_unused_extra_and_unbound_replies_fail():
    case = load()
    replay = ModelReplay(case)
    with pytest.raises(ReplayMismatch, match='unused'):
        replay.assert_finished()
    with pytest.raises(ReplayMismatch, match='unbound'):
        replay.materialize({'goal':'${goal}'})
    case['model_steps'] = case['model_steps'][:1]
    replay = ModelReplay(case)
    replay.reply('/api/chat', case['model_steps'][0]['request'])
    replay.assert_finished()
    with pytest.raises(ReplayMismatch, match='extra'):
        replay.reply('/api/chat', case['model_steps'][0]['request'])


def test_actual_changed_evidence_does_not_receive_frozen_next_plan(tmp_path):
    case = load('conditional-rain')
    case['provider_outputs']['chromie.weather.lookup']['rain_forecast'] = False
    replay = ModelReplay(case)
    with pytest.raises(AssertionError):
        asyncio.run(run_case(case, tmp_path, replay))
    assert replay.errors == ['request mismatch at fast-result']
    assert replay.position == 3


@pytest.mark.parametrize('count', [None, 3])
def test_bad_effect_reply_rejected_before_provider_dispatch(count, tmp_path):
    case = load()
    args = case['model_steps'][2]['response']['steps'][0]['args']
    if count is None:
        args.pop('count')
    else:
        args['count'] = count
    replay = ModelReplay(case)
    async def check():
        with ReplayServer(replay) as server, controlled_runtime():
            episode = Episode(case, replay, server.url, tmp_path)
            with pytest.raises(AssertionError, match='contract failure'):
                await episode.begin()
            assert not episode.provider.calls
            assert replay.records[-1]['schema_errors']
    asyncio.run(check())


@pytest.mark.parametrize('tier', ['fast','deep'])
@pytest.mark.parametrize('mutation', ['valid','label_only','false_completion','missing_obligation','information_quantity'])
def test_acquisition_count_exception_requires_complete_deferred_effect(tier, mutation, tmp_path):
    case = load('conditional-rain')
    replay = ModelReplay(case)
    async def check():
        with ReplayServer(replay) as server, controlled_runtime():
            episode = Episode(case, replay, server.url, tmp_path)
            await episode.begin()
            request = episode.request.model_copy(deep=True)
            raw = replay.materialize(case['model_steps'][2]['response'])
            catalog = copy.deepcopy(case['catalog'])
            gid = episode.goal
            if mutation == 'label_only':
                for capability in catalog:
                    if capability['capability_id'] == 'chromie.weather.lookup':
                        capability['effects'] = ['state_change']
            elif mutation == 'false_completion':
                for sat in (raw['goal_satisfaction'], raw['goal_outcomes'][gid]['satisfaction']):
                    sat.update(score=1.0, status='exact', unmet_goal_ids=[], satisfied_goal_ids=[gid])
            elif mutation == 'missing_obligation':
                raw['goal_outcomes'][gid]['satisfaction']['unmet_requirements'] = []
            elif mutation == 'information_quantity':
                request.context['goal_association_resolution']['new_goals'][0]['metadata']['output_mode'] = 'information'
                request.context['active_goal_snapshots'][0]['metadata']['output_mode'] = 'information'
            model = ReplayModel(json.dumps(raw))
            resolver = FastPlannerResolver if tier == 'fast' else DeepPlannerResolver
            result = await resolver(model, StaticCatalog(catalog)).resolve(request)
            assert model.calls == 1
            if mutation == 'valid' and tier == 'deep':
                assert result.disposition == 'execute', result.metadata
                assert not result.metadata.get('failure_class')
            else:
                # Fast's whole-Goal catalog excludes this cross-domain query;
                # composition belongs to Deep, not a wider Fast authority.
                assert result.metadata.get('failure_class'), result
    asyncio.run(check())


def test_new_gi_ready_at_is_not_claimed_by_seeded_timer_case():
    case = load('delayed')
    raw = copy.deepcopy(case['model_steps'][0]['response'])
    raw['responsibilities'][0]['binding_items']['ready_at'] = '2099-09-04T19:00:00+08:00'
    assert not Draft202012Validator(case['model_steps'][0]['request']['format']).is_valid(raw)
    assert case['initial_goal_resolution']['new_goals'][0]['object']['bindings']['ready_at']


def test_reference_corpus_matches_reviewed_freeze():
    manifest = json.loads((CASES/'manifest.json').read_text())
    actual = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in CASES.glob('workflow-*.json')}
    assert actual == manifest['case_sha256']
    assert manifest['model_ability_evaluated'] is False
