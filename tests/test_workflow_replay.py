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

CORPUS = CASES.parent/'workflow_scenarios'


def test_expanded_corpus_identity_coverage_and_split_integrity():
    from collections import Counter, defaultdict
    from benchmarks.integration.workflow_corpus import FAMILIES
    manifest = json.loads((CORPUS/'manifest.json').read_text())
    paths = sorted(CORPUS.glob('workflow-*.json'))
    assert len(paths) == manifest['count'] == 1500
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == manifest['case_sha256']
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (CORPUS/'artifacts').glob('*.json')} == manifest['artifact_sha256']
    assert manifest['unrendered_requests'] == []
    cases = [json.loads(p.read_text()) for p in paths]
    assert Counter(c['coverage_family'] for c in cases) == {family:50 for family in FAMILIES}
    assert Counter(c['split'] for c in cases) == manifest['splits']
    splits = defaultdict(set)
    for case in cases:
        splits[case['contrast_set']].add(case['split'])
        assert case['provenance']['training_eligible'] is False
        assert case['provenance']['independent_inference_per_case'] is False
        for step in case['model_steps']:
            assert step['training_eligible'] is False
            assert 'request' in step and 'request_unavailable' not in step
    assert len(splits) == 10 and all(len(values) == 1 for values in splits.values())
    assert manifest['training_eligible'] is False


@pytest.mark.parametrize('path', sorted(CORPUS.glob('workflow-*-blink-0-0.json')), ids=lambda p:p.stem)
def test_expanded_family_regression(path, tmp_path):
    from benchmarks.integration.model_replay import load_case
    case = load_case(path)
    result = asyncio.run(run_case(case, tmp_path))
    if case['coverage_family'] == 'new_readiness_gap':
        assert result['verdict'] == 'known_contract_gap' and not result['passed']
        assert result['known_issue'] == 60
    else:
        assert result['passed']


def test_shared_packet_parts_are_hash_checked(tmp_path):
    from benchmarks.integration.model_replay import load_case
    value = b'{"frozen":"packet"}'
    digest = hashlib.sha256(value).hexdigest()
    (tmp_path/'artifacts').mkdir()
    part = tmp_path/'artifacts'/f'{digest}.json'
    part.write_bytes(value)
    case = tmp_path/'case.json'
    case.write_text(json.dumps({'request':{'$artifact':digest}}))
    assert load_case(case) == {'request':{'frozen':'packet'}}
    part.write_text('{"frozen":"changed"}')
    with pytest.raises(ReplayMismatch, match='hash mismatch'):
        load_case(case)
    part.unlink()
    with pytest.raises(FileNotFoundError):
        load_case(case)


@pytest.mark.parametrize('role', ['gi', 'ga', 'fast', 'deep'])
def test_only_selected_role_receives_actual_answer_blind_packet(role, tmp_path):
    from benchmarks.integration.model_replay import load_case
    family = 'normal_deep' if role == 'deep' else 'normal_fast'
    case = load_case(CORPUS/f'workflow-{family}-blink-0-0.json')
    case['private_adjudication'] = 'REFERENCE_AND_RUBRIC_MUST_NOT_ENTER_INFERENCE'
    step = copy.deepcopy(next(s for s in case['model_steps'] if s['role'] == role))
    step['request']['model'] = 'candidate-local'
    candidate = ModelReplay({'model_steps':[step]})
    with ReplayServer(candidate) as server:
        replay = ModelReplay(case, candidate={'role':role,'url':server.url,'model':'candidate-local'})
        candidate.bindings = replay.bindings
        result = asyncio.run(run_case(case, tmp_path, replay))
    candidate.assert_finished()
    assert result['passed'] and replay.candidate_calls == 1
    assert [r['step'] for r in replay.records if r['source'] == 'candidate'] == [step['name']]
    assert len([r for r in replay.records if r['source'] == 'replay']) == len(case['model_steps']) - 1
    assert candidate.records[0]['request'] == step['request']
    assert case['private_adjudication'] not in json.dumps(candidate.records[0]['request'])
    assert replay.records[case['model_steps'].index(next(s for s in case['model_steps'] if s['role'] == role))]['raw_transport_response']


def test_valid_candidate_variation_stops_at_uncovered_downstream_branch(tmp_path):
    from benchmarks.integration.model_replay import load_case
    case = load_case(CORPUS/'workflow-normal_fast-blink-0-0.json')
    step = copy.deepcopy(case['model_steps'][0])
    step['request']['model'] = 'candidate-local'
    step['response']['responsibilities'][0]['confidence'] = 0.75
    candidate = ModelReplay({'model_steps':[step]})
    with ReplayServer(candidate) as server:
        replay = ModelReplay(case, candidate={'role':'gi','url':server.url,'model':'candidate-local'})
        with pytest.raises(Exception):
            asyncio.run(run_case(case, tmp_path, replay))
    failure = json.loads((tmp_path/'failure.json').read_text())
    assert failure['verdict'] == 'uncovered_replay_branch'
    assert replay.position == replay.candidate_calls == 1
    assert replay.records[0]['response']['responsibilities'][0]['confidence'] == 0.75
    assert replay.records[0]['schema_errors'] == []
    assert failure['provider_calls'] == []
    with pytest.raises(ReplayMismatch):
        replay.assert_finished()


def test_candidate_mode_rejects_fault_injection_references():
    from benchmarks.integration.model_replay import load_case
    case = load_case(CORPUS/'workflow-gi_unknown_binding-blink-0-0.json')
    with pytest.raises(ValueError, match='intentional model faults'):
        ModelReplay(case, candidate={'role':'gi','url':'http://127.0.0.1:1','model':'unused'})


def test_candidate_transport_preserves_incomplete_provider_envelope():
    case = load()
    step = copy.deepcopy(case['model_steps'][0])
    step['request']['model'] = 'candidate-local'
    candidate = ModelReplay({'model_steps':[step]})
    original_reply = candidate.reply
    def incomplete(path, request):
        envelope = original_reply(path, request)
        envelope.update(done=False, done_reason='length')
        return envelope
    candidate.reply = incomplete
    with ReplayServer(candidate) as server:
        replay = ModelReplay(case, candidate={'role':'gi','url':server.url,'model':'candidate-local'})
        actual = replay.reply('/api/chat', case['model_steps'][0]['request'])
    assert actual['done'] is False and actual['done_reason'] == 'length'
    assert json.loads(replay.records[0]['raw_transport_response']) == actual


def test_candidate_http_failure_has_raw_evidence_and_no_reference_fallback():
    case = load()
    candidate = ModelReplay({'model_steps':[]})
    with ReplayServer(candidate) as server:
        replay = ModelReplay(case, candidate={'role':'gi','url':server.url,'model':'candidate-local'})
        with pytest.raises(ReplayMismatch, match='HTTP 409'):
            replay.reply('/api/chat', case['model_steps'][0]['request'])
    assert replay.position == 0 and replay.candidate_calls == 1
    assert replay.records[0]['http_status'] == 409
    assert 'unexpected extra model call' in replay.records[0]['raw_transport_response']
    assert 'response' not in replay.records[0]
